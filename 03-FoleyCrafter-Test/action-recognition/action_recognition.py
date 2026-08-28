"""
MODULE 2 — Temporal Action Recognition (Qwen2.5-VL-3B-Instruct, Apple M4 / MPS / BF16)

    VIDEO -> frames (video stream ONLY) -> overlapping windows -> Qwen
          -> ACTION/EVIDENCE per window -> merge -> timestamped action segments

DESIGN
  * Qwen is NEVER asked for timestamps. It answers only "what is happening here?".
    Timing comes from each window's known position on the timeline.
    (Semantics from the VLM; timing from the windowing.)
  * Open vocabulary: no candidate labels are ever shown to the model.
  * Merging uses ACTION-HEAD matching (the '-ing' verb), not numeric confidence
    thresholds, so it stays transparent and explainable.
  * Model is loaded ONCE and reused for every window.

AUDIO: frames are extracted with `ffmpeg -map 0:v:0`. The audio stream is never
opened, decoded, or referenced, and no audio tensor is ever constructed.
"""
import gc, json, os, re, subprocess, threading, time
import numpy as np, psutil, torch
from transformers import (AutoProcessor, Qwen2_5_VLForConditionalGeneration,
                          StoppingCriteria, StoppingCriteriaList)

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "module2_test_video.mp4")
RESULTS = os.path.join(HERE, "results")
MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"

WINDOW_S, STRIDE_S = 2.0, 1.0
FRAMES_PER_WINDOW, TW, TH = 8, 448, 252
MAX_NEW_TOKENS = 96
MIN_AVAIL_GB, MAX_SWAP_GROWTH_GB = 1.5, 5.0

PROMPT = (
    "You are analyzing a video for an action-recognition system.\n\n"
    "Look only at the visual content.\n\n"
    "Identify the main physical action occurring during this video segment.\n\n"
    "Return:\n"
    "ACTION: <short action phrase>\n"
    "EVIDENCE: <brief visual evidence>\n\n"
    "Do not infer sound.\n"
    "Do not infer unseen events.\n"
    "Do not invent actions that are not visually supported."
)

FILLERS = {"a","an","the","person","man","woman","someone","people","is","are","being",
           "in","on","at","of","to","toward","towards","from","with","his","her","their",
           "it","its","and","then","video","segment","frame","scene","clip","appears"}

# ---------------------------------------------------------------- memory guard
BASE_SWAP = psutil.swap_memory().used / 1e9
stats = {"peak_used": 0.0, "min_avail": 999.0, "peak_swap": 0.0, "breach": None}
_stop = threading.Event()

def _monitor():
    while not _stop.is_set():
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        a, s = vm.available/1e9, sw.used/1e9
        stats["peak_used"] = max(stats["peak_used"], vm.used/1e9)
        stats["min_avail"] = min(stats["min_avail"], a)
        stats["peak_swap"] = max(stats["peak_swap"], s)
        if stats["breach"] is None:
            if a < MIN_AVAIL_GB: stats["breach"] = f"available {a:.2f}GB < {MIN_AVAIL_GB}GB"
            elif s - BASE_SWAP > MAX_SWAP_GROWTH_GB: stats["breach"] = f"swap +{s-BASE_SWAP:.2f}GB > {MAX_SWAP_GROWTH_GB}GB"
        time.sleep(0.05)

class MemoryGuard(StoppingCriteria):
    def __call__(self, input_ids, scores, **kw): return stats["breach"] is not None

def snap(tag):
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    print(f"[MEM] {tag:34s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB swap={sw.used/1e9:5.2f}GB")

# ---------------------------------------------------------------- video utils
def probe(path):
    v = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
        "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames",
        "-show_entries","format=duration","-of","default=noprint_wrappers=1",path],
        capture_output=True, text=True)
    meta = dict(l.split("=",1) for l in v.stdout.strip().splitlines() if "=" in l)
    st = subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type",
        "-of","csv=p=0",path], capture_output=True, text=True)
    meta["audio_present"] = "audio" in st.stdout
    return meta

def extract_video_frames(path, w, h):
    """VIDEO STREAM ONLY: `-map 0:v:0`. The audio stream is never decoded."""
    out = subprocess.run(["ffmpeg","-v","error","-i",path,"-map","0:v:0",
        "-vf",f"scale={w}:{h}","-f","image2pipe","-pix_fmt","rgb24","-vcodec","rawvideo","-"],
        capture_output=True).stdout
    fb = w*h*3
    n = len(out)//fb
    return np.frombuffer(out, dtype=np.uint8)[:n*fb].reshape(n, h, w, 3)

def plan_windows(duration):
    win = min(WINDOW_S, duration)
    span = duration - win
    if span <= 1e-6: return [(0.0, duration)]
    starts, s = [], 0.0
    while s < span - 1e-6:
        starts.append(round(s, 3)); s += STRIDE_S
    # snap final window to the end, unless it duplicates the previous one
    if not starts or abs(span - starts[-1]) > 0.25:
        starts.append(round(span, 3))
    return [(st, round(st+win, 3)) for st in starts]

# ---------------------------------------------------------------- parsing/merge
def parse_response(text):
    action = evidence = ""
    m = re.search(r"ACTION\s*:\s*(.+)", text, re.I)
    if m: action = m.group(1).splitlines()[0].strip().strip('".')
    m = re.search(r"EVIDENCE\s*:\s*(.+)", text, re.I | re.S)
    if m: evidence = " ".join(m.group(1).split()).strip().strip('"')
    if not action:  # fallback: first non-empty line
        for ln in text.splitlines():
            if ln.strip(): action = ln.strip().strip('".'); break
    return action, evidence

def content_words(phrase):
    toks = re.findall(r"[a-z]+", phrase.lower())
    return [t for t in toks if t not in FILLERS]

def action_head(phrase):
    """Primary '-ing' verb = the action head. Falls back to first content word."""
    cw = content_words(phrase)
    for t in cw:
        if t.endswith("ing") and len(t) > 4:
            return t
    return cw[0] if cw else ""

def same_action(a, b):
    ha, hb = action_head(a), action_head(b)
    if ha and hb:
        return ha == hb                     # primary rule: heads must match
    A, B = set(content_words(a)), set(content_words(b))
    if not A or not B: return False
    return len(A & B) / min(len(A), len(B)) >= 0.5   # fallback only

def merge(windows):
    segs, cur = [], None
    for i, w in enumerate(windows):
        if cur and same_action(cur["action"], w["action"]):
            cur["end"] = max(cur["end"], w["end"])
            cur["supporting_windows"].append(i)
            cur["_variants"].append(w["action"])
        else:
            if cur: segs.append(cur)
            cur = {"action": w["action"], "start": w["start"], "end": w["end"],
                   "supporting_windows": [i], "_variants": [w["action"]]}
    if cur: segs.append(cur)
    out = []
    for s in segs:
        # representative label = most common variant, tie-broken by first occurrence
        best = max(set(s["_variants"]), key=lambda v: (s["_variants"].count(v), -s["_variants"].index(v)))
        out.append({"action": best, "action_head": action_head(best),
                    "start": round(s["start"],3), "end": round(s["end"],3),
                    "supporting_windows": s["supporting_windows"],
                    "variants": s["_variants"]})
    return out

# ---------------------------------------------------------------- main
def main():
    t_all = time.time()
    os.makedirs(RESULTS, exist_ok=True)
    print(f"baseline swap={BASE_SWAP:.2f}GB | guards: avail<{MIN_AVAIL_GB}GB swap+>{MAX_SWAP_GROWTH_GB}GB")
    snap("baseline")
    threading.Thread(target=_monitor, daemon=True).start()

    meta = probe(VIDEO)
    dur = float(meta["duration"])
    print(f"\nvideo: {meta['width']}x{meta['height']} {meta['codec_name']} "
          f"dur={dur:.3f}s fps={meta['r_frame_rate']} frames={meta['nb_frames']} "
          f"audio_present={meta['audio_present']} -> audio NEVER decoded")

    t0 = time.time()
    frames = extract_video_frames(VIDEO, TW, TH)
    extract_s = time.time() - t0
    total_frames = len(frames)
    ftimes = np.linspace(0, dur, total_frames, endpoint=False)
    print(f"decoded {total_frames} frames @ {TW}x{TH} in {extract_s:.2f}s "
          f"({frames.nbytes/1e6:.1f} MB) — no audio tensor exists")

    wins = plan_windows(dur)
    print(f"\nwindow plan: {WINDOW_S}s window / {STRIDE_S}s stride -> {len(wins)} windows")
    for i,(a,b) in enumerate(wins,1): print(f"   W{i:2d}: {a:6.2f} - {b:6.2f}")

    print("\n>>> loading Qwen2.5-VL-3B-Instruct ONCE -> MPS (bf16) <<<")
    t0 = time.time()
    proc = AutoProcessor.from_pretrained(MODEL)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL, dtype=torch.bfloat16).to("mps").eval()
    torch.mps.synchronize()
    load_s = time.time() - t0
    print(f"    load+transfer: {load_s:.2f}s | all params on mps: "
          f"{all(p.device.type=='mps' for p in model.parameters())}")
    snap("after model on MPS")
    if stats["breach"]:
        print(f"!!! ABORT before inference: {stats['breach']}"); _stop.set(); return

    chat = proc.apply_chat_template(
        [{"role":"user","content":[{"type":"video"},{"type":"text","text":PROMPT}]}],
        tokenize=False, add_generation_prompt=True)

    results, inf_times = [], []
    print(f"\n>>> running {len(wins)} windows (model reused; no reload) <<<")
    for i,(ws,we) in enumerate(wins, 1):
        sel = np.where((ftimes >= ws) & (ftimes < we))[0]
        if len(sel) == 0:
            sel = np.array([min(int(ws/dur*total_frames), total_frames-1)])
        pick = sel[np.linspace(0, len(sel)-1, FRAMES_PER_WINDOW, dtype=int)]
        clip = list(np.ascontiguousarray(frames[pick]))

        inputs = proc(text=[chat], videos=[clip], return_tensors="pt")
        inputs = {k:(v.to("mps") if hasattr(v,"to") else v) for k,v in inputs.items()}

        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                 stopping_criteria=StoppingCriteriaList([MemoryGuard()]))
        torch.mps.synchronize()
        inf_times.append(time.time()-t0)

        raw = proc.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        action, evidence = parse_response(raw)
        results.append({"window": i, "start": ws, "end": we,
                        "action": action, "evidence": evidence,
                        "action_head": action_head(action), "raw": raw,
                        "frames_used": len(sel), "inference_time": round(inf_times[-1],2)})
        print(f"\n  W{i:2d} [{ws:5.2f}-{we:5.2f}] ({inf_times[-1]:.1f}s)")
        print(f"     ACTION:   {action}")
        print(f"     EVIDENCE: {evidence[:110]}")

        del inputs, out, clip
        gc.collect(); torch.mps.empty_cache()
        if stats["breach"]:
            print(f"\n!!! MEMORY GUARD BREACHED at window {i}: {stats['breach']} — STOPPING !!!")
            break

    segments = merge(results)
    print(f"\n>>> MERGED SEGMENTS ({len(segments)}) <<<")
    for s in segments:
        print(f"   {s['start']:5.2f} - {s['end']:5.2f}  {s['action']}  "
              f"[head={s['action_head']}, windows={s['supporting_windows']}]")

    print("\n>>> releasing model <<<")
    del model
    gc.collect(); torch.mps.empty_cache(); time.sleep(2)
    snap("after release")
    _stop.set(); time.sleep(0.2)
    total_s = time.time() - t_all
    final_swap = psutil.swap_memory().used/1e9

    payload = {
        "module": "Module 2 - Temporal Action Recognition",
        "model": MODEL, "device": "mps", "dtype": "bfloat16",
        "video": {"path": VIDEO, "duration": round(dur,3),
                  "fps": meta["r_frame_rate"], "fps_avg": meta["avg_frame_rate"],
                  "frame_count": int(meta["nb_frames"]), "resolution": f"{meta['width']}x{meta['height']}",
                  "codec": meta["codec_name"], "audio_present": meta["audio_present"],
                  "audio_used": False},
        "config": {"window_s": WINDOW_S, "stride_s": STRIDE_S,
                   "frames_per_window": FRAMES_PER_WINDOW, "resize": f"{TW}x{TH}",
                   "max_new_tokens": MAX_NEW_TOKENS, "prompt": PROMPT,
                   "merge_rule": "action-head (-ing verb) match; fallback content containment>=0.5"},
        "windows": results,
        "actions": [{k:v for k,v in s.items() if k != "variants"} for s in segments],
        "actions_detail": segments,
        "timing": {"model_load_s": round(load_s,2), "frame_extraction_s": round(extract_s,2),
                   "total_inference_s": round(sum(inf_times),2),
                   "avg_window_inference_s": round(float(np.mean(inf_times)),2) if inf_times else None,
                   "total_wall_s": round(total_s,2)},
        "memory": {"baseline_swap_gb": round(BASE_SWAP,2), "peak_used_gb": round(stats["peak_used"],2),
                   "min_available_gb": round(stats["min_avail"],2), "peak_swap_gb": round(stats["peak_swap"],2),
                   "final_swap_gb": round(final_swap,2), "guard_breach": stats["breach"]},
    }
    jp = os.path.join(RESULTS, "module2_action_segments.json")
    with open(jp,"w") as f: json.dump(payload, f, indent=2)

    tp = os.path.join(RESULTS, "module2_action_timeline.txt")
    with open(tp,"w") as f:
        f.write(f"MODULE 2 — TEMPORAL ACTION RECOGNITION (Qwen2.5-VL-3B-Instruct)\n")
        f.write(f"VIDEO: {VIDEO}\nDURATION: {dur:.3f}s  {meta['width']}x{meta['height']}  "
                f"{meta['r_frame_rate']} fps  {meta['nb_frames']} frames\n")
        f.write(f"WINDOW: {WINDOW_S}s  STRIDE: {STRIDE_S}s  FRAMES/WINDOW: {FRAMES_PER_WINDOW}\n\n")
        f.write("RAW WINDOW PREDICTIONS\n\n")
        for r in results:
            f.write(f"{r['start']:5.2f} {'-'*14} {r['end']:5.2f}  {r['action']}\n")
        f.write("\nMERGED ACTION SEGMENTS\n\n")
        for s in segments:
            f.write(f"{s['start']:5.2f} {'-'*14} {s['end']:5.2f}  {s['action']}\n")
    print(f"\nWrote {jp}\nWrote {tp}")

    print("\n>>> PERFORMANCE <<<")
    print(f"  model load:      {load_s:.2f}s")
    print(f"  frame extract:   {extract_s:.2f}s")
    print(f"  windows:         {len(results)}")
    print(f"  avg inference:   {np.mean(inf_times):.2f}s/window")
    print(f"  total inference: {sum(inf_times):.2f}s")
    print(f"  total wall:      {total_s:.2f}s")
    print("\n>>> MEMORY <<<")
    print(f"  peak used:     {stats['peak_used']:.2f}GB")
    print(f"  min available: {stats['min_avail']:.2f}GB")
    print(f"  baseline swap: {BASE_SWAP:.2f}GB")
    print(f"  peak swap:     {stats['peak_swap']:.2f}GB (growth {stats['peak_swap']-BASE_SWAP:+.2f}GB)")
    print(f"  final swap:    {final_swap:.2f}GB")
    print(f"  guard breach:  {stats['breach'] or 'NONE'}")
    print("\nRESULT:", "MODULE2_TEST_COMPLETED" if not stats["breach"] else "MODULE2_ABORTED_MEMORY_GUARD")

if __name__ == "__main__":
    main()

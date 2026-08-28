"""
STEP 8: ONE controlled real-video inference — Qwen2.5-VL-3B-Instruct on M4/MPS.

8 frames @ 448x252, video stream ONLY (`ffmpeg -map 0:v:0`).
Audio is never decoded; no audio tensor is ever constructed.
Exactly ONE inference. No retries, no prompt tuning.

Hard guards: abort if available memory < 1.5GB or swap grows > 5GB.
"""
import gc, subprocess, threading, time
import numpy as np, psutil, torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, StoppingCriteria, StoppingCriteriaList

VIDEO = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"
N_FRAMES, TW, TH = 8, 448, 252
MIN_AVAIL_GB, MAX_SWAP_GROWTH_GB = 1.5, 5.0

PROMPT = ("What action is the person performing in this video? Describe the main visible "
          "action briefly and objectively. Do not infer sounds or audio. "
          "Answer with one short action phrase.")

BASE_SWAP = psutil.swap_memory().used / 1e9
stats = {"peak_used": 0.0, "min_avail": 999.0, "peak_swap": 0.0, "breach": None}
_stop = threading.Event()

def monitor():
    while not _stop.is_set():
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        u, a, s = vm.used/1e9, vm.available/1e9, sw.used/1e9
        stats["peak_used"] = max(stats["peak_used"], u)
        stats["min_avail"] = min(stats["min_avail"], a)
        stats["peak_swap"] = max(stats["peak_swap"], s)
        if stats["breach"] is None:
            if a < MIN_AVAIL_GB: stats["breach"] = f"available {a:.2f}GB < {MIN_AVAIL_GB}GB"
            elif s - BASE_SWAP > MAX_SWAP_GROWTH_GB: stats["breach"] = f"swap +{s-BASE_SWAP:.2f}GB > {MAX_SWAP_GROWTH_GB}GB"
        time.sleep(0.05)

class MemoryGuard(StoppingCriteria):
    """Aborts generation mid-flight if a memory guard trips."""
    def __call__(self, input_ids, scores, **kw): return stats["breach"] is not None

def snap(tag):
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    print(f"[MEM] {tag:32s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB swap={sw.used/1e9:5.2f}GB")

t_all = time.time()
print(f"baseline swap={BASE_SWAP:.2f}GB | guards: avail<{MIN_AVAIL_GB}GB, swap growth>{MAX_SWAP_GROWTH_GB}GB")
snap("baseline")
threading.Thread(target=monitor, daemon=True).start()

# --- 3/4: frame extraction, VIDEO STREAM ONLY ------------------------------
print(f"\n>>> 3/4. extracting frames: ffmpeg -map 0:v:0 (audio stream NEVER decoded) <<<")
t0 = time.time()
dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
    "-of","default=noprint_wrappers=1:nokey=1",VIDEO],capture_output=True,text=True).stdout.strip())
# ONLY 0:v:0 is mapped -> the AAC stream is not opened, decoded, or referenced.
raw = subprocess.run(
    ["ffmpeg","-v","error","-i",VIDEO,"-map","0:v:0",
     "-vf",f"scale={TW}:{TH}","-f","image2pipe","-pix_fmt","rgb24","-vcodec","rawvideo","-"],
    capture_output=True).stdout
fb = TW*TH*3
total = len(raw)//fb
allf = np.frombuffer(raw, dtype=np.uint8)[:total*fb].reshape(total, TH, TW, 3)
idx = np.linspace(0, total-1, N_FRAMES, dtype=int)
video_np = np.ascontiguousarray(allf[idx])       # (8, 252, 448, 3)
extract_s = time.time() - t0
print(f"    duration={dur:.4f}s decoded={total} frames @ {TW}x{TH}")
print(f"    sampled {N_FRAMES} uniformly: indices {idx.tolist()}")
print(f"    5. frame array: shape={video_np.shape} dtype={video_np.dtype} "
      f"({video_np.nbytes/1e6:.1f} MB)  <- video only, no audio tensor exists")
print(f"    extraction time: {extract_s:.2f}s")

# --- load model ------------------------------------------------------------
print("\n>>> loading model -> MPS (bf16) <<<")
t0 = time.time()
proc = AutoProcessor.from_pretrained(MODEL)
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL, dtype=torch.bfloat16)
model = model.to("mps").eval()
torch.mps.synchronize()
load_s = time.time() - t0
print(f"    load+transfer: {load_s:.2f}s | params on mps: {all(p.device.type=='mps' for p in model.parameters())}")
snap("after model on MPS")
if stats["breach"]:
    print(f"\n!!! GUARD BREACHED before inference: {stats['breach']} — ABORTING !!!"); _stop.set(); raise SystemExit(2)

# --- preprocessing ---------------------------------------------------------
print("\n>>> preprocessing <<<")
t0 = time.time()
msgs = [{"role":"user","content":[{"type":"video"},{"type":"text","text":PROMPT}]}]
text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inputs = proc(text=[text], videos=[list(video_np)], return_tensors="pt")
prep_s = time.time() - t0
for k,v in inputs.items():
    if hasattr(v,"shape"): print(f"    {k}: {tuple(v.shape)} {v.dtype}")
if "video_grid_thw" in inputs:
    g = inputs["video_grid_thw"]
    print(f"    video_grid_thw={g.tolist()} -> {int(g.prod())} patches -> {int(g.prod())//4} visual tokens")
print(f"    preprocessing time: {prep_s:.2f}s")
inputs = {k:(v.to("mps") if hasattr(v,"to") else v) for k,v in inputs.items()}
snap("after preprocessing")

# --- ONE inference ---------------------------------------------------------
print(f"\n>>> ONE inference (prompt is neutral; no candidate answer given) <<<")
print(f'    PROMPT: "{PROMPT}"')
t0 = time.time()
with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=64, do_sample=False,
                         stopping_criteria=StoppingCriteriaList([MemoryGuard()]))
torch.mps.synchronize()
infer_s = time.time() - t0
snap("after inference")

trimmed = out[0][inputs["input_ids"].shape[1]:]
answer = proc.decode(trimmed, skip_special_tokens=True).strip()
total_s = time.time() - t_all

print("\n" + "="*70)
print("QWEN RESPONSE:")
print(f"  {answer!r}")
print("="*70)
print(f"\n  tokens generated: {len(trimmed)}")
print(f"  aborted by guard: {stats['breach'] or 'NO'}")

# --- release / recovery ----------------------------------------------------
print("\n>>> releasing model <<<")
del model, out, inputs, trimmed
gc.collect(); torch.mps.empty_cache(); time.sleep(3)
snap("after release")
_stop.set(); time.sleep(0.2)
final_swap = psutil.swap_memory().used/1e9

print("\n>>> TIMING <<<")
print(f"  model load+transfer: {load_s:.2f}s")
print(f"  frame extraction:    {extract_s:.2f}s")
print(f"  preprocessing:       {prep_s:.2f}s")
print(f"  inference:           {infer_s:.2f}s")
print(f"  total wall:          {total_s:.2f}s")
print("\n>>> MEMORY <<<")
print(f"  peak used:      {stats['peak_used']:.2f}GB")
print(f"  min available:  {stats['min_avail']:.2f}GB")
print(f"  baseline swap:  {BASE_SWAP:.2f}GB")
print(f"  peak swap:      {stats['peak_swap']:.2f}GB (growth {stats['peak_swap']-BASE_SWAP:+.2f}GB)")
print(f"  final swap:     {final_swap:.2f}GB")
print(f"  guard breach:   {stats['breach'] or 'NONE'}")
print("\nRESULT:", "STEP8_COMPLETED" if not stats["breach"] else "STEP8_ABORTED_MEMORY_GUARD")

"""
Temporal Action Recognition module (X-CLIP, zero-shot, Apple Silicon / MPS).

    VIDEO -> overlapping temporal windows -> X-CLIP -> action segments

Independent of FoleyCrafter: imports nothing from it, touches no FoleyCrafter
environment/checkpoint, and generates no audio.

Video frames only: extraction uses `ffmpeg -map 0:v:0`, so any audio stream in
the source is never decoded or used.

-------------------------------------------------------------------------------
DESIGN NOTES (kept deliberately simple and explainable for the FYP report)
-------------------------------------------------------------------------------
1. WINDOWING (adaptive)
   Target window = 1.0s, stride = 0.5s. Rationale: our earlier 0.5s windows were
   unstable, partly because a 0.5s window supplies only ~15 real frames to a model
   that requires 32, forcing heavy frame duplication. A 1.0s window supplies ~29.
   The window is capped at the video duration, and if the clip is too short to
   produce at least MIN_WINDOWS windows, the stride is reduced so the windows
   spread evenly. The last window is snapped to end exactly at the video end.

2. PER-WINDOW SCORING
   Each window runs its OWN X-CLIP forward pass over the full vocabulary and
   yields a softmax distribution. Top-3 candidates are recorded for transparency.

3. DECISION LAYER (no blind top-1)
   Thresholds are expressed as multiples of uniform chance (1/N) so they remain
   meaningful if the vocabulary size changes:
     - confidence gate: top1 >= MIN_CONF_RATIO * (1/N)
     - separation gate: top1 >= MARGIN_RATIO * top2
   A window failing either gate is labelled UNKNOWN rather than forced into a class.

4. TEMPORAL SMOOTHING
   A mode filter (kernel 3) removes isolated single-window flicker: a window is
   overwritten only when BOTH neighbours agree with each other and disagree with it.

5. SEGMENTATION
   Consecutive windows with the same verdict are merged. Segment confidence is the
   mean of the member windows' top-1 scores for that action. Segments are marked
   "candidate" or "low-confidence"; UNKNOWN segments are preserved (not deleted)
   so gaps in coverage remain visible.
"""
import json
import os
import subprocess
import time
from collections import Counter

import numpy as np
import psutil
import torch
from PIL import Image
from transformers import XCLIPModel, XCLIPProcessor

from action_vocabulary import (
    ACTION_LABELS,
    ACTION_TO_CATEGORY,
    UNKNOWN_ACTION,
    uniform_chance,
)

VIDEO_PATH = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL_ID = "microsoft/xclip-base-patch16-zero-shot"
DEVICE = "mps"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# --- windowing -------------------------------------------------------------
TARGET_WINDOW = 1.0      # seconds
TARGET_STRIDE = 0.5      # seconds
MIN_WINDOWS = 4          # adapt stride down on short clips to reach this many

# --- decision layer --------------------------------------------------------
MIN_CONF_RATIO = 3.0     # top1 must beat 3x uniform chance
MARGIN_RATIO = 1.25      # top1 must be at least 1.25x top2
SMOOTHING_KERNEL = 3     # mode filter width (odd)

_peak_used_gb = 0.0
_peak_swap_gb = 0.0


def mem(label, verbose=True):
    global _peak_used_gb, _peak_swap_gb
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    _peak_used_gb = max(_peak_used_gb, vm.used / 1e9)
    _peak_swap_gb = max(_peak_swap_gb, sw.used / 1e9)
    if verbose:
        print(f"=== MEMORY: {label} === used={vm.used/1e9:.2f}GB "
              f"available={vm.available/1e9:.2f}GB swap={sw.used/1e9:.2f}GB")
    return {"used_gb": vm.used / 1e9, "swap_gb": sw.used / 1e9}


# ---------------------------------------------------------------------------
def probe_video(path):
    v = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,codec_name,r_frame_rate,avg_frame_rate,nb_frames",
         "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", path],
        capture_output=True, text=True)
    meta = dict(l.split("=", 1) for l in v.stdout.strip().splitlines() if "=" in l)
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    meta["audio_present"] = "audio" in streams.stdout
    return meta


def extract_video_frames(path, width, height):
    """Decode ONLY the video stream (`-map 0:v:0`); the audio stream is never read."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0",
         "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"],
        capture_output=True)
    fb = width * height * 3
    n = len(out.stdout) // fb
    return np.frombuffer(out.stdout, dtype=np.uint8)[: n * fb].reshape(n, height, width, 3)


def plan_windows(duration):
    """Adaptive overlapping windows; returns (windows, window_len, stride)."""
    window = min(TARGET_WINDOW, duration)
    stride = min(TARGET_STRIDE, window / 2)
    span = duration - window
    if span <= 1e-6:
        return [(0.0, duration)], window, stride
    n = int(np.floor(span / stride)) + 1
    if n < MIN_WINDOWS:
        stride = span / (MIN_WINDOWS - 1)
    starts = []
    s = 0.0
    while s < span - 1e-6:
        starts.append(s)
        s += stride
    starts.append(span)  # final window snapped to end exactly at duration
    return [(round(s, 4), round(s + window, 4)) for s in starts], window, stride


def decide(scores):
    """Apply confidence + separation gates. Returns (verdict, top3)."""
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top3 = [{"action": a, "score": round(float(s), 6)} for a, s in ranked[:3]]
    (a1, s1), (a2, s2) = ranked[0], ranked[1]
    conf_gate = s1 >= MIN_CONF_RATIO * uniform_chance()
    margin_gate = s1 >= MARGIN_RATIO * s2
    verdict = a1 if (conf_gate and margin_gate) else UNKNOWN_ACTION
    return verdict, top3, bool(conf_gate), bool(margin_gate)


def smooth(verdicts, k=SMOOTHING_KERNEL):
    """Mode filter: overwrite a window only if both neighbours agree with each other."""
    if len(verdicts) < k:
        return list(verdicts)
    out = list(verdicts)
    half = k // 2
    for i in range(half, len(verdicts) - half):
        neigh = verdicts[i - half:i + half + 1]
        others = [v for j, v in enumerate(neigh) if j != half]
        c = Counter(others)
        top, count = c.most_common(1)[0]
        if count == len(others) and top != verdicts[i]:
            out[i] = top
    return out


def build_segments(windows, verdicts, per_window_scores):
    segments, cur = [], None
    for (ws, we), verdict, scores in zip(windows, verdicts, per_window_scores):
        conf = float(scores[verdict]) if verdict != UNKNOWN_ACTION else 0.0
        if cur and cur["action"] == verdict:
            cur["end"] = max(cur["end"], we)
            cur["confs"].append(conf)
            cur["n_windows"] += 1
        else:
            if cur:
                segments.append(cur)
            cur = {"action": verdict, "start": ws, "end": we, "confs": [conf], "n_windows": 1}
    if cur:
        segments.append(cur)

    final = []
    for s in segments:
        if s["action"] == UNKNOWN_ACTION:
            conf, status = 0.0, "unknown"
        else:
            conf = float(np.mean(s["confs"]))
            status = "candidate" if conf >= MIN_CONF_RATIO * uniform_chance() else "low-confidence"
        final.append({
            "action": s["action"],
            "category": ACTION_TO_CATEGORY.get(s["action"], "unknown"),
            "start": round(s["start"], 4),
            "end": round(s["end"], 4),
            "confidence": round(conf, 6),
            "n_windows": s["n_windows"],
            "status": status,
        })
    return final


# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    print(f"Vocabulary: {len(ACTION_LABELS)} labels | uniform chance = {uniform_chance():.4f}")
    print(f"Gates: top1 >= {MIN_CONF_RATIO}x chance ({MIN_CONF_RATIO*uniform_chance():.4f}) "
          f"AND top1 >= {MARGIN_RATIO}x top2")
    mem("baseline (before model load)")

    assert torch.backends.mps.is_available(), "MPS unavailable"
    print("\n>>> Loading X-CLIP (cached; no download) -> MPS <<<")
    t_ld = time.time()
    processor = XCLIPProcessor.from_pretrained(MODEL_ID)
    model, info = XCLIPModel.from_pretrained(MODEL_ID, output_loading_info=True)
    assert not info["missing_keys"] and not info["unexpected_keys"], "checkpoint mismatch"
    model = model.to(DEVICE).eval()
    load_time = time.time() - t_ld
    frames_needed = model.config.vision_config.num_frames
    print(f"checkpoint integrity: missing=0 unexpected=0 | frames required={frames_needed}")
    print(f"model load time: {load_time:.2f}s")
    mem("after model load (MPS)")

    # --- video -------------------------------------------------------------
    meta = probe_video(VIDEO_PATH)
    duration = float(meta["duration"])
    w, h = int(meta["width"]), int(meta["height"])
    print(f"\nvideo: {w}x{h} {meta['codec_name']} dur={duration:.4f}s "
          f"fps_nom={meta['r_frame_rate']} fps_avg={meta['avg_frame_rate']} "
          f"nb_frames={meta['nb_frames']} audio_present={meta['audio_present']} (audio NOT used)")

    t_fe = time.time()
    frames = extract_video_frames(VIDEO_PATH, w, h)
    frame_extraction_time = time.time() - t_fe
    total_frames = len(frames)
    frame_times = np.linspace(0, duration, total_frames, endpoint=False)
    print(f"decoded {total_frames} video frames in {frame_extraction_time:.2f}s")

    windows, window_len, stride = plan_windows(duration)
    print(f"\nwindow plan: len={window_len:.3f}s stride={stride:.3f}s -> {len(windows)} windows")
    for i, (s, e) in enumerate(windows, 1):
        print(f"  W{i}: {s:.3f} - {e:.3f}")

    # --- per-window inference ---------------------------------------------
    print(f"\n>>> Running one X-CLIP pass per window ({len(windows)} total) <<<")
    mem("before inference loop")
    per_window_scores, raw_rows, inf_times = [], [], []

    for i, (ws, we) in enumerate(windows, 1):
        mask = (frame_times >= ws) & (frame_times < we)
        idx = np.where(mask)[0]
        if len(idx) == 0:
            idx = np.array([min(int(ws / duration * total_frames), total_frames - 1)])
        pick = idx[np.linspace(0, len(idx) - 1, frames_needed, dtype=int)]
        clip = [Image.fromarray(frames[j]) for j in pick]

        inputs = processor(text=ACTION_LABELS, videos=[clip], return_tensors="pt", padding=True)
        inputs = {k: (v.to(DEVICE) if hasattr(v, "to") else v) for k, v in inputs.items()}
        t_i = time.time()
        with torch.no_grad():
            probs = model(**inputs).logits_per_video.softmax(dim=1)[0].cpu().numpy()
        inf_times.append(time.time() - t_i)
        mem(f"window {i}", verbose=False)

        scores = {a: float(p) for a, p in zip(ACTION_LABELS, probs)}
        verdict, top3, conf_gate, margin_gate = decide(scores)
        per_window_scores.append(scores)
        raw_rows.append({
            "window": i, "start": ws, "end": we,
            "raw_frames_in_window": int(len(idx)), "frames_fed": int(frames_needed),
            "top3": top3, "verdict_before_smoothing": verdict,
            "passed_confidence_gate": conf_gate, "passed_margin_gate": margin_gate,
            "scores": {a: round(s, 6) for a, s in scores.items()},
        })
        print(f"\nW{i} {ws:.3f}-{we:.3f} ({len(idx)} raw frames -> {frames_needed})")
        for r, t in enumerate(top3, 1):
            print(f"   top{r}: {t['action']:<22} {t['score']:.4f}")
        print(f"   gates: conf={'PASS' if conf_gate else 'FAIL'} "
              f"margin={'PASS' if margin_gate else 'FAIL'} -> {verdict}")

    mem("after inference loop (peak)")

    # --- smoothing + segmentation -----------------------------------------
    raw_verdicts = [r["verdict_before_smoothing"] for r in raw_rows]
    smoothed = smooth(raw_verdicts)
    for r, s in zip(raw_rows, smoothed):
        r["verdict_after_smoothing"] = s
    changed = sum(1 for a, b in zip(raw_verdicts, smoothed) if a != b)
    print(f"\n>>> Smoothing (mode filter k={SMOOTHING_KERNEL}): {changed} window(s) changed <<<")

    segments = build_segments(windows, smoothed, per_window_scores)
    print("\n>>> FINAL ACTION SEGMENTS <<<")
    for s in segments:
        print(f"  {s['start']:.3f} - {s['end']:.3f}  {s['action']:<22} "
              f"conf={s['confidence']:.4f}  [{s['status']}]  ({s['n_windows']} windows)")

    total_wall = time.time() - t0

    # --- outputs -----------------------------------------------------------
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = {
        "module": "temporal_action_recognition",
        "model": MODEL_ID,
        "device": DEVICE,
        "video": VIDEO_PATH,
        "duration": round(duration, 6),
        "resolution": f"{w}x{h}",
        "codec": meta["codec_name"],
        "fps_nominal": meta["r_frame_rate"],
        "fps_average": meta["avg_frame_rate"],
        "frame_count": int(meta["nb_frames"]),
        "frames_decoded": int(total_frames),
        "audio_present": meta["audio_present"],
        "audio_used": False,
        "vocabulary_size": len(ACTION_LABELS),
        "vocabulary": ACTION_LABELS,
        "window_duration": round(window_len, 4),
        "stride": round(stride, 4),
        "num_windows": len(windows),
        "frames_per_window_fed_to_model": int(frames_needed),
        "decision_rules": {
            "uniform_chance": round(uniform_chance(), 6),
            "min_conf_ratio": MIN_CONF_RATIO,
            "min_conf_absolute": round(MIN_CONF_RATIO * uniform_chance(), 6),
            "margin_ratio": MARGIN_RATIO,
            "smoothing_kernel": SMOOTHING_KERNEL,
        },
        "windows": raw_rows,
        "segments": segments,
        "timing": {
            "model_load_time": round(load_time, 3),
            "frame_extraction_time": round(frame_extraction_time, 3),
            "total_inference_time": round(sum(inf_times), 3),
            "avg_inference_time_per_window": round(float(np.mean(inf_times)), 3),
            "total_wall_time": round(total_wall, 3),
        },
        "memory": {"peak_used_gb": round(_peak_used_gb, 3), "peak_swap_gb": round(_peak_swap_gb, 3)},
    }
    jp = os.path.join(RESULTS_DIR, "action_segments.json")
    with open(jp, "w") as f:
        json.dump(out, f, indent=2)

    tp = os.path.join(RESULTS_DIR, "action_timeline.txt")
    with open(tp, "w") as f:
        f.write(f"VIDEO: {VIDEO_PATH}\nDURATION: {duration:.3f}s   "
                f"WINDOW: {window_len:.3f}s   STRIDE: {stride:.3f}s   "
                f"VOCAB: {len(ACTION_LABELS)} labels\n\n")
        f.write("RAW WINDOW PREDICTIONS (top-1 before smoothing)\n\n")
        for r in raw_rows:
            t1 = r["top3"][0]
            f.write(f"{r['start']:5.2f} {'─'*18} {r['end']:5.2f}  "
                    f"{t1['action']:<22} {t1['score']:.3f}  -> {r['verdict_before_smoothing']}\n")
        f.write("\nFINAL SEGMENTS\n\n")
        for s in segments:
            f.write(f"{s['start']:5.2f} {'─'*18} {s['end']:5.2f}  "
                    f"{s['action']:<22} {s['confidence']:.3f}  [{s['status']}]\n")

    print(f"\nWrote {jp}\nWrote {tp}")
    print("\n>>> PERFORMANCE <<<")
    print(f"model load:        {load_time:.2f}s")
    print(f"frame extraction:  {frame_extraction_time:.2f}s")
    print(f"windows:           {len(windows)}")
    print(f"avg inference/win: {np.mean(inf_times):.3f}s")
    print(f"total inference:   {sum(inf_times):.2f}s")
    print(f"total wall:        {total_wall:.2f}s")
    print(f"peak memory:       {_peak_used_gb:.2f}GB")
    print(f"peak swap:         {_peak_swap_gb:.2f}GB")
    print("\nRESULT: ACTION_RECOGNITION_MODULE_TEST_PASS")


if __name__ == "__main__":
    main()

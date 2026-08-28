"""
X-CLIP TEMPORAL action-recognition test (sliding windows) — Module 2.

Isolated experiment. Does NOT import or touch any FoleyCrafter code,
environment, or checkpoints. Uses only: transformers, torch, PIL, numpy,
psutil, and the system ffmpeg CLI (video frames only, audio never read).

Research/smoke-test only: these timestamps are NOT ground truth.
"""
import json
import subprocess
import time

import numpy as np
import psutil
import torch
from PIL import Image
from transformers import XCLIPModel, XCLIPProcessor

VIDEO_PATH = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL_ID = "microsoft/xclip-base-patch16-zero-shot"
DEVICE = "mps"
RESULTS_DIR = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/action-recognition/results"

WINDOW_DURATION = 0.5
STRIDE = 0.25
CONFIDENCE_THRESHOLD = 0.15

CANDIDATE_LABELS = [
    "opening a door",
    "closing a door",
    "locking a door",
    "unlocking a door",
    "walking",
    "running",
    "clapping",
    "knocking on a door",
    "pouring liquid",
    "an object falling",
]

_peak_used_gb = 0.0


def mem_snapshot(label, verbose=True):
    global _peak_used_gb
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    used_gb = vm.used / 1e9
    _peak_used_gb = max(_peak_used_gb, used_gb)
    if verbose:
        print(f"=== MEMORY: {label} === used={used_gb:.2f}GB available={vm.available/1e9:.2f}GB swap_used={swap.used/1e9:.2f}GB")
    return {"used_gb": used_gb, "swap_used_gb": swap.used / 1e9}


t0 = time.time()
mem_before_load = mem_snapshot("before model load")

print("\n>>> torch.backends.mps.is_available() check <<<")
assert torch.backends.mps.is_available(), "MPS not available — stopping."
print("MPS available: True")

print("\n>>> Loading XCLIPProcessor + XCLIPModel (already cached, no re-download), moving to MPS <<<")
processor = XCLIPProcessor.from_pretrained(MODEL_ID)
model = XCLIPModel.from_pretrained(MODEL_ID)
model = model.to(DEVICE)
model.eval()
num_frames_needed = model.config.vision_config.num_frames
t_loaded = time.time()
model_load_time = t_loaded - t0
mem_after_load = mem_snapshot("after model load (on MPS)")
print(f"Model load time: {model_load_time:.1f}s, num_frames required: {num_frames_needed}")

# ---------------------------------------------------------------------------
print("\n>>> Extracting ALL video frames via ffmpeg -map 0:v:0 (video only, audio never read) <<<")
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", VIDEO_PATH],
    capture_output=True, text=True,
)
duration = float(probe.stdout.strip().split("=")[1])

probe_wh = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", VIDEO_PATH],
    capture_output=True, text=True,
)
w, h = [int(x) for x in probe_wh.stdout.strip().rstrip(",").split(",")]

extract = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", VIDEO_PATH, "-map", "0:v:0",
     "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"],
    capture_output=True,
)
frame_bytes = w * h * 3
raw = extract.stdout
total_frames = len(raw) // frame_bytes
all_frames = np.frombuffer(raw, dtype=np.uint8)[: total_frames * frame_bytes].reshape(total_frames, h, w, 3)
frame_times = np.linspace(0, duration, total_frames, endpoint=False)
print(f"Video duration: {duration:.6f}s, decoded {total_frames} raw video frames at {w}x{h}")

# ---------------------------------------------------------------------------
print("\n>>> Generating sliding windows (duration=0.5s, stride=0.25s) <<<")
windows = []
start = 0.0
while start < duration:
    end = start + WINDOW_DURATION
    if end > duration:
        # adjust final window so it does not exceed video duration
        adj_start = max(0.0, duration - WINDOW_DURATION)
        adj_end = duration
        if not windows or abs(windows[-1][0] - adj_start) > 1e-6:
            windows.append((adj_start, adj_end))
        break
    windows.append((start, end))
    start += STRIDE

for i, (s, e) in enumerate(windows, 1):
    print(f"Window {i}: {s:.2f} - {e:.2f}")

# ---------------------------------------------------------------------------
print(f"\n>>> Running X-CLIP inference on EACH of the {len(windows)} windows separately <<<")
window_results = []
inference_times = []

mem_before_inference = mem_snapshot("before temporal inference loop")

for i, (w_start, w_end) in enumerate(windows, 1):
    mask = (frame_times >= w_start) & (frame_times < w_end)
    sub_indices = np.where(mask)[0]
    if len(sub_indices) == 0:
        sub_indices = np.array([min(int(w_start / duration * total_frames), total_frames - 1)])
    resample_idx = np.linspace(0, len(sub_indices) - 1, num_frames_needed, dtype=int)
    chosen = sub_indices[resample_idx]
    sampled = [Image.fromarray(all_frames[j]) for j in chosen]

    inputs = processor(text=CANDIDATE_LABELS, videos=[sampled], return_tensors="pt", padding=True)
    inputs = {k: (v.to(DEVICE) if hasattr(v, "to") else v) for k, v in inputs.items()}

    t_i0 = time.time()
    with torch.no_grad():
        outputs = model(**inputs)
        probs = outputs.logits_per_video.softmax(dim=1)[0].cpu().numpy()
    t_i1 = time.time()
    inference_times.append(t_i1 - t_i0)
    mem_snapshot(f"after window {i} inference", verbose=False)

    scores = {label: float(p) for label, p in zip(CANDIDATE_LABELS, probs)}
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top1_label, top1_score = ranked[0]
    top2_label, top2_score = ranked[1]

    print(f"\nWindow {i}: {w_start:.2f} - {w_end:.2f} ({len(sub_indices)} raw frames in window, resampled to {num_frames_needed})")
    print(f"  Top-1: {top1_label} = {top1_score:.4f}")
    print(f"  Top-2: {top2_label} = {top2_score:.4f}")

    window_results.append({
        "start": round(w_start, 4),
        "end": round(w_end, 4),
        "scores": scores,
        "top1": top1_label,
        "top1_score": top1_score,
        "top2": top2_label,
        "top2_score": top2_score,
    })

t_inference_end = time.time()
total_temporal_inference_time = sum(inference_times)
mem_after_inference = mem_snapshot("after ALL temporal windows (peak)")

# ---------------------------------------------------------------------------
print("\n>>> TEMPORAL SEGMENTATION (simple consecutive-same-action grouping) <<<")
segments = []
current = None
for wr in window_results:
    if current is not None and current["action"] == wr["top1"]:
        current["end"] = max(current["end"], wr["end"])
        current["start"] = min(current["start"], wr["start"])
        current["scores"].append(wr["top1_score"])
    else:
        if current is not None:
            segments.append(current)
        current = {"action": wr["top1"], "start": wr["start"], "end": wr["end"], "scores": [wr["top1_score"]]}
if current is not None:
    segments.append(current)

final_segments = []
for seg in segments:
    confidence = float(np.mean(seg["scores"]))
    status = "candidate" if confidence >= CONFIDENCE_THRESHOLD else "low-confidence"
    final_segments.append({
        "action": seg["action"],
        "start": round(seg["start"], 4),
        "end": round(seg["end"], 4),
        "confidence": round(confidence, 4),
        "status": status,
    })
    print(f"{seg['action']}: {seg['start']:.2f} - {seg['end']:.2f}  confidence={confidence:.4f} [{status}]")

# ---------------------------------------------------------------------------
result_json = {
    "video": VIDEO_PATH,
    "duration": round(duration, 6),
    "window_duration": WINDOW_DURATION,
    "stride": STRIDE,
    "num_windows": len(windows),
    "windows": window_results,
    "segments": final_segments,
}
import os
os.makedirs(RESULTS_DIR, exist_ok=True)
json_path = os.path.join(RESULTS_DIR, "temporal_results.json")
with open(json_path, "w") as f:
    json.dump(result_json, f, indent=2)
print(f"\nWrote {json_path}")

# ---------------------------------------------------------------------------
timeline_path = os.path.join(RESULTS_DIR, "temporal_timeline.txt")
with open(timeline_path, "w") as f:
    f.write("RAW WINDOW PREDICTIONS\n\n")
    for wr in window_results:
        bar_len = 20
        f.write(f"{wr['start']:.2f} {'─'*bar_len} {wr['end']:.2f}  {wr['top1']:<22} {wr['top1_score']:.2f}\n")
    f.write("\nFINAL SEGMENTS\n\n")
    for seg in final_segments:
        bar_len = 20
        f.write(f"{seg['start']:.2f} {'─'*bar_len} {seg['end']:.2f}  {seg['action']:<22} {seg['confidence']:.2f}  [{seg['status']}]\n")
print(f"Wrote {timeline_path}")

t_end = time.time()
print("\n>>> PERFORMANCE <<<")
print(f"Model load time: {model_load_time:.2f}s")
print(f"Number of windows: {len(windows)}")
print(f"Average inference time/window: {np.mean(inference_times):.3f}s")
print(f"Total temporal inference time: {total_temporal_inference_time:.2f}s")
print(f"Total wall time: {t_end - t0:.1f}s")
print(f"Peak memory (used) observed: {_peak_used_gb:.2f}GB")
print(f"Swap before inference: {mem_before_inference['swap_used_gb']:.2f}GB")
print(f"Swap after inference: {mem_after_inference['swap_used_gb']:.2f}GB")
print("\nRESULT: XCLIP_TEMPORAL_TEST_PASS")

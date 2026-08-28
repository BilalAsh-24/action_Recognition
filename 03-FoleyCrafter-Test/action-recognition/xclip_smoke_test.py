"""
X-CLIP action-recognition smoke test — Module 2, isolated experiment.

Does NOT import or touch any FoleyCrafter code, environment, or checkpoints.
Uses only: transformers, torch, PIL, numpy, and the system ffmpeg CLI
(video frames only — audio stream is never read).
"""
import subprocess
import sys
import time

import numpy as np
import psutil
import torch
from PIL import Image
from transformers import XCLIPModel, XCLIPProcessor

VIDEO_PATH = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL_ID = "microsoft/xclip-base-patch16-zero-shot"
DEVICE = "mps"

CANDIDATE_LABELS = [
    "someone unlocking a door",
    "someone locking a door",
    "someone turning a key in a door lock",
    "someone opening a door with a key",
    "someone operating a door lock",
    "someone turning a door handle",
    "someone opening a wooden door",
    "someone closing a wooden door",
    "someone manipulating a door latch",
    "a hand operating a door lock",
]

_peak_used_gb = 0.0


def mem_snapshot(label):
    global _peak_used_gb
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    used_gb = vm.used / 1e9
    _peak_used_gb = max(_peak_used_gb, used_gb)
    print(f"=== MEMORY: {label} ===")
    print(f"  used={used_gb:.2f}GB available={vm.available/1e9:.2f}GB percent={vm.percent:.1f}%  swap_used={swap.used/1e9:.2f}GB")
    return {"used_gb": used_gb, "swap_used_gb": swap.used / 1e9}


t0 = time.time()
mem_snapshot("baseline (before model load)")

print("\n>>> Loading XCLIPProcessor + XCLIPModel, moving model to MPS <<<")
processor = XCLIPProcessor.from_pretrained(MODEL_ID)
model = XCLIPModel.from_pretrained(MODEL_ID)
model = model.to(DEVICE)
model.eval()
t_loaded = time.time()
print(f"Model config num_frames: {model.config.vision_config.num_frames}")
mem_after_load = mem_snapshot("after model load (on MPS)")
print(f"Model load time: {t_loaded - t0:.1f}s")

# ---------------------------------------------------------------------------
print("\n>>> Extracting frames from test_video.mp4 via ffmpeg (video only, no audio) <<<")
num_frames_needed = model.config.vision_config.num_frames
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
     "stream=nb_frames,r_frame_rate,width,height,codec_name", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1", VIDEO_PATH],
    capture_output=True, text=True,
)
print(probe.stdout)

# extract all video frames as raw RGB via ffmpeg (no audio stream ever touched)
extract = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", VIDEO_PATH, "-map", "0:v:0",
     "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"],
    capture_output=True,
)
# get resolution to reshape the raw pipe
probe_wh = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
     "-of", "csv=p=0", VIDEO_PATH],
    capture_output=True, text=True,
)
w, h = [int(x) for x in probe_wh.stdout.strip().rstrip(",").split(",")]
frame_bytes = w * h * 3
raw = extract.stdout
total_frames = len(raw) // frame_bytes
all_frames = np.frombuffer(raw, dtype=np.uint8)[: total_frames * frame_bytes].reshape(total_frames, h, w, 3)
print(f"Decoded {total_frames} raw video frames at {w}x{h} (audio stream never read)")

indices = np.linspace(0, total_frames - 1, num_frames_needed, dtype=int)
sampled = [Image.fromarray(all_frames[i]) for i in indices]
print(f"Uniformly sampled {len(sampled)} frames (indices: {list(indices)}) for X-CLIP (expects {num_frames_needed})")

# ---------------------------------------------------------------------------
print("\n>>> STEP 10: ONE X-CLIP classification pass against the 10 candidate labels <<<")
inputs = processor(text=CANDIDATE_LABELS, videos=[sampled], return_tensors="pt", padding=True)
inputs = {k: (v.to(DEVICE) if hasattr(v, "to") else v) for k, v in inputs.items()}

mem_before_inference = mem_snapshot("before inference (pipe about to run)")

t_inf_start = time.time()
with torch.no_grad():
    outputs = model(**inputs)
    logits_per_video = outputs.logits_per_video
    probs = logits_per_video.softmax(dim=1)[0].cpu().numpy()
t_inf_end = time.time()

mem_after_inference = mem_snapshot("after inference (peak)")
print(f"Inference time: {t_inf_end - t_inf_start:.2f}s")

# ---------------------------------------------------------------------------
print("\n>>> RESULTS (sorted highest to lowest) <<<")
ranked = sorted(zip(CANDIDATE_LABELS, probs), key=lambda x: -x[1])
for i, (label, score) in enumerate(ranked, 1):
    print(f"{i}. {label} — {score:.4f}")

t_end = time.time()
print(f"\nTotal wall time: {t_end - t0:.1f}s")
print(f"Peak memory (used) observed: {_peak_used_gb:.2f}GB")
print("\nRESULT: XCLIP_SMOKE_TEST_PASS")

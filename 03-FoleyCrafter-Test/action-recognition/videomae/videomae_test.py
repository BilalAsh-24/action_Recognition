"""
VideoMAE whole-video classification smoke test — Module 2, isolated experiment.

Does NOT import or touch any FoleyCrafter or X-CLIP code/environment/checkpoints.
Uses only: transformers, torch, torchvision, PIL, numpy, psutil, huggingface_hub,
and the system ffmpeg CLI (video frames only — audio stream is never read).

Classification only. No temporal windows. No FoleyCrafter integration.
"""
import subprocess
import time

import numpy as np
import psutil
import torch
from huggingface_hub import snapshot_download
from PIL import Image
from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor

VIDEO_PATH = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL_ID = "MCG-NJU/videomae-base-finetuned-kinetics"
DEVICE = "mps"

_peak_used_gb = 0.0


def mem_snapshot(label):
    global _peak_used_gb
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    used_gb = vm.used / 1e9
    _peak_used_gb = max(_peak_used_gb, used_gb)
    print(f"=== MEMORY: {label} === used={used_gb:.2f}GB available={vm.available/1e9:.2f}GB swap_used={swap.used/1e9:.2f}GB")
    return {"used_gb": used_gb, "swap_used_gb": swap.used / 1e9}


t0 = time.time()
mem_before_load = mem_snapshot("before model download/load")

# ---------------------------------------------------------------------------
print("\n>>> STEP 6: downloading MCG-NJU/videomae-base-finetuned-kinetics (only this model) <<<")
t_dl0 = time.time()
local_path = snapshot_download(MODEL_ID)
t_dl1 = time.time()
download_time = t_dl1 - t_dl0
print(f"Downloaded/resolved to cache: {local_path}")
print(f"Download time: {download_time:.1f}s")

# ---------------------------------------------------------------------------
print("\n>>> STEP 7: loading VideoMAEImageProcessor + VideoMAEForVideoClassification, moving to MPS <<<")
t_ld0 = time.time()
processor = VideoMAEImageProcessor.from_pretrained(MODEL_ID)
model = VideoMAEForVideoClassification.from_pretrained(MODEL_ID)
model = model.to(DEVICE)
model.eval()
t_ld1 = time.time()
load_time = t_ld1 - t_ld0

num_frames_needed = model.config.num_frames
devices_seen = {p.device.type for p in model.parameters()}
print(f"Model config num_frames: {num_frames_needed}")
print(f"Parameter devices observed: {devices_seen}")
assert devices_seen == {"mps"}, f"Not all parameters on MPS! Found: {devices_seen}"
print("Confirmed: all model parameters are on MPS")
mem_after_load = mem_snapshot("after model load (on MPS)")
print(f"Load time: {load_time:.1f}s")

# ---------------------------------------------------------------------------
print("\n>>> STEP 8: extracting VIDEO FRAMES ONLY via ffmpeg -map 0:v:0 (audio never read) <<<")
t_fe0 = time.time()
probe_wh = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
     "-of", "csv=p=0", VIDEO_PATH],
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
print(f"Decoded {total_frames} raw video frames at {w}x{h} (audio stream never read, no -map 0:a used)")

indices = np.linspace(0, total_frames - 1, num_frames_needed, dtype=int)
sampled = [Image.fromarray(all_frames[i]) for i in indices]
t_fe1 = time.time()
frame_extraction_time = t_fe1 - t_fe0
print(f"Uniformly sampled {len(sampled)} frames across the FULL video (indices: {list(indices)})")
print(f"Frame extraction time: {frame_extraction_time:.2f}s")

# ---------------------------------------------------------------------------
print("\n>>> STEP 9: ONE VideoMAE classification inference (native Kinetics-400 label space) <<<")
inputs = processor(sampled, return_tensors="pt")
inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

mem_before_inference = mem_snapshot("before inference")

t_inf0 = time.time()
with torch.no_grad():
    outputs = model(**inputs)
    logits = outputs.logits
    probs = torch.nn.functional.softmax(logits, dim=-1)[0].cpu().numpy()
t_inf1 = time.time()
inference_time = t_inf1 - t_inf0

mem_after_inference = mem_snapshot("after inference (peak)")
print(f"Inference time: {inference_time:.2f}s")

# ---------------------------------------------------------------------------
print("\n>>> TOP 10 KINETICS-400 PREDICTIONS (native model output, not manually corrected) <<<")
top10_idx = np.argsort(-probs)[:10]
for rank, idx in enumerate(top10_idx, 1):
    label = model.config.id2label[idx]
    score = probs[idx]
    print(f"{rank}. {label} — {score:.4f}")

t_end = time.time()
print("\n>>> PERFORMANCE <<<")
print(f"Model download time: {download_time:.1f}s")
print(f"Model load time: {load_time:.1f}s")
print(f"Frame extraction time: {frame_extraction_time:.2f}s")
print(f"Inference time: {inference_time:.2f}s")
print(f"Total runtime: {t_end - t0:.1f}s")
print(f"Peak memory: {_peak_used_gb:.2f}GB")
print(f"Swap before inference: {mem_before_inference['swap_used_gb']:.2f}GB")
print(f"Swap after inference: {mem_after_inference['swap_used_gb']:.2f}GB")
print("\nRESULT: VIDEOMAE_TEST_PASS")

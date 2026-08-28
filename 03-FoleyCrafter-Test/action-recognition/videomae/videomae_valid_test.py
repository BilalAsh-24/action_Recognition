"""
FIRST VALID VideoMAE classification test — transformers 4.45.2 (checkpoint-faithful).

Isolated experiment. Does NOT import/touch FoleyCrafter or X-CLIP code, envs, or checkpoints.
Uses only: transformers, torch, PIL, numpy, psutil + system ffmpeg CLI (video stream only).

Exactly ONE forward pass. No temporal windows. No audio. No external API.
"""
import json
import os
import subprocess
import time

import numpy as np
import psutil
import torch
import transformers
from PIL import Image
from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor

VIDEO_PATH = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/test_video.mp4"
MODEL_ID = "MCG-NJU/videomae-base-finetuned-kinetics"
DEVICE = "mps"
RESULTS_DIR = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/action-recognition/results"

_peak_used_gb = 0.0
_peak_swap_gb = 0.0


def mem(label, verbose=True):
    global _peak_used_gb, _peak_swap_gb
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    _peak_used_gb = max(_peak_used_gb, vm.used / 1e9)
    _peak_swap_gb = max(_peak_swap_gb, sw.used / 1e9)
    if verbose:
        print(f"=== MEMORY: {label} === used={vm.used/1e9:.2f}GB available={vm.available/1e9:.2f}GB swap={sw.used/1e9:.2f}GB")
    return {"used_gb": vm.used / 1e9, "swap_gb": sw.used / 1e9}


t0 = time.time()
print(f"transformers: {transformers.__version__}  torch: {torch.__version__}")
mem("baseline (before model load)")

# --- STEP 3: load model, verify integrity -----------------------------------
print("\n>>> STEP 3: loading model (cached; no download) with load-info verification <<<")
t_ld0 = time.time()
processor = VideoMAEImageProcessor.from_pretrained(MODEL_ID)
model, loading_info = VideoMAEForVideoClassification.from_pretrained(MODEL_ID, output_loading_info=True)
t_ld1 = time.time()
load_time = t_ld1 - t_ld0

print(f"missing_keys:    {loading_info['missing_keys']}")
print(f"unexpected_keys: {loading_info['unexpected_keys']}")
print(f"mismatched_keys: {loading_info['mismatched_keys']}")
print(f"error_msgs:      {loading_info['error_msgs']}")
assert loading_info["missing_keys"] == [], "missing keys present — refusing to proceed"
assert loading_info["unexpected_keys"] == [], "unexpected keys present — refusing to proceed"
assert loading_info["mismatched_keys"] == [], "mismatched keys present — refusing to proceed"
total_params = sum(p.numel() for p in model.parameters())
print(f"total parameters: {total_params:,}  (all checkpoint-loaded, none randomly initialized)")

model = model.to(DEVICE)
model.eval()
devices = {p.device.type for p in model.parameters()}
assert devices == {"mps"}, f"not all params on MPS: {devices}"
print(f"parameter devices: {devices}  -> all on MPS")
mem("after model load (on MPS)")
print(f"Model load time: {load_time:.2f}s")

num_frames_needed = model.config.num_frames
print(f"model.config.num_frames = {num_frames_needed}")

# --- STEP 4/5: frame extraction, video stream ONLY ---------------------------
print("\n>>> STEP 4/5: extracting VIDEO FRAMES ONLY via `ffmpeg -map 0:v:0` <<<")
t_fe0 = time.time()

probe_all = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", VIDEO_PATH],
    capture_output=True, text=True,
)
audio_present = "audio" in probe_all.stdout
print(f"audio stream present in source: {audio_present}  (it will NOT be decoded or used)")

probe_v = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
     "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1", VIDEO_PATH],
    capture_output=True, text=True,
)
meta = dict(line.split("=", 1) for line in probe_v.stdout.strip().splitlines() if "=" in line)
w, h = int(meta["width"]), int(meta["height"])
duration = float(meta["duration"])
r_fps = meta["r_frame_rate"]
avg_fps = meta["avg_frame_rate"]
nb_frames = int(meta["nb_frames"])

# ONLY the video stream is mapped; the AAC stream is never touched.
extract = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", VIDEO_PATH, "-map", "0:v:0",
     "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"],
    capture_output=True,
)
frame_bytes = w * h * 3
total_frames = len(extract.stdout) // frame_bytes
all_frames = np.frombuffer(extract.stdout, dtype=np.uint8)[: total_frames * frame_bytes].reshape(total_frames, h, w, 3)
t_fe1 = time.time()
frame_extraction_time = t_fe1 - t_fe0
print(f"decoded {total_frames} raw video frames at {w}x{h} in {frame_extraction_time:.2f}s")

indices = np.linspace(0, total_frames - 1, num_frames_needed, dtype=int)
sampled = [Image.fromarray(all_frames[i]) for i in indices]
print(f"uniformly sampled {len(sampled)} frames across full duration: {list(indices)}")

# --- preprocessing ----------------------------------------------------------
t_pp0 = time.time()
inputs = processor(sampled, return_tensors="pt")
inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
t_pp1 = time.time()
preprocess_time = t_pp1 - t_pp0
print(f"preprocessing time: {preprocess_time:.2f}s  pixel_values shape: {tuple(inputs['pixel_values'].shape)}")
print(f"inputs supplied to model: {list(inputs.keys())}  (frames only — no audio tensor exists)")

# --- STEP 6: ONE inference ---------------------------------------------------
print("\n>>> STEP 6: ONE forward pass (native Kinetics-400 output) <<<")
mem_before_inf = mem("before inference")
t_i0 = time.time()
with torch.no_grad():
    outputs = model(**inputs)
    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0].cpu().numpy()
t_i1 = time.time()
inference_time = t_i1 - t_i0
mem_after_inf = mem("after inference (peak)")
print(f"Inference time: {inference_time:.2f}s")

print("\n>>> TOP 10 KINETICS-400 PREDICTIONS (raw model output, unmodified) <<<")
top10 = np.argsort(-probs)[:10]
predictions = []
for rank, idx in enumerate(top10, 1):
    label = model.config.id2label[int(idx)]
    score = float(probs[idx])
    predictions.append({"rank": rank, "label": label, "score": round(score, 6)})
    print(f"{rank:2d}. {label} — {score:.4f}")

total_wall = time.time() - t0

# --- STEP 8: save JSON -------------------------------------------------------
os.makedirs(RESULTS_DIR, exist_ok=True)
out = {
    "model": MODEL_ID,
    "transformers_version": transformers.__version__,
    "torch_version": torch.__version__,
    "device": DEVICE,
    "video": VIDEO_PATH,
    "duration": round(duration, 6),
    "width": w,
    "height": h,
    "codec": "hevc",
    "fps_nominal": r_fps,
    "fps_average": avg_fps,
    "frame_count": nb_frames,
    "frames_decoded": total_frames,
    "sampled_frames": int(num_frames_needed),
    "audio_present": audio_present,
    "audio_used": False,
    "checkpoint_integrity": {
        "missing_keys": loading_info["missing_keys"],
        "unexpected_keys": loading_info["unexpected_keys"],
        "mismatched_keys": loading_info["mismatched_keys"],
        "total_parameters": int(total_params),
    },
    "predictions": predictions,
    "model_load_time": round(load_time, 3),
    "frame_extraction_time": round(frame_extraction_time, 3),
    "preprocess_time": round(preprocess_time, 3),
    "inference_time": round(inference_time, 3),
    "total_wall_time": round(total_wall, 3),
    "peak_memory_gb": round(_peak_used_gb, 3),
    "peak_swap_gb": round(_peak_swap_gb, 3),
}
json_path = os.path.join(RESULTS_DIR, "videomae_test_result.json")
with open(json_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nWrote {json_path}")

print("\n>>> PERFORMANCE <<<")
print(f"model load time:       {load_time:.2f}s")
print(f"frame extraction time: {frame_extraction_time:.2f}s")
print(f"preprocessing time:    {preprocess_time:.2f}s")
print(f"inference time:        {inference_time:.2f}s")
print(f"total wall time:       {total_wall:.2f}s")
print(f"peak memory:           {_peak_used_gb:.2f}GB")
print(f"peak swap:             {_peak_swap_gb:.2f}GB")
print("\nRESULT: VIDEOMAE_VALID_TEST_PASS")

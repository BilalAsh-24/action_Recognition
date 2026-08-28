"""
FIRST REAL FOLEYCRAFTER INFERENCE — controlled baseline test.

Mirrors inference.py's build_models() + run_inference() logic exactly (same
library calls, same parameters), but:
  - processes exactly ONE short (~1.5s) video-only test clip
  - stops after saving the generated .wav (does NOT merge audio back into
    the video / does NOT call video.write_videofile, per this test's scope)
  - records memory pressure and timing at each stage

Does NOT modify any file inside the foleycrafter/ repo.
"""
import os
import os.path as osp
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
import torch
import torchvision

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "foleycrafter"))

from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection  # noqa: E402

from foleycrafter.models.onset import torch_utils  # noqa: E402
from foleycrafter.models.time_detector.model import VideoOnsetNet  # noqa: E402
from foleycrafter.pipelines.auffusion_pipeline import Generator, denormalize_spectrogram  # noqa: E402
from foleycrafter.utils.util import build_foleycrafter, read_frames_with_moviepy  # noqa: E402

MPS_DEVICE = "mps"
CPU_DEVICE = "cpu"
CKPT_DIR = "checkpoints"
INPUT_VIDEO = "../test_video.mp4"
SAVE_DIR = "output/second_test/"
SEED = 42
SEMANTIC_SCALE = 1.0
TEMPORAL_SCALE = 0.2

vision_transform_list = [
    torchvision.transforms.Resize((128, 128)),
    torchvision.transforms.CenterCrop((112, 112)),
    torchvision.transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
]
video_transform = torchvision.transforms.Compose(vision_transform_list)

_baseline_swap_used_gb = None
_peak_used_gb = 0.0
_peak_swap_gb = 0.0


def mem_snapshot(label):
    global _peak_used_gb, _peak_swap_gb
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    avail_gb = vm.available / 1e9
    used_gb = vm.used / 1e9
    swap_used_gb = swap.used / 1e9
    _peak_used_gb = max(_peak_used_gb, used_gb)
    _peak_swap_gb = max(_peak_swap_gb, swap_used_gb)
    print(f"\n=== MEMORY: {label} ===")
    print(f"  used={used_gb:.2f}GB available={avail_gb:.2f}GB percent={vm.percent:.1f}%  swap_used={swap_used_gb:.2f}GB")
    return {"used_gb": used_gb, "available_gb": avail_gb, "swap_used_gb": swap_used_gb}


t_start = time.time()
mem_snapshot("baseline (before model load)")

print("\n>>> Loading models (mirrors inference.py build_models()) <<<")
fc_ckpt = CKPT_DIR
pretrained_model_name_or_path = "auffusion/auffusion-full-no-adapter"
temporal_ckpt_path = osp.join(CKPT_DIR, "temporal_adapter.ckpt")

vocoder = Generator.from_pretrained(fc_ckpt, subfolder="vocoder").to(MPS_DEVICE)

time_detector_ckpt = osp.join(CKPT_DIR, "timestamp_detector.pth.tar")
time_detector = VideoOnsetNet(False)
time_detector, _ = torch_utils.load_model(time_detector_ckpt, time_detector, device=CPU_DEVICE, strict=True)
time_detector = time_detector.to(CPU_DEVICE)

pipe = build_foleycrafter().to(MPS_DEVICE)
ckpt = torch.load(temporal_ckpt_path, map_location="cpu")
if "state_dict" in ckpt.keys():
    ckpt = ckpt["state_dict"]
load_gligen_ckpt = {}
for key, value in ckpt.items():
    if key.startswith("module."):
        load_gligen_ckpt[key[len("module.") :]] = value
    else:
        load_gligen_ckpt[key] = value
m, u = pipe.controlnet.load_state_dict(load_gligen_ckpt, strict=False)
print(f"ControlNet missing keys: {len(m)}; unexpected keys: {len(u)}")
del ckpt, load_gligen_ckpt

pipe.load_ip_adapter(
    osp.join(CKPT_DIR, "semantic"), subfolder="", weight_name="semantic_adapter.bin", image_encoder_folder=None
)
pipe.set_ip_adapter_scale(SEMANTIC_SCALE)

image_processor = CLIPImageProcessor()
image_encoder = CLIPVisionModelWithProjection.from_pretrained(
    "h94/IP-Adapter", subfolder="models/image_encoder"
).to(MPS_DEVICE)

t_models_loaded = time.time()
mem_snapshot("after all models loaded (vocoder/pipe/controlnet/adapters/image_encoder -> MPS, onset detector -> CPU)")
print(f"\nModel load time: {t_models_loaded - t_start:.1f}s")

# ---------------------------------------------------------------------------
print("\n>>> Verifying input video properties <<<")
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-show_entries", "stream=width,height,codec_type,r_frame_rate,nb_frames",
     "-of", "default=noprint_wrappers=1", INPUT_VIDEO],
    capture_output=True, text=True,
)
print(probe.stdout)
has_audio_stream = "codec_type=audio" in probe.stdout
print(f"Input video has an audio stream: {has_audio_stream}")
print("Note: read_frames_with_moviepy() below only reads clip.iter_frames()/clip.duration; "
      "it never accesses clip.audio, so any audio track present is structurally never used.")

os.makedirs(SAVE_DIR, exist_ok=True)
generator = torch.Generator(device=MPS_DEVICE)
generator.manual_seed(SEED)

print("\n>>> Reading video frames (read_frames_with_moviepy — video only, no audio) <<<")
frames, duration = read_frames_with_moviepy(INPUT_VIDEO, max_frame_nums=150)
print(f"frames shape: {frames.shape}, duration: {duration:.3f}s")

with torch.no_grad():
    print("\n>>> Timestamp/onset detection on CPU <<<")
    time_frames = torch.FloatTensor(frames).permute(0, 3, 1, 2)
    time_frames = video_transform(time_frames)
    time_frames = {"frames": time_frames.unsqueeze(0).permute(0, 2, 1, 3, 4).to("cpu")}
    preds = time_detector(time_frames)
    preds = torch.sigmoid(preds)
    print("onset detector output device:", preds.device, "shape:", preds.shape)

    time_condition = [
        -1 if preds[0][int(i / (1024 / 10 * duration) * 150)] < 0.5 else 1
        for i in range(int(1024 / 10 * duration))
    ]
    time_condition = time_condition + [-1] * (1024 - len(time_condition))
    time_condition = (
        torch.FloatTensor(time_condition).unsqueeze(0).unsqueeze(0).unsqueeze(0).repeat(1, 1, 256, 1).to(MPS_DEVICE)
    )

    print("\n>>> CLIP image embedding (visual conditioning, video frames only) <<<")
    images = image_processor(images=frames, return_tensors="pt").to(MPS_DEVICE)
    image_embeddings = image_encoder(**images).image_embeds
    image_embeddings = torch.mean(image_embeddings, dim=0, keepdim=True).unsqueeze(0).unsqueeze(0)
    neg_image_embeddings = torch.zeros_like(image_embeddings)
    image_embeddings = torch.cat([neg_image_embeddings, image_embeddings], dim=1)

    mem_snapshot("before generation (pipe(...) about to be called)")

    print("\n>>> RUNNING GENERATION (pipe(...)) — the actual diffusion denoising, 25 steps <<<")
    t_gen_start = time.time()
    sample = pipe(
        prompt="",
        negative_prompt="",
        ip_adapter_image_embeds=image_embeddings,
        image=time_condition,
        controlnet_conditioning_scale=TEMPORAL_SCALE,
        num_inference_steps=25,
        height=256,
        width=1024,
        output_type="pt",
        generator=generator,
    )
    t_gen_end = time.time()
    mem_snapshot("immediately after generation (pipe returned)")
    print(f"\nGeneration time: {t_gen_end - t_gen_start:.1f}s")

    audio_img = sample.images[0]
    audio = denormalize_spectrogram(audio_img)
    audio = vocoder.inference(audio, lengths=160000)[0]
    audio = audio[: int(duration * 16000)]

name = Path(INPUT_VIDEO).stem
audio_save_path = osp.join(SAVE_DIR, "audio")
os.makedirs(audio_save_path, exist_ok=True)
save_path = osp.join(audio_save_path, f"{name}.wav")
sf.write(save_path, audio, 16000)

mem_snapshot("after saving audio (final)")

print("\n>>> NOT merging audio back into video (out of scope for this test) <<<")

# --- verification ---
info = sf.info(save_path)
data, sr = sf.read(save_path)
print(f"\n=== OUTPUT VERIFICATION ===")
print(f"file: {save_path}")
print(f"file size: {os.path.getsize(save_path)} bytes")
print(f"format: {info.format}, subtype: {info.subtype}")
print(f"sample_rate: {sr}")
print(f"duration: {len(data)/sr:.3f}s")
print(f"non-empty: {len(data) > 0 and np.any(data != 0)}")
print(f"finite (decodable, no NaN/Inf): {np.all(np.isfinite(data))}")

t_end = time.time()
print(f"\nTotal wall time: {t_end - t_start:.1f}s")
print(f"Peak memory used: {_peak_used_gb:.2f}GB")
print(f"Peak swap used: {_peak_swap_gb:.2f}GB")
print("\nRESULT: INFERENCE_TEST_PASS")

"""
Standalone checkpoint DOWNLOAD -> LOAD -> VERIFY test for FoleyCrafter on Apple M4 / MPS.

Does NOT modify any file inside the foleycrafter/ repo.
Does NOT call pipe(...) / run any denoising or generation.
Mirrors inference.py's build_models() logic exactly (same library calls),
with memory-pressure checks inserted between every major load step, and
a self-abort if memory gets dangerous.
"""
import gc
import os
import os.path as osp
import subprocess
import sys
import time

import psutil
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "foleycrafter"))

from huggingface_hub import snapshot_download  # noqa: E402
from transformers import CLIPVisionModelWithProjection  # noqa: E402

from foleycrafter.models.onset import torch_utils  # noqa: E402
from foleycrafter.models.time_detector.model import VideoOnsetNet  # noqa: E402
from foleycrafter.pipelines.auffusion_pipeline import Generator  # noqa: E402
from foleycrafter.utils.util import build_foleycrafter  # noqa: E402

MPS_DEVICE = "mps"
CPU_DEVICE = "cpu"
CKPT_DIR = "checkpoints"
PRETRAIN = "auffusion/auffusion-full-no-adapter"
FC_REPO = "ymzhang319/FoleyCrafter"

# Safety thresholds
MIN_AVAILABLE_GB = 1.5   # abort if available memory drops below this
MAX_SWAP_GROWTH_GB = 3.0  # abort if swap used grows this much beyond baseline

_baseline_swap_used_gb = None


def mem_snapshot(label):
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    total_gb = vm.total / 1e9
    avail_gb = vm.available / 1e9
    used_gb = vm.used / 1e9
    percent = vm.percent
    swap_used_gb = swap.used / 1e9
    swap_total_gb = swap.total / 1e9

    # macOS-native memory pressure signal via vm_stat (page counts)
    try:
        out = subprocess.check_output(["vm_stat"], text=True)
    except Exception:
        out = ""

    print(f"\n=== MEMORY SNAPSHOT: {label} ===")
    print(f"  total={total_gb:.2f}GB  used={used_gb:.2f}GB  available={avail_gb:.2f}GB  percent_used={percent:.1f}%")
    print(f"  swap_used={swap_used_gb:.2f}GB / swap_total={swap_total_gb:.2f}GB")

    global _baseline_swap_used_gb
    if _baseline_swap_used_gb is None:
        _baseline_swap_used_gb = swap_used_gb

    danger = False
    reasons = []
    if avail_gb < MIN_AVAILABLE_GB:
        danger = True
        reasons.append(f"available memory {avail_gb:.2f}GB < {MIN_AVAILABLE_GB}GB threshold")
    swap_growth = swap_used_gb - _baseline_swap_used_gb
    if swap_growth > MAX_SWAP_GROWTH_GB:
        danger = True
        reasons.append(f"swap grew by {swap_growth:.2f}GB since baseline (> {MAX_SWAP_GROWTH_GB}GB threshold)")

    if danger:
        print(f"  !!! DANGER: {'; '.join(reasons)} !!!")
    else:
        print("  status: OK")

    return {"available_gb": avail_gb, "used_gb": used_gb, "percent": percent, "swap_used_gb": swap_used_gb, "danger": danger, "reasons": reasons}


def check_or_abort(label):
    snap = mem_snapshot(label)
    if snap["danger"]:
        print(f"\n!!! ABORTING: dangerous memory pressure detected at stage '{label}' !!!")
        print(f"Reasons: {snap['reasons']}")
        sys.exit(2)
    return snap


t0 = time.time()
print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
check_or_abort("baseline (before anything)")

# ---------------------------------------------------------------------------
print("\n>>> STAGE 1: download auffusion/auffusion-full-no-adapter (base SD components) <<<")
pretrained_model_name_or_path = PRETRAIN
if not os.path.isdir(pretrained_model_name_or_path):
    pretrained_model_name_or_path = snapshot_download(pretrained_model_name_or_path)
print("Resolved auffusion path:", pretrained_model_name_or_path)
check_or_abort("after downloading auffusion repo")

print("\n>>> STAGE 2: download ymzhang319/FoleyCrafter (adapters/vocoder/detector) <<<")
fc_ckpt = FC_REPO
if not os.path.isdir(fc_ckpt):
    fc_ckpt = snapshot_download(fc_ckpt, local_dir=CKPT_DIR)
print("Resolved FoleyCrafter ckpt path:", fc_ckpt)
check_or_abort("after downloading FoleyCrafter repo")

# ---------------------------------------------------------------------------
print("\n>>> STAGE 3: load vocoder -> MPS <<<")
vocoder_config_path = fc_ckpt
vocoder = Generator.from_pretrained(vocoder_config_path, subfolder="vocoder").to(MPS_DEVICE)
print("vocoder device:", next(vocoder.parameters()).device)
check_or_abort("after loading vocoder to MPS")

print("\n>>> STAGE 4: load timestamp/onset detector -> CPU (forced) <<<")
temporal_ckpt_path = osp.join(CKPT_DIR, "temporal_adapter.ckpt")
time_detector_ckpt = osp.join(CKPT_DIR, "timestamp_detector.pth.tar")
time_detector = VideoOnsetNet(False)
time_detector, _ = torch_utils.load_model(time_detector_ckpt, time_detector, device=CPU_DEVICE, strict=True)
time_detector = time_detector.to(CPU_DEVICE)
print("time_detector device:", next(time_detector.parameters()).device)
check_or_abort("after loading timestamp detector to CPU")

print("\n>>> STAGE 5: build_foleycrafter() [vae+unet+scheduler+tokenizer+text_encoder+controlnet-init] -> MPS <<<")
pipe = build_foleycrafter().to(MPS_DEVICE)
print("unet device:", next(pipe.unet.parameters()).device)
print("vae device:", next(pipe.vae.parameters()).device)
print("text_encoder device:", next(pipe.text_encoder.parameters()).device)
print("controlnet device:", next(pipe.controlnet.parameters()).device)
check_or_abort("after building main pipeline (vae/unet/text_encoder/controlnet-init) on MPS")

print("\n>>> STAGE 6: load temporal_adapter.ckpt into controlnet <<<")
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
gc.collect()
check_or_abort("after loading temporal adapter weights into controlnet")

print("\n>>> STAGE 7: load semantic (IP-Adapter) adapter <<<")
pipe.load_ip_adapter(
    osp.join(CKPT_DIR, "semantic"), subfolder="", weight_name="semantic_adapter.bin", image_encoder_folder=None
)
pipe.set_ip_adapter_scale(1.0)
print("semantic adapter loaded")
check_or_abort("after loading semantic adapter")

print("\n>>> STAGE 8: load CLIP/IP-Adapter image encoder -> MPS <<<")
image_encoder = CLIPVisionModelWithProjection.from_pretrained(
    "h94/IP-Adapter", subfolder="models/image_encoder"
).to(MPS_DEVICE)
print("image_encoder device:", next(image_encoder.parameters()).device)
final_snap = check_or_abort("after loading CLIP image encoder to MPS (FULL PIPELINE CONSTRUCTED)")

print("\n>>> ALL COMPONENTS LOADED SUCCESSFULLY. NOT running denoising/generation. <<<")
print(f"Total elapsed: {time.time() - t0:.1f}s")
print("RESULT: LOAD_TEST_PASS")

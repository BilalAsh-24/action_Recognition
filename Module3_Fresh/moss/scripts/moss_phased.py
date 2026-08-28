"""Phase-separated component loaders for MOSS-SoundEffect v2.0 on Apple MPS.

The official MOSS repository is NOT modified. This wrapper reproduces the exact
component-construction sequence of
`diffsynth.pipelines.wan_audio.WanAudioPipeline.from_pretrained`, with two
deliberate differences:

  1. The DiT and the DAC VAE are cast to bfloat16 after loading. Upstream leaves
     both in float32 because `torch_dtype` is only forwarded to the Qwen3 text
     encoder. This costs no precision at inference: `MossSoundEffectPipeline.__call__`
     already wraps the whole engine call in
     `torch.autocast(device_type, dtype=torch.bfloat16)`, so the forward pass
     computes in bfloat16 either way — float32 storage merely doubles resident
     memory.

  2. Components are constructed and released independently, so CLIP-scale peaks
     never overlap.

No fp16. No CUDA. Device is always passed explicitly ("mps"), never "auto" —
upstream's `_normalize_device("auto")` falls back to CPU, not MPS.
"""
from __future__ import annotations

import gc
import json
import os
import threading
import time
from pathlib import Path

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

import psutil
import torch

ROOT = Path(__file__).resolve().parents[2]                 # Module3_Fresh/
CKPT = ROOT / "moss" / "checkpoints" / "MOSS-SoundEffect-v2.0"

DEVICE = "mps"
DTYPE = torch.bfloat16
FORBIDDEN_DTYPES = (torch.float16,)

# Successful Hugging Face Space configuration — reproduced verbatim, not tuned.
PROMPT = ("close-up realistic Foley of a person taking several natural sips of water from a "
          "ceramic mug, distinct sipping sounds followed by natural swallowing, subtle "
          "cup-to-lips contact and realistic ceramic handling, continuous recognizable "
          "drinking action, isolated Foley recording, no speech, no music, no ambience")
NEGATIVE = ""
SECONDS = 10
NUM_INFERENCE_STEPS = 50
CFG_SCALE = 4
SIGMA_SHIFT = 5
SEED = 42
SAMPLE_RATE = 48000
NUM_CHANNELS = 1


# --------------------------------------------------------------------------- memory
def snapshot() -> dict:
    v, s = psutil.virtual_memory(), psutil.swap_memory()
    d = {"used_gb": round(v.used / 1e9, 3),
         "available_gb": round(v.available / 1e9, 3),
         "swap_gb": round(s.used / 1e9, 3)}
    if torch.backends.mps.is_available():
        d["mps_alloc_gb"] = round(torch.mps.current_allocated_memory() / 1e9, 3)
        d["mps_driver_gb"] = round(torch.mps.driver_allocated_memory() / 1e9, 3)
    return d


class MemoryTracker(threading.Thread):
    """Samples system memory every 50 ms and records peaks."""

    def __init__(self, abort_available_gb: float = 1.5, interval: float = 0.05):
        super().__init__(daemon=True)
        self.abort_available_gb = abort_available_gb
        self.interval = interval
        self._stop_evt = threading.Event()
        base = snapshot()
        self.baseline = base
        self.peak_used_gb = base["used_gb"]
        self.min_available_gb = base["available_gb"]
        self.peak_swap_gb = base["swap_gb"]
        self.peak_mps_driver_gb = base.get("mps_driver_gb", 0.0)
        self.breach: str | None = None

    def run(self):
        while not self._stop_evt.is_set():
            s = snapshot()
            self.peak_used_gb = max(self.peak_used_gb, s["used_gb"])
            self.min_available_gb = min(self.min_available_gb, s["available_gb"])
            self.peak_swap_gb = max(self.peak_swap_gb, s["swap_gb"])
            self.peak_mps_driver_gb = max(self.peak_mps_driver_gb, s.get("mps_driver_gb", 0.0))
            if self.breach is None and s["available_gb"] < self.abort_available_gb:
                self.breach = (f"available {s['available_gb']:.2f} GB < "
                               f"{self.abort_available_gb} GB")
            time.sleep(self.interval)

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=2)

    def report(self) -> dict:
        return {"baseline": self.baseline,
                "peak_used_gb": round(self.peak_used_gb, 3),
                "min_available_gb": round(self.min_available_gb, 3),
                "peak_swap_gb": round(self.peak_swap_gb, 3),
                "peak_mps_driver_gb": round(self.peak_mps_driver_gb, 3),
                "swap_growth_gb": round(self.peak_swap_gb - self.baseline["swap_gb"], 3),
                "used_growth_gb": round(self.peak_used_gb - self.baseline["used_gb"], 3),
                "abort_threshold_gb": self.abort_available_gb,
                "breach": self.breach}


def sweep():
    """Release freed tensors back to the OS."""
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
        torch.mps.synchronize()
    gc.collect()


def live_instances(*classes) -> dict:
    """Count reachable instances — residency proof after deletion."""
    return {c.__name__: sum(1 for o in gc.get_objects() if type(o) is c) for c in classes}


def cast_params_only(module, device: str, dtype):
    """Move to `device` and cast **parameters** to `dtype`, leaving buffers alone.

    Buffers must not be blanket-cast: the DiT carries three complex128 RoPE
    tables (`freqs_cis_0/1/2`). A plain `.to(dtype=bfloat16)` silently discards
    their imaginary part ("Casting complex values to real discards the imaginary
    part") and destroys rotary position encoding. Upstream keeps them complex128
    on MPS, so we do too.
    """
    # complex128 buffers: MPS has no ComplexDouble support — moving is sometimes
    # tolerated but any op (e.g. torch.cat in model_fn_wan_video) raises
    # "Trying to convert ComplexDouble to the MPS backend". Downcast to complex64.
    # This is lossless *in use*: rope_apply only reads freqs.real / freqs.imag and
    # casts both to float32, so complex64 reproduces them bit-for-bit (verified,
    # max abs diff 0.0). Buffers of other dtypes are left untouched.
    converted = []
    if device == "mps":
        for bname, buf in list(module.named_buffers()):
            if buf.dtype == torch.complex128:
                owner, parts = module, bname.split(".")
                for part in parts[:-1]:
                    owner = getattr(owner, part)
                setattr(owner, parts[-1], buf.to(torch.complex64))
                converted.append(bname)
    module.to(device=device)
    for p in module.parameters():
        p.data = p.data.to(dtype)
    module._complex128_downcast = converted
    return module


def describe(module, name: str, expect_dtype=DTYPE, expect_device=DEVICE) -> dict:
    pdt, bdt, devs, n = set(), set(), set(), 0
    for p in module.parameters():
        pdt.add(p.dtype); devs.add(p.device.type); n += p.numel()
    for b in module.buffers():
        bdt.add(b.dtype); devs.add(b.device.type)
    bad = [str(d) for d in (pdt | bdt) if d in FORBIDDEN_DTYPES]
    assert not bad, f"{name}: forbidden dtype {bad}"
    pfloat = {d for d in pdt if d.is_floating_point}
    nbytes = (sum(p.numel() * p.element_size() for p in module.parameters())
              + sum(b.numel() * b.element_size() for b in module.buffers()))
    return {"name": name, "params_M": round(n / 1e6, 2),
            "bytes_gb": round(nbytes / 1e9, 3),
            "param_dtypes": sorted(str(d) for d in pdt),
            "buffer_dtypes": sorted(str(d) for d in bdt),
            "complex_buffers_preserved": any(d.is_complex for d in bdt),
            "devices": sorted(devs),
            "dtype_ok": pfloat <= {expect_dtype},
            "device_ok": devs <= {expect_device}}


# --------------------------------------------------------------------------- loaders
def _paths(ckpt: Path = CKPT):
    return {"te": ckpt / "text_encoder", "tok": ckpt / "tokenizer",
            "vae": ckpt / "vae" / "vae_128d_48k.pth",
            "dit_w": ckpt / "transformer" / "diffusion_pytorch_model.safetensors",
            "dit_c": ckpt / "transformer" / "config.json",
            "sched": ckpt / "scheduler" / "scheduler_config.json",
            "index": ckpt / "model_index.json"}


def load_text_encoder(ckpt: Path = CKPT, device: str = DEVICE, dtype=DTYPE):
    """PHASE 1 component. Qwen3 already honours torch_dtype upstream."""
    from moss_soundeffect_v2.diffsynth.models.qwen3_text_encoder import Qwen3TextEncoder
    from moss_soundeffect_v2.diffsynth.prompters import WanPrompter
    p = _paths(ckpt)
    te = Qwen3TextEncoder(str(p["te"]), torch_dtype=dtype).to(device)
    prompter = WanPrompter(tokenizer_path=str(p["tok"]))
    prompter.fetch_models(te)
    return te, prompter


def load_dit(ckpt: Path = CKPT, device: str = DEVICE, dtype=DTYPE):
    """PHASE 2 component. Cast to bfloat16 (upstream leaves it float32)."""
    from safetensors.torch import load_file
    from moss_soundeffect_v2.diffsynth.models.wan_audio_dit import WanAudioModel
    from moss_soundeffect_v2.diffsynth.pipelines.wan_audio import _convert_hf_dit_state_dict
    p = _paths(ckpt)
    cfg = json.loads(p["dit_c"].read_text())
    sd = _convert_hf_dit_state_dict(load_file(str(p["dit_w"])))
    dit = WanAudioModel(
        in_dim=cfg["in_dim"], out_dim=cfg["out_dim"], text_dim=cfg["text_dim"],
        freq_dim=cfg["freq_dim"], eps=cfg["eps"], patch_size=tuple(cfg["patch_size"]),
        has_image_input=cfg["has_image_input"], dim=cfg["dim"], ffn_dim=cfg["ffn_dim"],
        num_heads=cfg["num_heads"], num_layers=cfg["num_layers"],
        vae_type=cfg.get("vae_type", "dac"))
    res = dit.load_state_dict(sd)
    assert not res.missing_keys and not res.unexpected_keys, \
        f"DiT load mismatch: missing={len(res.missing_keys)} unexpected={len(res.unexpected_keys)}"
    del sd
    dit = cast_params_only(dit, device, dtype).eval()   # params -> bf16, buffers preserved
    return dit, cfg


def load_vae(ckpt: Path = CKPT, device: str = DEVICE, dtype=DTYPE):
    """PHASE 3 component. Cast to bfloat16 (upstream leaves it float32)."""
    from moss_soundeffect_v2.diffsynth.models.dac_vae import DAC
    p = _paths(ckpt)
    vae = DAC.load(str(p["vae"]))
    vae = cast_params_only(vae, device, dtype).eval()   # params -> bf16, buffers preserved
    return vae


def build_engine_shell(ckpt: Path = CKPT, device: str = DEVICE, dtype=DTYPE):
    """A WanAudioPipeline with scheduler/units but no heavy components attached."""
    from moss_soundeffect_v2.diffsynth.pipelines.wan_audio import WanAudioPipeline
    p = _paths(ckpt)
    shift = json.loads(p["sched"].read_text()).get("shift", 5.0)
    return WanAudioPipeline(device=device, torch_dtype=dtype,
                            tokenizer_path=str(p["tok"]), flow_shift=shift)

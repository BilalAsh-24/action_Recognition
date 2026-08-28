"""Wrapper-level MPS compatibility shims for MOSS-SoundEffect v2.0.

The MOSS repository is NOT modified. These shims replace module attributes at
runtime, in our own process only.

Problem
-------
`diffsynth/models/wan_video_dit.py::sinusoidal_embedding_1d` (and the identical
copy in `wan_audio_dit.py`) computes the timestep embedding in float64:

    sinusoid = torch.outer(position.type(torch.float64), torch.pow(
        10000, -torch.arange(dim//2, dtype=torch.float64, device=position.device)...))

MPS has no float64 support, so on Apple Silicon this raises:

    TypeError: Cannot convert a MPS Tensor to float64 dtype as the MPS framework
    doesn't support float64. Please use float32 instead.

Fix
---
Run the *same* float64 arithmetic on CPU and move the result back to the input's
device. This is numerically identical to upstream — no precision is lost and no
approximation is introduced; only the execution device for a tiny
(1 x freq_dim) tensor changes. Per-call cost is negligible.
"""
from __future__ import annotations

import torch


def sinusoidal_embedding_1d_cpu_f64(dim, position):
    """Upstream `sinusoidal_embedding_1d`, with the float64 math run on CPU."""
    device, out_dtype = position.device, position.dtype
    # two steps: move to CPU first, THEN cast — a fused .to("cpu", float64)
    # still attempts the float64 conversion on the MPS device and raises.
    pos = position.detach().cpu().to(torch.float64)
    freqs = torch.pow(
        torch.tensor(10000.0, dtype=torch.float64),
        -torch.arange(dim // 2, dtype=torch.float64).div(dim // 2),
    )
    sinusoid = torch.outer(pos, freqs)
    x = torch.cat([torch.cos(sinusoid), torch.sin(sinusoid)], dim=1)
    return x.to(device=device, dtype=out_dtype)


def apply(verbose: bool = True) -> list[str]:
    """Patch every module that exposes `sinusoidal_embedding_1d`. Returns names patched."""
    import importlib

    patched = []
    for mod_name in ("moss_soundeffect_v2.diffsynth.models.wan_video_dit",
                     "moss_soundeffect_v2.diffsynth.models.wan_audio_dit",
                     "moss_soundeffect_v2.diffsynth.pipelines.wan_audio"):
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        if hasattr(mod, "sinusoidal_embedding_1d"):
            setattr(mod, "sinusoidal_embedding_1d", sinusoidal_embedding_1d_cpu_f64)
            patched.append(mod_name)
    if verbose:
        print(f"  [mps_compat] sinusoidal_embedding_1d float64->CPU patched in "
              f"{len(patched)} module(s):")
        for p in patched:
            print(f"     - {p}")
    return patched


def verify() -> dict:
    """Confirm the shim reproduces upstream float64 output exactly (on CPU)."""
    from moss_soundeffect_v2.diffsynth.models import wan_video_dit as W
    ref = W.__dict__.get("_orig_sinusoidal_embedding_1d")
    t = torch.tensor([137.0], dtype=torch.float32)
    ours = sinusoidal_embedding_1d_cpu_f64(256, t)
    # recompute upstream formula inline on CPU for comparison
    pos = t.type(torch.float64)
    f = torch.pow(10000, -torch.arange(128, dtype=torch.float64).div(128))
    s = torch.outer(pos, f)
    up = torch.cat([torch.cos(s), torch.sin(s)], dim=1).to(t.dtype)
    return {"max_abs_diff_vs_upstream_cpu": float((ours - up).abs().max()),
            "exact_match": bool(torch.equal(ours, up)), "shape": list(ours.shape)}

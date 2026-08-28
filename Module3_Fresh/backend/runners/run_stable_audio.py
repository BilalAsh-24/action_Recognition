#!/usr/bin/env python
"""Stable Audio Open 1.0 runner — executed INSIDE venv-stable-audio.

Reuses the configuration proven in the existing project experiment
(03-FoleyCrafter-Test/action-recognition/stable-audio/open1_drinking_v1.py):
float32 throughout, MPS, dpmpp-3m-sde, vanilla CFG (apg_scale 0 — the library default
of 1.0 needs float64, unsupported on MPS), and a latent-token budget rather than the
model's full 47 s native size, which does not fit in available RAM.

Writes native 44.1 kHz stereo. Conversion to the pipeline's 48 kHz mono is done by the
caller with ffmpeg, so this runner stays minimal.

    run_stable_audio.py --prompt P --out PATH --seconds 10 --steps 100 --cfg 7.0 --seed 42
"""
from __future__ import annotations
import argparse, gc, json, os, sys, time, warnings
from pathlib import Path

import torch
from scipy.io import wavfile

MODEL_ID = "stabilityai/stable-audio-open-1.0"
SAMPLER = "dpmpp-3m-sde"
SIGMA_MIN, SIGMA_MAX = 0.3, 500.0
APG_SCALE = 0.0            # vanilla CFG; library default 1.0 requires float64 (no MPS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--cfg", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-avail-gb", type=float, default=1.5)
    a = ap.parse_args()
    t_all = time.time()

    # NOTE: the available-RAM guard runs in the CALLER (backend/services), not here.
    # venv-stable-audio is a protected environment and psutil is not installed in it;
    # adding a package to it purely for a guard is not worth the modification.

    from stable_audio_tools import get_pretrained_model
    from stable_audio_tools.inference.generation import generate_diffusion_cond

    t0 = time.time()
    model, cfgd = get_pretrained_model(MODEL_ID)
    SR = int(cfgd["sample_rate"])
    CH = int(cfgd["audio_channels"])
    DOWNSAMPLE = int(cfgd["model"]["pretransform"]["config"]["downsampling_ratio"])

    # Latent-token budget: enough tokens to cover the requested duration. The model's
    # native sample_size (47 s) does not fit in this machine's RAM.
    tokens = int((a.seconds * SR) // DOWNSAMPLE) + 1
    sample_size = tokens * DOWNSAMPLE

    # float32 everywhere: MPS lacks the float64 paths the library would otherwise use,
    # and float16 produced non-finite values in earlier testing.
    model = model.to(torch.float32)
    cond = model.conditioner.conditioners["prompt"]
    if hasattr(cond, "model"):
        cond.__dict__["model"] = cond.__dict__["model"].to(torch.float32)
    model = model.to("mps")
    if hasattr(cond, "model"):
        cond.__dict__["model"] = cond.__dict__["model"].to("mps")
    load_s = time.time() - t0

    COND = [{"prompt": a.prompt, "seconds_start": 0, "seconds_total": float(a.seconds)}]
    NEG = [{"prompt": a.negative, "seconds_start": 0,
            "seconds_total": float(a.seconds)}] if a.negative.strip() else None

    t0 = time.time()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # apg_scale MUST be 0. The library default of 1.0 takes an adaptive-projected-
        # guidance path that computes in float64, which MPS does not support.
        kw = dict(model=model, conditioning=COND, steps=int(a.steps),
                  cfg_scale=float(a.cfg), sample_size=sample_size, sample_rate=SR,
                  seed=int(a.seed), device="mps", sampler_type=SAMPLER,
                  sigma_min=SIGMA_MIN, sigma_max=SIGMA_MAX,
                  apg_scale=APG_SCALE, batch_size=1)
        if NEG:
            kw["negative_conditioning"] = NEG
        audio = generate_diffusion_cond(**kw)
        caught = sorted({str(x.message)[:160] for x in w})
    gen_s = time.time() - t0

    aud = audio.to(torch.float32).div(torch.max(torch.abs(audio)).clamp(min=1e-9)) \
               .clamp(-1, 1).cpu()[0]
    if not torch.isfinite(aud).all():
        raise ValueError("generated audio contains NaN or Inf")

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(out), SR, aud.mul(32767).to(torch.int16).numpy().T)

    del model, audio, aud
    gc.collect(); torch.mps.empty_cache()

    print(json.dumps({
        "ok": True, "model": MODEL_ID, "out": str(out),
        "sample_rate": SR, "channels": CH, "seconds": a.seconds,
        "latent_tokens": tokens, "sample_size": sample_size,
        "steps": a.steps, "cfg_scale": a.cfg, "seed": a.seed,
        "sampler": SAMPLER, "apg_scale": APG_SCALE,
        "load_s": round(load_s, 2), "generation_s": round(gen_s, 2),
        "total_s": round(time.time() - t_all, 2), "warnings": caught}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}),
              file=sys.stderr)
        sys.exit(1)

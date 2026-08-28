#!/usr/bin/env python
"""MOSS-SoundEffect v2.0 — local installation smoke test (NO audio generation).

Verifies that the model loads, sits on MPS at the expected dtype, contains no
NaN/Inf, invokes no CUDA-only code path, and can construct its inference
pipeline. Deliberately stops short of running the denoiser: no WAV is produced.

Reproducible: python moss/scripts/moss_smoke_test.py [--dtype bfloat16] [--device mps]
Exit code 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # Module3_Fresh/
CKPT = ROOT / "moss" / "checkpoints" / "MOSS-SoundEffect-v2.0"
REPORT = ROOT / "results" / "moss_smoke_test_result.json"

# The DiT's torch.compile path targets Triton/CUDA; disable it up front on MPS.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

import psutil  # noqa: E402
import torch   # noqa: E402


def mem():
    v, s = psutil.virtual_memory(), psutil.swap_memory()
    return {"used_gb": round(v.used / 1e9, 3),
            "available_gb": round(v.available / 1e9, 3),
            "swap_gb": round(s.used / 1e9, 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="mps")
    ap.add_argument("--dtype", default="bfloat16", choices=["float32", "bfloat16"])
    ap.add_argument("--ckpt", default=str(CKPT))
    args = ap.parse_args()
    dtype = getattr(torch, args.dtype)

    R: dict = {"checks": {}, "warnings": []}
    fails: list[str] = []

    def check(name, ok, detail=None):
        R["checks"][name] = {"pass": bool(ok), "detail": detail}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    print("=" * 72)
    print("MOSS-SoundEffect v2.0 — local smoke test (no generation)")
    print("=" * 72)

    R["environment"] = {
        "os": f"{platform.system()} {platform.mac_ver()[0]} ({platform.release()})",
        "arch": platform.machine(),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "TORCHDYNAMO_DISABLE": os.environ.get("TORCHDYNAMO_DISABLE"),
    }
    print(json.dumps(R["environment"], indent=2))

    R["memory_before"] = mem()
    print(f"\nRAM before: {R['memory_before']}")

    # ---- 1. import -----------------------------------------------------------
    print("\n1. import")
    try:
        from moss_soundeffect_v2 import MossSoundEffectPipeline
        import moss_soundeffect_v2 as _m
        check("import_moss", True, Path(_m.__file__).parent.name)
    except Exception as e:
        check("import_moss", False, f"{type(e).__name__}: {e}")
        return finish(R, fails)

    # ---- 2. isolation --------------------------------------------------------
    print("\n2. environment isolation")
    forbidden = ("venv-qwen", "venv-foley", "venv-stable-audio",
                 "venv-audioldm2", "venv-mmaudio")
    leaks = [p for p in sys.path if any(f in p for f in forbidden)]
    check("no_other_venv_on_path", not leaks, str(leaks) if leaks else "clean")

    for mod in ("flash_attn", "flash_attn_interface", "xformers", "triton", "bitsandbytes"):
        check(f"absent:{mod}", mod not in sys.modules and _cannot_import(mod))

    # ---- 3. checkpoints ------------------------------------------------------
    print("\n3. checkpoint completeness")
    ck = Path(args.ckpt)
    expected = {
        "transformer/diffusion_pytorch_model.safetensors": 5_664_000_000,
        "text_encoder/model-00001-of-00002.safetensors":   3_441_000_000,
        "text_encoder/model-00002-of-00002.safetensors":     622_000_000,
        "vae/vae_128d_48k.pth":                            1_486_000_000,
        "model_index.json": 0, "tokenizer/tokenizer.json": 0,
    }
    files = {}
    for rel, min_sz in expected.items():
        f = ck / rel
        ok = f.is_file() and f.stat().st_size >= min_sz * 0.98
        files[rel] = f.stat().st_size if f.is_file() else 0
        check(f"ckpt:{rel}", ok, f"{files[rel]/1e9:.3f} GB" if files[rel] else "MISSING")
    incomplete = list(ck.rglob("*.incomplete")) if ck.exists() else []
    check("no_incomplete_downloads", not incomplete, str(len(incomplete)))
    R["checkpoints"] = {k: {"bytes": v, "gb": round(v / 1e9, 3)} for k, v in files.items()}
    R["checkpoint_total_gb"] = round(sum(f.stat().st_size for f in ck.rglob("*") if f.is_file()) / 1e9, 3)

    # ---- 4. MPS --------------------------------------------------------------
    print("\n4. MPS availability")
    check("mps_built", torch.backends.mps.is_built())
    check("mps_available", torch.backends.mps.is_available())
    check("cuda_absent", not torch.cuda.is_available(), "torch.version.cuda=" + str(torch.version.cuda))
    if torch.backends.mps.is_available():
        x = torch.randn(512, 512, device="mps", dtype=dtype)
        check("mps_matmul_finite", bool(torch.isfinite(x @ x).all()))
        R["mps_recommended_max_memory_gb"] = round(torch.mps.recommended_max_memory() / 2**30, 2)

    # ---- 5. load -------------------------------------------------------------
    print(f"\n5. load pipeline (device={args.device}, dtype={args.dtype})")
    t0 = time.time()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            pipe = MossSoundEffectPipeline.from_pretrained(
                str(ck), torch_dtype=dtype, device=args.device)
            load_s = round(time.time() - t0, 2)
            check("pipeline_loaded", True, f"{load_s}s")
        except Exception as e:
            check("pipeline_loaded", False, f"{type(e).__name__}: {e}")
            return finish(R, fails)
        R["warnings"] = sorted({str(x.message)[:220] for x in w})
    R["memory_after_load"] = mem()
    R["load_seconds"] = load_s
    print(f"   RAM after load: {R['memory_after_load']}")

    # ---- 6. device / dtype / finiteness -------------------------------------
    print("\n6. device, dtype and parameter integrity")
    check("device_is_requested", pipe.device.type == args.device,
          f"pipe.device={pipe.device}")
    check("dtype_is_requested", pipe.dtype == dtype, f"pipe.dtype={pipe.dtype}")
    check("sample_rate_48k", pipe.sample_rate == 48000, str(pipe.sample_rate))
    check("max_inference_seconds", pipe.max_inference_seconds == 30,
          str(pipe.max_inference_seconds))

    comps, bad_dtype, bad_dev, nonfinite, total = {}, [], [], [], 0
    for name in ("dit", "text_encoder", "vae"):
        mod = getattr(pipe.engine, name, None)
        if mod is None or not hasattr(mod, "parameters"):
            continue
        n = sum(p.numel() for p in mod.parameters())
        total += n
        dts = {str(p.dtype) for p in mod.parameters()}
        devs = {p.device.type for p in mod.parameters()}
        nf = sum(int(not torch.isfinite(p).all()) for p in mod.parameters())
        comps[name] = {"params_M": round(n / 1e6, 2), "dtypes": sorted(dts),
                       "devices": sorted(devs), "nonfinite_tensors": nf}
        print(f"   {name:<13} {n/1e6:8.2f}M  {sorted(dts)}  {sorted(devs)}  nonfinite={nf}")
        if nf:
            nonfinite.append(name)
        if any(d not in (str(dtype), "torch.float32") for d in dts):
            bad_dtype.append(name)
        if devs - {args.device}:
            bad_dev.append(name)
    R["components"] = comps
    R["total_params_M"] = round(total / 1e6, 2)
    check("components_found", bool(comps), f"{len(comps)} modules, {total/1e6:.1f}M params")
    check("all_on_device", not bad_dev, str(bad_dev) if bad_dev else args.device)
    check("no_unexpected_dtype", not bad_dtype, str(bad_dtype) if bad_dtype else "ok")
    check("no_nan_inf_in_weights", not nonfinite, str(nonfinite) if nonfinite else "clean")

    # ---- 7. pipeline can initialise its scheduler ---------------------------
    print("\n7. inference pipeline initialisation")
    check("scheduler_present", pipe.scheduler is not None, type(pipe.scheduler).__name__)
    check("engine_present", pipe.engine is not None, type(pipe.engine).__name__)
    check("callable", callable(pipe), "no denoising invoked")

    # ---- 8. no CUDA was touched ---------------------------------------------
    print("\n8. CUDA non-invocation")
    check("cuda_never_initialized", not torch.cuda.is_initialized())
    for mod in ("flash_attn", "xformers", "triton", "bitsandbytes"):
        check(f"not_loaded:{mod}", mod not in sys.modules)

    R["memory_peak_note"] = "measured at load; no denoising performed"
    return finish(R, fails)


def _cannot_import(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is None


def finish(R, fails):
    R["failed_checks"] = fails
    R["result"] = "PASS" if not fails else "FAIL"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(R, indent=2))
    print("\n" + "=" * 72)
    print(f"RESULT: {R['result']}" + (f"  (failed: {fails})" if fails else ""))
    print(f"wrote {REPORT}")
    print("=" * 72)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

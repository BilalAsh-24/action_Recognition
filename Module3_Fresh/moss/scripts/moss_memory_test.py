#!/usr/bin/env python
"""MOSS-SoundEffect v2.0 — phase-separation DRY RUN / memory test.

Loads each phase's components in isolation, records memory, frees them, and
verifies they are no longer resident. **Generates no audio**: no denoising loop
is entered and the VAE decoder is never invoked.

Goal: confirm that phase separation + bfloat16 casting avoids the +9.80 GB swap
growth measured when the stock pipeline loads everything at once in mixed
float32/bfloat16.

    moss/venv-moss/bin/python moss/scripts/moss_memory_test.py

Exit 0 = SAFE TO GENERATE, 1 = UNSAFE (do not generate).
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moss_phased as M                                    # noqa: E402
import torch                                               # noqa: E402

ABORT_AVAILABLE_GB = 1.5
MAX_SAFE_SWAP_GROWTH_GB = 2.0          # MMAudio's successful runs were +0.33 / +0.49 GB
REPORT = M.ROOT / "results" / "moss_memory_test_result.json"

R: dict = {"mode": "DRY RUN — no audio generated", "phases": {}}


def banner(t):
    print("\n" + "=" * 74 + f"\n{t}\n" + "=" * 74, flush=True)


def main() -> int:
    banner("MOSS phase-separation memory test (no generation)")
    assert torch.backends.mps.is_available(), "MPS unavailable"
    assert not torch.cuda.is_available(), "CUDA unexpectedly present"

    R["config"] = {"device": M.DEVICE, "dtype": str(M.DTYPE),
                   "fp16_used": False, "cuda_used": False,
                   "TORCHDYNAMO_DISABLE": "1",
                   "checkpoint": str(M.CKPT.relative_to(M.ROOT))}
    print(json.dumps(R["config"], indent=2))

    tracker = M.MemoryTracker(abort_available_gb=ABORT_AVAILABLE_GB)
    tracker.start()
    R["baseline"] = M.snapshot()
    print(f"\nbaseline: {R['baseline']}")

    # ------------------------------------------------------------ PHASE 1
    banner("PHASE 1 — Qwen3 text encoder (bfloat16)")
    from moss_soundeffect_v2.diffsynth.models.qwen3_text_encoder import Qwen3TextEncoder
    t0 = time.time()
    te, prompter = M.load_text_encoder()
    load_s = round(time.time() - t0, 2)
    d = M.describe(te, "text_encoder")
    peak = M.snapshot()
    print(f"  {d}")
    print(f"  loaded in {load_s}s   mem {peak}")
    R["phases"]["1_text_encoder"] = {"component": d, "load_s": load_s, "resident": peak}

    del te, prompter
    M.sweep()
    resid = M.live_instances(Qwen3TextEncoder)
    after = M.snapshot()
    print(f"  after free: residency {resid}   mem {after}")
    R["phases"]["1_text_encoder"]["residency_after_free"] = resid
    R["phases"]["1_text_encoder"]["after_free"] = after
    assert resid["Qwen3TextEncoder"] == 0, "text encoder still resident"

    # ------------------------------------------------------------ PHASE 2
    banner("PHASE 2 — MOSS DiT (cast to bfloat16)")
    from moss_soundeffect_v2.diffsynth.models.wan_audio_dit import WanAudioModel
    t0 = time.time()
    dit, dit_cfg = M.load_dit()
    load_s = round(time.time() - t0, 2)
    d = M.describe(dit, "dit")
    peak = M.snapshot()
    print(f"  {d}")
    print(f"  loaded in {load_s}s   mem {peak}")
    R["phases"]["2_dit"] = {"component": d, "load_s": load_s, "resident": peak,
                            "dit_dim": dit_cfg["dim"], "num_layers": dit_cfg["num_layers"]}

    del dit
    M.sweep()
    resid = M.live_instances(WanAudioModel)
    after = M.snapshot()
    print(f"  after free: residency {resid}   mem {after}")
    R["phases"]["2_dit"]["residency_after_free"] = resid
    R["phases"]["2_dit"]["after_free"] = after
    assert resid["WanAudioModel"] == 0, "DiT still resident"

    # ------------------------------------------------------------ PHASE 3
    banner("PHASE 3 — DAC VAE (cast to bfloat16)")
    from moss_soundeffect_v2.diffsynth.models.dac_vae import DAC
    t0 = time.time()
    vae = M.load_vae()
    load_s = round(time.time() - t0, 2)
    d = M.describe(vae, "vae")
    peak = M.snapshot()
    print(f"  {d}")
    print(f"  loaded in {load_s}s   mem {peak}")
    print(f"  sample_rate {getattr(vae,'sample_rate','?')}  hop_length {getattr(vae,'hop_length','?')}")
    R["phases"]["3_vae"] = {"component": d, "load_s": load_s, "resident": peak,
                            "sample_rate": int(getattr(vae, "sample_rate", 0)),
                            "hop_length": int(getattr(vae, "hop_length", 0))}

    del vae
    M.sweep()
    resid = M.live_instances(DAC)
    after = M.snapshot()
    print(f"  after free: residency {resid}   mem {after}")
    R["phases"]["3_vae"]["residency_after_free"] = resid
    R["phases"]["3_vae"]["after_free"] = after

    # ------------------------------------------------------------ verdict
    tracker.stop()
    R["memory"] = tracker.report()
    R["final"] = M.snapshot()

    banner("RESULT")
    m = R["memory"]
    print(f"baseline used {m['baseline']['used_gb']:.2f} / available "
          f"{m['baseline']['available_gb']:.2f} / swap {m['baseline']['swap_gb']:.2f} GB")
    print(f"peak used        : {m['peak_used_gb']:.2f} GB   (+{m['used_growth_gb']:.2f})")
    print(f"min available    : {m['min_available_gb']:.2f} GB   (abort at {ABORT_AVAILABLE_GB})")
    print(f"peak swap        : {m['peak_swap_gb']:.2f} GB")
    print(f"swap growth      : {m['swap_growth_gb']:+.2f} GB   (safe if <= {MAX_SAFE_SWAP_GROWTH_GB})")
    print(f"peak MPS driver  : {m['peak_mps_driver_gb']:.2f} GB")

    largest = max(p["component"]["bytes_gb"] for p in R["phases"].values())
    total_if_resident = round(sum(p["component"]["bytes_gb"] for p in R["phases"].values()), 3)
    R["weights"] = {"largest_single_phase_gb": largest,
                    "sum_if_all_resident_gb": total_if_resident,
                    "stock_pipeline_gb": 10.59,
                    "saving_vs_stock_gb": round(10.59 - largest, 2)}
    print(f"\nlargest single phase : {largest:.2f} GB")
    print(f"sum if co-resident   : {total_if_resident:.2f} GB   (stock float32 pipeline: 10.59 GB)")

    problems = []
    if m["breach"]:
        problems.append(f"available RAM breach: {m['breach']}")
    if m["min_available_gb"] < ABORT_AVAILABLE_GB:
        problems.append(f"min available {m['min_available_gb']:.2f} GB < {ABORT_AVAILABLE_GB} GB")
    if m["swap_growth_gb"] > MAX_SAFE_SWAP_GROWTH_GB:
        problems.append(f"swap growth {m['swap_growth_gb']:.2f} GB > {MAX_SAFE_SWAP_GROWTH_GB} GB")
    for k, p in R["phases"].items():
        if not p["component"]["dtype_ok"]:
            problems.append(f"{k}: dtype not bfloat16 ({p['component']['dtypes']})")
        if not p["component"]["device_ok"]:
            problems.append(f"{k}: not on {M.DEVICE} ({p['component']['devices']})")

    R["problems"] = problems
    R["verdict"] = "SAFE_TO_GENERATE" if not problems else "UNSAFE_DO_NOT_GENERATE"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(R, indent=2, default=str))

    print(f"\nVERDICT: {R['verdict']}")
    for p in problems:
        print(f"  - {p}")
    print(f"wrote {REPORT}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""MOSS-SoundEffect v2.0 generation driver — phase-separated, bfloat16, MPS.

Parameterised version of the validated drinking-generation script. Same wrapper,
same MPS compatibility fixes, same sampler settings; prompt/negative/output are
supplied on the command line so each action gets its own file.

Reproduces the successful Hugging Face Space configuration exactly, but splits
MossSoundEffectPipeline.__call__ into three subprocess-free phases so the Qwen3
text encoder, the DiT and the DAC VAE are never co-resident.

Faithfulness to upstream (verified against wan_audio.py / pipeline_moss_soundeffect.py):
  * prompt gets the training-time suffix `" duration: 10.0s"` (append_duration_suffix=True)
  * the engine always denoises a FULL 30 s latent, then the waveform is cropped to 10 s
  * noise is drawn on CPU with the seeded generator, then moved (rand_device="cpu")
  * the whole engine call runs under torch.autocast(device_type, bfloat16)
  * CFG: noise_pred = nega + cfg_scale * (posi - nega), computed in float32
  * scheduler: FlowMatchScheduler, shift=sigma_shift, denoising_strength=1.0

The MOSS repository is imported, never modified. ONE generation. No retries.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moss_phased as M                                        # noqa: E402
import mps_compat                                              # noqa: E402
import numpy as np                                             # noqa: E402
import soundfile as sf                                         # noqa: E402
import torch                                                   # noqa: E402

ABORT_AVAILABLE_GB = 1.5

R: dict = {"generations": 1}


def banner(t):
    print("\n" + "=" * 74 + f"\n{t}\n" + "=" * 74, flush=True)


def guard(tracker, phase):
    if tracker.breach:
        raise MemoryError(f"memory guard tripped during {phase}: {tracker.breach}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=M.SEED)
    ap.add_argument("--seconds", type=float, default=M.SECONDS)
    ap.add_argument("--steps", type=int, default=M.NUM_INFERENCE_STEPS)
    ap.add_argument("--cfg", type=float, default=M.CFG_SCALE)
    ap.add_argument("--sigma_shift", type=float, default=M.SIGMA_SHIFT)
    A = ap.parse_args()
    global OUT_WAV, REPORT
    OUT_WAV = Path(A.out) if Path(A.out).is_absolute() else M.ROOT / A.out
    REPORT = M.ROOT / "results" / f"{A.label}_generation.json"
    R["run"] = A.label
    assert not OUT_WAV.exists(), f"refusing to overwrite {OUT_WAV}"
    assert torch.backends.mps.is_available(), "MPS unavailable"
    assert not torch.cuda.is_available(), "CUDA unexpectedly present"
    assert M.DTYPE is torch.bfloat16

    # --- exact Space configuration -------------------------------------------
    seconds = round(float(A.seconds), 1)
    full_seconds = 30                       # max_inference_seconds; engine always denoises this
    sr = M.SAMPLE_RATE
    formatted_prompt = f"{A.prompt.strip()} duration: {seconds:.1f}s"
    cfg = {"model": "MOSS-SoundEffect v2.0", "device": M.DEVICE, "dtype": str(M.DTYPE),
           "prompt": A.prompt, "prompt_sent_to_model": formatted_prompt,
           "negative_prompt": A.negative, "seconds": seconds,
           "denoised_seconds_internally": full_seconds,
           "num_inference_steps": A.steps, "cfg_scale": A.cfg,
           "sigma_shift": A.sigma_shift, "seed": A.seed, "denoising_strength": 1.0,
           "rand_device": "cpu", "sample_rate": sr, "num_channels": M.NUM_CHANNELS,
           "fp16_used": False, "cuda_used": False, "TORCHDYNAMO_DISABLE": "1"}
    R["config"] = cfg
    banner(f"MOSS-SoundEffect v2.0 — local generation: {A.label}")
    print(json.dumps(cfg, indent=2))

    tracker = M.MemoryTracker(abort_available_gb=ABORT_AVAILABLE_GB)
    tracker.start()
    R["baseline"] = M.snapshot()
    print(f"\nbaseline {R['baseline']}\nguard: abort below {ABORT_AVAILABLE_GB} GB available")
    t_all = time.time()

    with warnings.catch_warnings(record=True) as wlog:
        warnings.simplefilter("always")

        # ================= PHASE 1 — TEXT =====================================
        banner("PHASE 1 — Qwen3 text encoder (bf16)")
        from moss_soundeffect_v2.diffsynth.models.qwen3_text_encoder import Qwen3TextEncoder
        t0 = time.time()
        pipe = M.build_engine_shell()
        te, prompter = M.load_text_encoder()
        pipe.text_encoder, pipe.prompter = te, prompter
        print(f"  {M.describe(te, 'text_encoder')}")
        guard(tracker, "phase1 load")

        with torch.no_grad(), torch.autocast(M.DEVICE, dtype=M.DTYPE):
            ctx_posi = prompter.encode_prompt(formatted_prompt, positive=True, device=M.DEVICE)
            ctx_nega = prompter.encode_prompt(A.negative, positive=False, device=M.DEVICE)
        torch.mps.synchronize()
        p1 = round(time.time() - t0, 2)
        for n, t in (("positive", ctx_posi), ("negative", ctx_nega)):
            print(f"  context {n}: {tuple(t.shape)} {t.dtype} finite={bool(torch.isfinite(t).all())}")
            assert torch.isfinite(t).all(), f"{n} context has NaN/Inf"
        R["phase1"] = {"seconds": p1, "resident": M.snapshot(),
                       "context_posi_shape": list(ctx_posi.shape),
                       "context_nega_shape": list(ctx_nega.shape)}

        ctx_posi_c, ctx_nega_c = ctx_posi.detach().cpu(), ctx_nega.detach().cpu()
        del te, prompter, pipe.text_encoder, pipe.prompter, pipe, ctx_posi, ctx_nega
        M.sweep()
        resid = M.live_instances(Qwen3TextEncoder)
        R["phase1"]["residency_after_free"] = resid
        R["phase1"]["after_free"] = M.snapshot()
        print(f"  freed: {resid}  {R['phase1']['after_free']}")
        assert resid["Qwen3TextEncoder"] == 0
        guard(tracker, "phase1 free")

        # ================= PHASE 2 — DIFFUSION ================================
        banner(f"PHASE 2 — MOSS DiT (bf16), {A.steps} euler steps, CFG {A.cfg}")
        from moss_soundeffect_v2.diffsynth.models.wan_audio_dit import WanAudioModel
        from moss_soundeffect_v2.diffsynth.pipelines.wan_audio import model_fn_wan_video
        # MPS has no float64; run the timestep-embedding float64 math on CPU.
        # Repository untouched — module attributes patched in this process only.
        R["mps_compat"] = {"sinusoidal_embedding_1d": mps_compat.verify(),
                           "patched_modules": mps_compat.apply()}
        t0 = time.time()
        pipe = M.build_engine_shell()
        dit, dit_cfg = M.load_dit()
        pipe.dit = dit
        pipe.audio_latent_dim = dit_cfg["in_dim"]
        pipe.num_samples_division_factor = 960          # DAC hop_length, asserted in phase 3
        d = M.describe(dit, "dit")
        print(f"  {d}")
        assert d["buffer_dtypes"] == ["torch.complex64"], \
            f"DiT RoPE buffers unexpected: {d['buffer_dtypes']}"
        R["phase2_rope"] = {"downcast_complex128_to_complex64": dit._complex128_downcast,
                            "lossless": "rope_apply reads .real/.imag at float32"}
        print(f"  RoPE buffers complex64 on MPS (downcast: {dit._complex128_downcast})")
        guard(tracker, "phase2 load")

        pipe.scheduler.set_timesteps(A.steps, denoising_strength=1.0,
                                     shift=A.sigma_shift)
        num_channels, num_samples = pipe.check_resize_num_channels_num_samples(
            M.NUM_CHANNELS, sr * full_seconds)
        shape = (1, pipe.audio_latent_dim, num_samples // pipe.num_samples_division_factor)
        latents = pipe.generate_noise(shape, seed=A.seed, rand_device="cpu")
        print(f"  latent {tuple(latents.shape)} {latents.dtype}  "
              f"num_samples {num_samples} ({num_samples/sr:.1f}s internal)")
        R["phase2"] = {"latent_shape": list(latents.shape), "num_samples": int(num_samples),
                       "num_channels": int(num_channels), "steps": A.steps}

        ctx_p = ctx_posi_c.to(M.DEVICE, M.DTYPE)
        ctx_n = ctx_nega_c.to(M.DEVICE, M.DTYPE)
        t_diff = time.time()
        with torch.no_grad(), torch.autocast(M.DEVICE, dtype=M.DTYPE):
            for i, ts in enumerate(pipe.scheduler.timesteps):
                timestep = ts.unsqueeze(0).to(device=M.DEVICE)
                npos = model_fn_wan_video(dit=dit, motion_controller=None, vace=None,
                                          latents=latents, timestep=timestep, context=ctx_p)
                npos = npos.clone()
                nneg = model_fn_wan_video(dit=dit, motion_controller=None, vace=None,
                                          latents=latents, timestep=timestep, context=ctx_n)
                noise_pred = nneg.float() + A.cfg * (npos.float() - nneg.float())
                latents = pipe.scheduler.step(noise_pred, pipe.scheduler.timesteps[i], latents)
                if (i + 1) % 10 == 0 or i == 0:
                    print(f"    step {i+1:>2}/{A.steps}  "
                          f"avail {M.snapshot()['available_gb']:.2f} GB", flush=True)
                    guard(tracker, f"phase2 step {i+1}")
        torch.mps.synchronize()
        diff_s = round(time.time() - t_diff, 2)
        assert torch.isfinite(latents).all(), "latent contains NaN/Inf"
        print(f"  diffusion {diff_s}s  latent finite  absmax {latents.abs().max().item():.4f}")
        R["phase2"].update({"seconds": round(time.time() - t0, 2), "diffusion_seconds": diff_s,
                            "resident": M.snapshot(),
                            "latent_absmax": float(latents.abs().max()),
                            "latent_std": float(latents.float().std())})

        latents_c = latents.detach().cpu()
        del dit, pipe.dit, pipe, latents, ctx_p, ctx_n
        M.sweep()
        resid = M.live_instances(WanAudioModel)
        R["phase2"]["residency_after_free"] = resid
        R["phase2"]["after_free"] = M.snapshot()
        print(f"  freed: {resid}  {R['phase2']['after_free']}")
        assert resid["WanAudioModel"] == 0
        guard(tracker, "phase2 free")

        # ================= PHASE 3 — DECODE ===================================
        banner("PHASE 3 — DAC VAE decode (bf16)")
        from moss_soundeffect_v2.diffsynth.models.dac_vae import DAC
        t0 = time.time()
        vae = M.load_vae()
        print(f"  {M.describe(vae, 'vae')}")
        assert int(vae.hop_length) == 960, f"hop_length {vae.hop_length} != 960 assumed in phase 2"
        assert int(vae.sample_rate) == sr
        guard(tracker, "phase3 load")

        lat = latents_c.to(M.DEVICE, M.DTYPE)
        with torch.no_grad(), torch.autocast(M.DEVICE, dtype=M.DTYPE):
            audio = vae.decode(lat)
        torch.mps.synchronize()
        dec_s = round(time.time() - t0, 2)
        print(f"  decode {dec_s}s  audio {tuple(audio.shape)} {audio.dtype}")

        a = audio.detach().float().cpu()[0]                    # (C, T)
        if a.ndim == 1:
            a = a.unsqueeze(0)
        a = a[:, : int(sr * seconds)]                          # crop 30 s -> 10 s
        y = a[0].numpy().astype(np.float64)
        R["phase3"] = {"seconds": dec_s, "resident": M.snapshot(),
                       "decoded_shape": list(audio.shape), "cropped_samples": int(y.shape[0])}
        del vae, audio, lat, latents_c
        M.sweep()
        R["phase3"]["residency_after_free"] = M.live_instances(DAC)
        R["phase3"]["after_free"] = M.snapshot()

        R["warnings"] = sorted({str(w.message)[:200] for w in wlog})

    # ---- write WAV ----------------------------------------------------------
    assert np.isfinite(y).all(), "audio contains NaN/Inf"
    peak = float(np.abs(y).max())
    over = int(np.sum(np.abs(y) > 1.0))
    print(f"\n  raw float: {y.shape[0]} samples  peak {peak:.6f}  >|1.0| {over}")
    pcm = y if over == 0 else np.clip(y, -1.0, 1.0)
    OUT_WAV.parent.mkdir(parents=True, exist_ok=True)
    sf.write(OUT_WAV, pcm.astype(np.float32), sr, subtype="PCM_16")
    print(f"  wrote {OUT_WAV}")

    tracker.stop()
    R["memory"] = tracker.report()
    R["total_seconds"] = round(time.time() - t_all, 2)
    R["output"] = {"path": str(OUT_WAV.relative_to(M.ROOT)), "sample_rate": sr,
                   "channels": 1, "subtype": "PCM_16",
                   "raw_peak": peak, "clipped_before_write": over > 0,
                   "bytes": OUT_WAV.stat().st_size}
    R["status"] = "SUCCESS"
    REPORT.write_text(json.dumps(R, indent=2, default=str))

    m = R["memory"]
    banner("RESULT")
    print(f"total {R['total_seconds']}s  (p1 {R['phase1']['seconds']}s  "
          f"p2 {R['phase2']['seconds']}s [diffusion {R['phase2']['diffusion_seconds']}s]  "
          f"p3 {R['phase3']['seconds']}s)")
    print(f"peak used {m['peak_used_gb']:.2f} GB   min available {m['min_available_gb']:.2f} GB")
    print(f"peak swap {m['peak_swap_gb']:.2f} GB   swap growth {m['swap_growth_gb']:+.2f} GB")
    print(f"breach: {m['breach']}")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MemoryError as e:
        print(f"\n!!! MEMORY GUARD ABORT: {e}", flush=True)
        sys.exit(2)

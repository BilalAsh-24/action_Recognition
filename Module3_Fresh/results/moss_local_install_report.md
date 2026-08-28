# MOSS-SoundEffect v2.0 — Local Installation Report

**Date:** 2026-08-25
**Phase:** installation + smoke test only. **No audio generated.**

# RESULT: ✅ PASS

All 33 smoke-test checks passed. The model loads on MPS, contains no NaN/Inf, invokes no CUDA-only
code path, and can construct its inference pipeline. One significant memory finding is documented
below — it does not fail the install, but it should be addressed before the first generation.

---

## Environment

| | |
|---|---|
| **OS** | macOS 26.2 (Tahoe), build 25C56 |
| **Hardware** | Apple M4, arm64, 17.18 GB unified memory |
| **Python** | **3.12.13** — built via `pyenv install 3.12.13` (MOSS requires >=3.12; machine had only 3.10.20 and 3.11.9) |
| **PyTorch** | **2.9.1**, default PyPI wheel (`torch.version.cuda = None`) |
| **torchaudio** | 2.9.1 |
| **MPS** | built OK, available OK, matmul finite OK, recommended_max_memory 11.84 GB |
| **CUDA** | absent — `torch.cuda.is_available() = False`, never initialised |
| **Virtualenv** | `Module3_Fresh/moss/venv-moss` (1.2 GB) |

## MOSS version

| | |
|---|---|
| **Repository** | `https://github.com/OpenMOSS/MOSS-TTS` |
| **Commit** | `58b20a0d5fcc6766658d50967a90a9d890009a46` (`58b20a0`), shallow clone |
| **Package** | `moss-soundeffect-v2==0.1.0`, editable from `moss/MOSS-TTS/moss_soundeffect_v2` |
| **Model repo** | `OpenMOSS-Team/MOSS-SoundEffect-v2.0` |
| **Model revision** | `e35df4d82fbe87fcd5d14e5d100e349c0c3c076d` |
| **License** | **Apache-2.0** (confirmed via HF API) |
| **Repo state** | **pristine** — `git status --porcelain` empty; no MOSS source modified |

## Checkpoints

Downloaded to `Module3_Fresh/moss/checkpoints/MOSS-SoundEffect-v2.0/` (10 GB on disk, 11.23 GB nominal).

| File | Size |
|---|---|
| `transformer/diffusion_pytorch_model.safetensors` | 5.664 GB |
| `text_encoder/model-00001-of-00002.safetensors` | 3.441 GB |
| `text_encoder/model-00002-of-00002.safetensors` | 0.622 GB |
| `vae/vae_128d_48k.pth` | 1.486 GB |
| `tokenizer/` + `model_index.json` + configs | ~0.017 GB |
| **Total** | **11.230 GB** |

`.incomplete` files: **0**. All expected files present at full size.
Disk after install: **181 GB free** (was 201 GB).

## Loaded model

| Component | Params | dtype | Device | NaN/Inf | Resident |
|---|---|---|---|---|---|
| DiT (`dit_variant: 1.3B`) | 1416.05 M | **float32** | mps | 0 | 5.66 GB |
| Text encoder (Qwen3, dim 2048) | 1720.57 M | bfloat16 | mps | 0 | 3.44 GB |
| DAC VAE (48 kHz) | 371.59 M | **float32** | mps | 0 | 1.49 GB |
| **Total** | **3508.21 M** | mixed | mps | **0** | **~10.59 GB** |

Pipeline: `MossSoundEffectPipeline` -> engine `WanAudioPipeline` -> scheduler `FlowMatchScheduler`.
`sample_rate = 48000`, `max_inference_seconds = 30`. DiT load: `missing=0, unexpected=0`.

## RAM before / after

| | Used | Available | Swap |
|---|---|---|---|
| Before load | 5.06 GB | 7.03 GB | 1.45 GB |
| After load | 11.01 GB | 5.05 GB | **11.25 GB** |
| **Delta** | **+5.94 GB** | -1.98 GB | **+9.80 GB** |

Load time: **30.38 s**.

### The one finding that matters

**`torch_dtype=torch.bfloat16` was only honoured by the text encoder.** The DiT and the DAC VAE both
loaded in **float32**, so resident weights are ~10.59 GB rather than the 5.6-7.6 GB estimated before
download. That drove **+9.80 GB of swap growth** during load alone — before any denoising activations.

Calibration against this project's history:

| Run | Swap growth | Outcome |
|---|---|---|
| MMAudio phase-separated | +0.33 / +0.49 GB | succeeded |
| MMAudio all-resident | +3.8 GB | killed |
| FoleyCrafter run 1 / run 2 | +6.04 / +10.08 GB | second aborted at the guard |
| **MOSS load only** | **+9.80 GB** | loaded fine, no generation attempted |

Not a failure — everything loaded correctly and the weights are clean — but it is the same regime
that killed earlier runs, and generation will add activations on top.

**Mitigations available, none implemented (installation phase only):**

1. **Cast the DiT and VAE to bf16 in our wrapper.** Nearly free: `__call__` already wraps the engine
   in `torch.autocast("mps", dtype=torch.bfloat16)`, so the forward computes in bf16 regardless —
   fp32 storage buys no precision at inference. Saves ~3.58 GB (10.59 -> 7.01 GB).
2. **Phase-separate**, as proven with MMAudio: encode text -> free the 3.44 GB encoder -> denoise ->
   free the DiT -> decode with the VAE. Max resident ~5.66 GB, or ~2.83 GB combined with (1).
3. Reduce host baseline before running.

## Installed packages

Core (per official `pyproject.toml`): `numpy==1.26.4`, `einops==0.8.2`, `pillow==12.2.0`,
`tqdm==4.67.3`, `safetensors==0.7.0`, `transformers==4.57.1`, `diffusers==0.37.1`, `ftfy==6.3.1`,
`regex==2026.4.4`, `soundfile==0.13.1`, `imageio==2.37.3`, `typing_extensions==4.16.0`,
`descript-audiotools==0.7.2` — plus `torch==2.9.1`, `torchaudio==2.9.1`, and `psutil` (required for
the memory measurements in this report).

Transitive: librosa, scipy, scikit-learn, numba, matplotlib, tensorboard, julius, pyloudnorm, pystoi,
torch-stoi, argbind, rich, ipython, huggingface_hub, tokenizers — all pulled by
`descript-audiotools`, which the DAC VAE requires.

**Verified absent:** `flash-attn`, `flash_attn_interface`, `xformers`, `triton`, `bitsandbytes`,
`torchcodec`, and every `nvidia-*` / `cu12` wheel. No CUDA package installed; none loaded at runtime.

## Compatibility workarounds

| # | Issue | Action taken |
|---|---|---|
| 1 | `pyproject` declares `gradio==6.11.0` as a **core** dependency | **Omitted.** Verified by grep that no library module imports gradio — it is only for the demo app. Installed core deps explicitly, then `pip install --no-deps -e .`. Keeps the environment minimal as instructed. **No MOSS source modified.** |
| 2 | Official install uses `--extra-index-url .../cu128` and the `torch-cu128` extra (`torch==2.9.0+cu128`) | **Not used.** Installed `torch==2.9.1` / `torchaudio==2.9.1` from default PyPI — the macOS wheel is the MPS build. |
| 3 | PyTorch issue #167679: torch 2.9.1 reports MPS unavailable on macOS 26.0 (open, unresolved) | **Tested before downloading.** Does **not** reproduce on macOS 26.2 — `mps_available = True`, matmul finite. Pinned torch 2.9 is safe here. |
| 4 | DiT uses `torch.compile` with a Triton/CUDA-graph path | `TORCHDYNAMO_DISABLE=1` set inside the smoke test (documented upstream escape hatch). Triton not installed. |
| 5 | `_normalize_device("auto")` falls back to **CPU**, not MPS | Always pass `device="mps"` explicitly. Never use `"auto"`. |
| 6 | 4x hard-coded `torch.autocast("cuda", dtype=torch.float32)` in `diffsynth/pipelines/wan_audio.py` (lines 165, 425, 493, 755) | **Not addressed — deferred to the generation phase.** On a CUDA-less machine PyTorch disables these, so sections deliberately forced to fp32 inherit ambient bf16. To be handled in our own driver script if it affects output quality. No repo edit. |

## Warnings observed

One, benign:

```
`torch.nn.utils.weight_norm` is deprecated in favor of
`torch.nn.utils.parametrizations.weight_norm`.
```

Emitted by the DAC VAE. Deprecation only; no functional impact.

## Isolation verification

- `sys.path` contains no reference to `venv-qwen`, `venv-foley`, `venv-stable-audio`,
  `venv-audioldm2`, or `venv-mmaudio`.
- All five existing venvs retain their original mtimes (Aug 15-18) — untouched.
- Module 2 outputs, the original video, all previous WAV/MP4 files, and the MMAudio / Stable Audio /
  FoleyCrafter trees were not modified.
- The MOSS repository clone is pristine.

## Files created

| Path | Purpose |
|---|---|
| `moss/venv-moss/` | isolated Python 3.12.13 environment (1.2 GB) |
| `moss/MOSS-TTS/` | official repo, commit `58b20a0`, unmodified (27 MB) |
| `moss/checkpoints/MOSS-SoundEffect-v2.0/` | official weights, 11.23 GB |
| `moss/scripts/moss_smoke_test.py` | reproducible verification script |
| `results/moss_smoke_test_result.json` | machine-readable smoke-test output |
| `results/moss_local_install_report.md` | this report |

## Reproducing the smoke test

```bash
moss/venv-moss/bin/python moss/scripts/moss_smoke_test.py
```

Optional: `--device mps|cpu`, `--dtype bfloat16|float32`, `--ckpt <path>`.
Exit code 0 = PASS, 1 = FAIL. Generates no audio.

---

## Status

**Installation complete and verified. Stopping here as instructed — no drinking audio generated.**

Before the first local generation, the memory finding above should be settled: casting the DiT and
VAE to bf16 in our own wrapper is the cheap fix, and phase separation is the proven one. Both are
implemented outside the MOSS repository. Awaiting your instruction.

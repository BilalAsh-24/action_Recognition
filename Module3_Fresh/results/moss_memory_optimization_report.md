# MOSS-SoundEffect v2.0 — Memory Optimization & Phase-Separation Dry Run

**Date:** 2026-08-25 · **Mode:** DRY RUN — **no audio generated**

# VERDICT: ✅ SAFE_TO_GENERATE

The `+9.80 GB` swap growth measured at install is **eliminated**: this run produced **+0.00 GB**.

---

## Result

| Metric | Stock pipeline (install report) | Phase-separated + bf16 | Change |
|---|---|---|---|
| **Swap growth** | **+9.80 GB** | **+0.00 GB** | eliminated |
| Peak swap | 11.25 GB | 2.13 GB (= baseline) | −9.12 GB |
| Resident weights | 10.59 GB (all co-resident) | **3.44 GB** (largest single phase) | −7.15 GB |
| Sum if co-resident | 10.59 GB | 7.03 GB | −3.56 GB |
| Min available RAM | — | **2.60 GB** (abort floor 1.5 GB) | safe |
| Peak used | — | 11.62 GB (+6.77 over baseline) | — |
| Peak MPS driver | — | 6.78 GB | — |

Baseline at run: used 4.85 GB · available 9.90 GB · swap 2.13 GB.

## Per phase

| Phase | Component | Params | Resident | Param dtype | Buffer dtype | Device | Load | Freed |
|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3 text encoder | 1720.57 M | 3.441 GB | bfloat16 | float32 | mps | 2.55 s | ✅ residency 0 |
| 2 | MOSS DiT | 1416.05 M | 2.849 GB | bfloat16 | **complex128** | mps | 10.36 s | ✅ residency 0 |
| 3 | DAC VAE (48 kHz, hop 960) | 371.59 M | 0.743 GB | bfloat16 | — | mps | 3.18 s | ✅ residency 0 |

After each phase, `mps_alloc` and `mps_driver` both return to **0.0 GB** and the live-instance count
is **0** — the components are genuinely released, not merely dereferenced.

Tightest moment: Phase 2, where available RAM dipped to **2.60 GB** while the fp32 safetensors state
dict (5.66 GB) and the freshly built model are briefly co-resident before the bf16 cast. Still
1.1 GB above the abort floor. Reducible with an mmap load if ever needed; not necessary at these
margins.

## A corruption bug caught by the dry run

The first attempt cast components with `module.to(device=..., dtype=torch.bfloat16)`. PyTorch warned:

```
UserWarning: Casting complex values to real discards the imaginary part
```

The DiT carries **three complex128 RoPE tables** — `freqs_cis_0 (16384, 22)`, `freqs_cis_1 (16384, 22)`,
`freqs_cis_2 (16384, 20)`. A blanket dtype cast destroys their imaginary component, silently breaking
rotary position encoding and corrupting every generation — with no error, just bad audio.

**Fix:** `cast_params_only()` moves the module to the device and casts **parameters only**, leaving
buffers at their original dtype. Verified: complex128 is fully supported on MPS, and the stock
pipeline also keeps these buffers complex128 on MPS — so this now matches upstream behaviour exactly.

Post-fix verification: `buffer_dtypes: ['torch.complex128']`, `complex_buffers_preserved: true`.

Two lesser bugs were also fixed: a `MemoryTracker._stop` attribute collision with `threading.Thread._stop`,
and a numpy `int64` JSON serialization failure.

## Why bfloat16 costs nothing here

`MossSoundEffectPipeline.__call__` already wraps the entire engine call in
`torch.autocast(device_type, dtype=torch.bfloat16)`. The forward pass therefore computes in bfloat16
regardless of how the weights are stored — upstream's float32 storage for the DiT and VAE merely
doubles resident memory without buying precision at inference. Only the Qwen3 text encoder honoured
`torch_dtype` upstream; the other two are cast in our wrapper.

## Constraints honoured

- MOSS repository **untouched** — `git status --porcelain` empty. All logic lives in
  `moss/scripts/moss_phased.py` and `moss/scripts/moss_memory_test.py`.
- Official checkpoint files unmodified.
- No packages installed.
- No fp16 anywhere (`fp16_used: false`; a hard assert rejects `torch.float16`).
- No CUDA (`cuda_used: false`).
- Device passed explicitly as `"mps"` — never `"auto"`, which upstream resolves to **CPU**.
- `TORCHDYNAMO_DISABLE=1`.
- **No audio generated.** No denoising loop entered, VAE decoder never invoked.

## Files

| Path | Purpose |
|---|---|
| `moss/scripts/moss_phased.py` | phase-separated loaders, bf16 param casting, memory tracker |
| `moss/scripts/moss_memory_test.py` | this dry run (exit 0 = safe, 1 = unsafe) |
| `results/moss_memory_test_result.json` | machine-readable measurements |

Reproduce:

```bash
moss/venv-moss/bin/python moss/scripts/moss_memory_test.py
```

## Configuration staged for the approved generation

Unchanged from the successful Hugging Face Space run — recorded in `moss_phased.py`, not yet executed:

```
prompt   : close-up realistic Foley of a person taking several natural sips of water from a
           ceramic mug, distinct sipping sounds followed by natural swallowing, subtle
           cup-to-lips contact and realistic ceramic handling, continuous recognizable
           drinking action, isolated Foley recording, no speech, no music, no ambience
seconds  : 10          num_inference_steps : 50
cfg_scale: 4           sigma_shift         : 5
seed     : 42          48 kHz mono, PCM16
```

---

**Stopping here as instructed. Awaiting explicit approval before the first local generation.**

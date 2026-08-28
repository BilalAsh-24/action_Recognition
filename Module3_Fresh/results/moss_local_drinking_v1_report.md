# MOSS-SoundEffect v2.0 — First Local Generation

**Date:** 2026-08-25 · **Generations run: exactly 1** · No retries, no alternatives, no sweeps.

# TECHNICAL VERDICT: ✅ PASS

The local phase-separated pipeline produced a valid 48 kHz / mono / PCM16 / 10.000 s WAV with
zero clipping and zero NaN/Inf, at **+0.00 GB swap growth**. The memory guard never tripped.

**Perceptual quality is NOT claimed.** Objective similarity to the Space output is reported below,
but it does not establish perceptual similarity. Your listening verdict decides that.

**Output:** `Module3_Fresh/audio/generated/drinking_moss_v2_local_seed42.wav`
The Space reference WAV (`~/Desktop/audio.wav`, 960044 bytes) was **not** touched.

---

## Configuration (reproducing the successful Space run)

| | |
|---|---|
| Model | MOSS-SoundEffect v2.0, commit `58b20a0`, revision `e35df4d8` |
| Prompt | `close-up realistic Foley of a person taking several natural sips of water from a ceramic mug, distinct sipping sounds followed by natural swallowing, subtle cup-to-lips contact and realistic ceramic handling, continuous recognizable drinking action, isolated Foley recording, no speech, no music, no ambience` |
| Prompt actually sent | above **+ `" duration: 10.0s"`** (upstream `append_duration_suffix=True`, the training-time convention) |
| Negative prompt | `""` |
| Duration | 10.0 s output — engine denoises a **full 30 s latent** internally, then crops |
| Steps / CFG / sigma_shift / seed | 50 / 4 / 5 / 42 |
| denoising_strength / rand_device | 1.0 / `cpu` (seeded generator on CPU, then moved) |
| Device / dtype | **mps** / bfloat16 parameters · no fp16 · no CUDA |
| Latent | `(1, 128, 1500)` — 1,440,000 samples internal, cropped to 480,000 |

## Timing and memory

| | |
|---|---|
| **Total** | **234.81 s** |
| Phase 1 (text encode) | 4.35 s |
| Phase 2 (diffusion) | 219.01 s — **207.35 s** of denoising |
| Phase 3 (VAE decode) | 8.31 s |
| **Peak RAM used** | **12.11 GB** |
| **Min available** | **1.99 GB** (guard floor 1.5 GB) |
| Peak swap | 2.12 GB |
| **Swap growth** | **+0.00 GB** |
| Guard breach | **none** |

Phase separation held: after each phase the component's live-instance count returned to 0 and MPS
allocation to ~0. For contrast, the stock all-resident load measured **+9.80 GB** swap growth.

Available RAM dipped to 1.99 GB at diffusion step 1 — 0.49 GB above the abort floor. That is the
tightest point of the run and worth knowing if the baseline is ever higher than the 5.36 GB it was here.

## Output verification

| Check | Result |
|---|---|
| Sample rate | **48,000 Hz** ✅ |
| Channels | **1 (mono)** ✅ |
| Encoding | **pcm_s16le (PCM16)** ✅ |
| Duration | **10.000 s** / 480,000 samples ✅ |
| Clipping | **0 samples** ✅ |
| NaN / Inf | **0 / 0** ✅ |
| Decode | valid, ffprobe clean ✅ |

## Objective comparison — LOCAL vs SPACE

| Metric | LOCAL | SPACE |
|---|---|---|
| Sample rate / channels / duration | 48 kHz / 1 / 10.0 s | 48 kHz / 1 / 10.0 s |
| RMS | 0.00176 | 0.02666 |
| Peak | 0.0669 (**−23.49 dBFS**) | 0.99997 (−0.0 dBFS) |
| **Crest factor** | **31.62 dB** | **31.48 dB** |
| Dynamic range (p95−p5) | 29.16 dB | 19.91 dB |
| % frames below −20 dB | 88.81 | 96.11 |
| Acoustic onset / offset | 0.261 s / 9.904 s | 0.352 s / 9.776 s |
| Event count | 12 | 7 |
| Event durations | 0.048–0.832 s | 0.048–0.277 s |
| Spectral centroid | 5632 Hz | 4261 Hz |
| Rolloff 95% | 14871 Hz | 15081 Hz |
| Spectral flatness | 0.0298 | 0.0035 |
| Frame self-similarity | 0.9043 | 0.8920 |

### The level difference is a gain offset, not a defect

The local file peaks at **−23.5 dBFS**; the Space file peaks at full scale. **The Space app
normalises its output; our wrapper writes the raw model output unmodified.**

Two measurements support this reading:

- **Crest factors are nearly identical** — 31.62 dB vs 31.48 dB. The waveform's peak-to-RMS
  structure matches; only the absolute level differs.
- **Peak-normalising LOCAL to the Space level (×14.95, +23.5 dB) gives RMS 0.02624 vs the Space's
  0.02666** — a 1.6 % difference.

**Practical consequence: the local WAV will sound very quiet at normal playback volume.** Turn it up
substantially, or normalise it, before judging. I have deliberately not altered the file — you asked
for the generation output, and normalising is a change you should authorise.

### The two files are not the same sample, and were never going to be

Same seed, same settings — but different events at different times. This is expected:

1. **Precision differs.** The Space (ZeroGPU A10G) runs the stock pipeline, which leaves the DiT and
   DAC VAE in **float32**. We cast both to bfloat16 to fit 17 GB. Different numerics → different
   denoising trajectory from the same noise.
2. **The 4 hard-coded `torch.autocast("cuda", dtype=torch.float32)` blocks** in `wan_audio.py`
   silently no-op on a CUDA-less machine, so sections upstream forces to fp32 ran in bf16 here.
3. **CUDA and MPS kernels round differently** even for identical math.

Diffusion is chaotic in its inputs; bit-identical reproduction across CUDA-fp32 and MPS-bf16 is not
achievable. The local output should be judged on its own merits, not on matching the Space sample.

Remaining differences after gain normalisation — more events (12 vs 7), higher centroid
(5632 vs 4261 Hz), higher flatness (0.0298 vs 0.0035) — indicate the local sample is **brighter and
busier**. Whether that is better, worse, or equivalent as drinking Foley is a listening question.

## MPS compatibility workarounds

Two blockers in MOSS's own code stopped it running on Apple Silicon. Both are fixed **in our wrapper
only** — `git status --porcelain` on the MOSS repo is empty, and no checkpoint file was altered.

### 1. `float64` in the timestep embedding

`diffsynth/models/wan_video_dit.py::sinusoidal_embedding_1d` computes in float64:

```
TypeError: Cannot convert a MPS Tensor to float64 dtype as the MPS framework
doesn't support float64. Please use float32 instead.
```

**Fix** (`moss/scripts/mps_compat.py`): run the *same* float64 arithmetic on CPU and move the result
back. The tensor is `(1, freq_dim)`, so the cost is negligible.
**Verified bit-exact vs upstream: max abs diff 0.0, `exact_match: True`.** No precision lost.

Note: the device move and dtype cast must be separate steps — a fused `.to("cpu", torch.float64)`
still attempts the conversion on the MPS device and raises.

### 2. `complex128` RoPE buffers

The DiT registers three complex128 buffers (`freqs_cis_0/1/2`). `model_fn_wan_video` calls
`torch.cat` on them:

```
TypeError: Trying to convert ComplexDouble to the MPS backend but it does not
have support for that dtype.
```

**Fix** (`moss_phased.cast_params_only`): downcast those buffers to **complex64** when targeting MPS.
**Lossless in use** — `rope_apply` only reads `freqs.real` and `freqs.imag` and casts both to
float32, and complex64 reproduces those float32 values bit-for-bit (verified, max abs diff 0.0).

This corrects an earlier claim of mine. During the memory dry run I reported that complex128 "works
on MPS" because `.to("mps")` succeeded. That was wrong: the tensor can sometimes be moved, but any
**operation** on it fails. The dry run never exercised an op, so it did not surface the problem.

### Not a retry

Neither failure produced audio — both crashed before or at diffusion step 0. These are porting fixes
to make MOSS run on MPS at all, made under your standing instruction to implement compatibility
workarounds in the wrapper rather than the repository. **Exactly one generation was executed.**

## Warnings

- `torch.nn.utils.weight_norm is deprecated…` — DAC VAE, benign.
- `torch_dtype is deprecated! Use dtype instead` — transformers 4.57, benign.
- `The following generation flags are not valid and may be ignored: ['output_hidden_states']` — benign.
- No errors during the successful run.

## Files

| Path | Contents |
|---|---|
| `audio/generated/drinking_moss_v2_local_seed42.wav` | the single generated audio |
| `results/moss_local_drinking_v1_generation.json` | config, per-phase timing, memory telemetry |
| `results/moss_local_drinking_v1_analysis.json` | full objective analysis, both files |
| `results/moss_local_drinking_v1_report.md` | this report |
| `moss/scripts/moss_generate_drinking.py` | the generation driver |
| `moss/scripts/mps_compat.py` | MPS shims (repo untouched) |

Not done, as instructed: no synchronisation, no MP4, no walking/pickup/placement, no second sample.

---

**Technical PASS. Stopping for your listening verdict — and please raise the volume substantially
before judging, since the file sits 23.5 dB below the Space reference.**

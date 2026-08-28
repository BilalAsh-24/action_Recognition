# MOSS-SoundEffect v2.0 — Read-Only Preflight

**Date:** 2026-08-25 · **Machine:** Apple M4, 17.18 GB, macOS, MPS available
**Goal:** text → realistic drinking-from-ceramic-cup Foley
**Status:** read-only. Nothing installed, downloaded, generated, or modified.

Everything below was verified against the **official source code and model repository**, not
summaries. Where a claim could not be verified, it is marked as such.

---

## A correction to my previous evaluation

In my earlier text-to-audio comparison I wrote that the model card documents MPS support, quoting
*"switch to 'mps' for apple devices."* **I could not reproduce that from the official sources, and I
now believe it was wrong.** The official model card and the GitHub README both show `device="cuda"`
and nothing else; the install path is `--extra-index-url .../cu128` with a `torch-cu128` extra.

I also estimated the download at 6–8 GB. **The actual repository is 11.2 GB.**

The MPS conclusion below is now based on reading the dispatch code directly, which is stronger
evidence than a doc string — but the earlier claim was unverified and I should not have made it.

---

## A. Official model

| | |
|---|---|
| **Hugging Face** | `OpenMOSS-Team/MOSS-SoundEffect-v2.0` |
| **GitHub** | `OpenMOSS/MOSS-TTS`, subdirectory `moss_soundeffect_v2/` |
| **Official demo** | `huggingface.co/spaces/OpenMOSS-Team/MOSS-SoundEffect-v2.0` (live, ZeroGPU) |
| **Released** | 2026-05-26 |
| **Predecessor** | `OpenMOSS-Team/MOSS-SoundEffect` (v1) — **different architecture**, autoregressive RVQ tokens at 16 kHz. Do not confuse the two. |

## B. License

**Apache 2.0.** Commercial use, redistribution and modification permitted, no revenue threshold.
The only fully permissive licence among every model this project has evaluated.

## C. Architecture

Diffusion Transformer with a **Flow Matching** objective, **Qwen3 text encoder**, **DAC VAE**.
The engine is `WanAudioPipeline`, a vendored DiffSynth-Studio pipeline; the public wrapper is
`MossSoundEffectPipeline` in `pipeline_moss_soundeffect.py`.

Structurally the same family as MMAudio (DiT + flow matching + VAE decode), which ran cleanly on
this machine.

## D. Parameters

**1.3 B** (model card). Consistent with the transformer weight file: 5.66 GB ÷ 4 bytes ≈ 1.41 B
parameters stored in float32.

## E. Checkpoint size

**11.2 GB total**, verified from the repository file listing:

| Component | Size |
|---|---|
| `transformer/diffusion_pytorch_model.safetensors` | **5.66 GB** (fp32) |
| `text_encoder/` (2 shards, Qwen3) | **4.06 GB** |
| `vae/` + `scheduler/` + `tokenizer/` + configs | ~1.5 GB |

A community MLX 4-bit build exists (`mlx-community/MOSS-SoundEffect-MLX-4bit`, 4.7 GB) but **its
version is not documented** and it may be a conversion of v1 (16 kHz), not v2.0. I could not confirm
which. Treat it as unverified.

## F. Dependencies

From the official `pyproject.toml`:

- **`requires-python = ">=3.12"`**
- README pins: `numpy==1.26`, `transformers==4.57`, `torch==2.9`
- Core deps: `diffusers`, `safetensors`, `einops`, `soundfile`, `descript-audiotools` (the DAC VAE),
  `ftfy`, `regex`, `gradio`, `pillow`, `imageio`, `tqdm`, `typing-extensions`
- Extras: `finetune` (accelerate, peft, pandas, torchcodec) — not needed;
  `torch-cu128` (torch/torchaudio/torchvision/torchcodec from the CUDA 12.8 index) — **not usable on
  macOS**
- **`flash-attn`, `xformers`, `triton`, `bitsandbytes` do not appear anywhere in the dependency
  specification.**

There is **no `cpu` or `mps` torch extra**. On macOS we would install torch ourselves from default
PyPI (which is the MPS build) and install the package without the torch extra.

## G. MPS compatibility

**Not officially supported. But the code does not block it, and I verified the three things that
usually do.**

**1. Device string is passed through unchanged.** From `pipeline_moss_soundeffect.py`:

```python
@staticmethod
def _normalize_device(device):
    requested = str(device)
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        print("[Warning] ... Falling back to CPU.")
        return "cpu"
    return requested            # <-- "mps" reaches the engine verbatim
```

Only `"auto"` and unavailable-CUDA are special-cased. Note the fallback is **CPU, not MPS** — so
`device="auto"` would silently give us CPU. We must pass `device="mps"` explicitly.

**2. flash-attn is optional with a real fallback.** In `diffsynth/models/wan_video_dit.py`:

```python
try:    import flash_attn_interface; FLASH_ATTN_3_AVAILABLE = True
except ImportError:                  FLASH_ATTN_3_AVAILABLE = False
...
x = F.scaled_dot_product_attention(q, k, v)     # lines 41 and 71
```

Attention dispatches to `F.scaled_dot_product_attention` when flash-attn and sage-attn are absent.
We already verified SDPA works on MPS in fp32 and bf16 on this machine.

**3. `torch.compile` / Triton is optional.** Documented escape hatch: `TORCHDYNAMO_DISABLE=1`.

**4. The CLI already exposes what we need:** `infer_from_pipeline.py` takes `--device` and
`--torch_dtype {float32,float16,bfloat16}`.

## H. RAM estimate

| Loading strategy | Resident weights |
|---|---|
| All components, bf16 | DiT 2.83 GB + Qwen3 4.06 GB + VAE ~0.75 GB ≈ **7.6 GB** |
| All components, fp32 | ≈ **11.2 GB** — will not fit alongside a 7–8 GB baseline |
| **Phase-separated** (text encode → free → denoise → free → decode) | **max single component ≈ 4.1 GB** |

Plus activations. The latent is always full-length (see L), so attention over a long sequence with
CFG batch 2 is the dominant activation cost — I cannot estimate this reliably without running it.

## I. Precision options

- **bf16** is the documented default (`torch_dtype=torch.bfloat16`) and we verified bf16 works on
  this M4 for matmul, SDPA, RMSNorm, Conv1d, ConvTranspose1d.
- **float32 is an official option** (`--torch_dtype float32`). It fits only with phase separation.
- float16 is offered by the CLI but you have excluded it.

**One real precision hazard.** `pipeline_moss_soundeffect.py` line 209 wraps the whole engine call in
`torch.autocast(device_type, dtype=torch.bfloat16)` — with `device_type` taken from the actual
device, so on MPS this correctly becomes `torch.autocast("mps", bfloat16)`. But inside the engine,
`diffsynth/pipelines/wan_audio.py` has **four hard-coded `torch.autocast("cuda", dtype=torch.float32)`
blocks** (lines 165, 425, 493, 755). On a CUDA-less machine PyTorch disables those and warns, so the
sections that were deliberately forced to fp32 would instead inherit the ambient bf16.

This is not fatal — those blocks are most likely scheduler/VAE math — but it is a genuine numerical
difference from the reference implementation, and worth knowing before blaming the model for a bad
result. It is avoidable without touching the repository by driving `self.engine(...)` from our own
thin script under an fp32 autocast, exactly as we did for MMAudio's `generate()`.

## J. Sample rate

**48 kHz** (`sample_rate = 48000`, overridable from `model_index.json`). Highest of anything
evaluated — above MMAudio's 44.1 kHz, 3× AudioLDM 2 / FoleyCrafter / AudioGen.

## K. Channels

**Mono.** From the source: `num_channels: int = 1` with the comment *"DAC is mono → 1"*.

## L. Maximum duration — and the most important finding in this preflight

**30 seconds.** But the mechanism matters far more than the number:

> From the official docstring: *"`seconds`: Output duration. **The pipeline always denoises a
> fixed-size latent (`max_inference_seconds` seconds)** and the returned tensor is cropped to
> `seconds` worth of samples."*

Confirmed in code:

```python
full_seconds     = int(max_inference_seconds or self.max_inference_seconds)   # 30
num_samples_full = self.sample_rate * full_seconds                            # 48000 * 30
... engine(..., num_samples=num_samples_full, ...)
output_samples   = int(self.sample_rate * seconds)
audio = audio[:, :, :output_samples]                                          # crop
```

**MOSS always generates the full 30 seconds internally and crops.** Duration is communicated to the
model *as text* instead — `append_duration_suffix=True` appends `" duration: 3.0s"` to the prompt,
described in the source as matching the training-time convention.

## M. Recommended duration for our drinking Foley

Because the latent is always full-size, **the duration you request cannot push the model out of
regime.** Request `seconds=10` for a comfortable margin around the 3 s action and crop afterwards, or
request `seconds=3` directly — the denoising is identical either way.

I would still ask for **10 s**: it gives room for the sip/swallow sequence to develop and lets us
choose the best 3 s window, at zero extra compute.

## N. Text-only capability

**Yes, text-only.** No video, image, or audio input exists in the API. Signature:
`__call__(prompt, seconds, num_inference_steps, cfg_scale, sigma_shift, seed, negative_prompt, ...)`.
**A `negative_prompt` is supported** and reaches CFG.

## O. Foley / human-action evidence

**Documented sound categories** include natural environments, urban environments, animals &
creatures, **human actions**, and short musical/percussive clips.

**Official example prompts I could actually verify:**
- *"The crisp, rhythmic click-clack of fast typing on a mechanical keyboard."*
- *"A dog barking loudly in a park."*
- v1 docs: *"fresh snow crunching under footsteps"*, *"clear footsteps echoing on concrete at a
  steady rhythm"*

**I found no official example involving drinking, sipping, swallowing, eating, water, or cup
sounds.** "Human actions" as a category is documented; drinking specifically is not demonstrated.
This is the single biggest unverified assumption in the recommendation, and I am not going to dress
it up: the case for MOSS on drinking is *category-level*, not *example-level*.

## P. MPS risks

| # | Risk | Severity | Note |
|---|---|---|---|
| 1 | 4× hard-coded `autocast("cuda", float32)` in `wan_audio.py` | **Medium-High** | fp32-critical sections silently run in bf16 on MPS |
| 2 | No official MPS testing at all | Medium | we are the test |
| 3 | `device="auto"` falls back to **CPU**, not MPS | Low | pass `"mps"` explicitly |
| 4 | `torch.autocast("mps", bfloat16)` must be supported by torch 2.9 | Low-Medium | present since ~2.5; unverified here |
| 5 | Always denoises 30 s → **slow** | **Medium-High** | see R |
| 6 | `descript-audiotools` (DAC VAE) MPS behaviour unknown | Medium | weight-norm convs + snake activations; probes suggest fine, untested |
| 7 | `torch.compile`/Triton path is CUDA-oriented | Low | `TORCHDYNAMO_DISABLE=1` |
| 8 | Python 3.12 + torch 2.9 not yet on this machine | Low | pyenv has only 3.10.20 |

## Q. Installation requirements (report only — not performed)

1. **`pyenv install 3.12.x`** — not currently present.
2. New isolated venv at `Module3_Fresh/models/venv-moss` — none of `venv-qwen`, `venv-foley`,
   `venv-stable-audio`, `venv-audioldm2`, `venv-mmaudio` touched.
3. `torch==2.9` + `torchaudio` from **default PyPI** (the macOS wheel is the MPS build).
   **Do not use the `cu128` index or the `torch-cu128` extra.**
4. `pip install -e .` **without** the torch extra, then pin `numpy==1.26`, `transformers==4.57`.
5. Download 11.2 GB from `OpenMOSS-Team/MOSS-SoundEffect-v2.0`.
6. Set `TORCHDYNAMO_DISABLE=1`.
7. Nothing to patch — the repository would remain unmodified; any phase separation or fp32 handling
   would live in our own driver script, as with MMAudio.

**Conflicts with existing environments: none.** A separate venv with its own Python 3.12 shares
nothing with the existing 3.10 environments. The only shared resource is the Hugging Face cache,
which is read-only for us and would gain a new 11.2 GB entry. Disk: 205 GB free, ample.

## R. Expected peak memory on our 17 GB M4

With **phase separation** (the strategy already proven here at +0.33 GB swap growth):

| Phase | Resident | Est. peak over baseline |
|---|---|---|
| 1 — Qwen3 text encode | 4.06 GB | ~4.5–5 GB |
| 2 — DiT denoise (bf16) | 2.83 GB | ~3.5–5 GB + long-sequence attention |
| 3 — DAC VAE decode | ~0.75 GB | ~1.5–2 GB |

**Estimated peak ≈ baseline + 5–6 GB.** From a 7 GB baseline that is ~12–13 GB of 17.18 GB — should
fit, with less headroom than MMAudio had. Loading all components at once in bf16 (~7.6 GB) would also
probably fit but is the riskier path.

**Speed is the bigger practical cost.** Because the latent is always 30 s, at the default 100 steps
with CFG that is 200 forward passes of a 1.3 B DiT over a long sequence — roughly two orders of
magnitude more compute than MMAudio's 2.4 s diffusion. I would budget **tens of minutes per
generation** on this M4, and `seconds=3` costs exactly the same as `seconds=30`. Dropping
`num_inference_steps` from 100 to 50 would roughly halve it.

## S. Do I recommend proceeding?

**Yes — but test on the free official Space before downloading 11.2 GB.**

The Space at `huggingface.co/spaces/OpenMOSS-Team/MOSS-SoundEffect-v2.0` is live and running. I
opened it read-only and confirmed the UI exposes exactly the controls that matter: **prompt, duration
slider 1–30 s, num_inference_steps 10–150, cfg_scale 1–8, sigma_shift 0–10, and seed.** I did not
generate anything, per your instruction.

That Space answers the only question that actually matters — *can this model make a recognisable
drinking sound?* — in about two minutes, at zero cost, with no install, no 11.2 GB download, no
Python 3.12, and no MPS risk. Five models have now failed this task after full local installs. It
would be poor judgement to make a sixth 11.2 GB commitment when the decisive experiment is free and
takes minutes.

**Recommended order: you try a drinking prompt on the Space → if it sounds right, we install locally
with confidence → if it does not, we have spent nothing.**

## T. Why MOSS is better (and worse) than what we tested

**Better:**

| | Previously tested | MOSS v2.0 |
|---|---|---|
| Short-duration collapse | Stable Audio / AudioLDM 2 gave **>91 % silence + 30–50 ms clicks** when asked for 2–4.5 s | **Structurally impossible** — always denoises 30 s and crops; duration is text-conditioned |
| Sample rate | 16 kHz (AudioLDM 2, FoleyCrafter, AudioGen) or 44.1 kHz (MMAudio, Stable Audio) | **48 kHz** |
| Licence | all non-commercial except EzAudio | **Apache 2.0** |
| Wrong-action risk | MMAudio scored the wrong action twice, driven by video motion | **No video conditioning** — cannot pick the wrong action |
| Negative prompting | MMAudio yes; FoleyCrafter effectively unused | supported |
| Duration control | fixed 10 s (FoleyCrafter), awkward elsewhere | explicit, 1–30 s |

**On the specific failure pattern you asked about:** the *sparse-clicks-in-near-silence* signature is
the one MOSS is best positioned to avoid, because our leading explanation for it was requesting 2–4.5 s
from models trained at 10–47 s, and MOSS makes that request structurally impossible. *Generic noise*
(FoleyCrafter's failure) and *wrong action* (MMAudio's) are also unlikely — the first came from a
mean-pooled 1-bit conditioning signal, the second from video conditioning MOSS does not have.

What MOSS does **not** guarantee is that its training data contains close-miked human drinking. That
is exactly what the Space will tell you.

**Worse:**

- **11.2 GB download** — the largest of any candidate; nothing is cached.
- **Slowest** — tens of minutes per generation vs MMAudio's 50 seconds.
- **No official MPS support**, versus MMAudio which at least had an MPS branch in `demo.py`.
- **New toolchain** — Python 3.12 and torch 2.9, neither currently installed.
- **No documented drinking/water/eating example** — the human-action claim is category-level only.
- **Mono**, where Stable Audio was stereo.

---

# VERDICT: ✅ RECOMMEND

Recommended **with one condition**: validate on the free official Space first.

MOSS-SoundEffect v2.0 is the strongest remaining candidate on the merits. It is 48 kHz, Apache 2.0,
text-only (so it cannot repeat MMAudio's wrong-action failure), it supports negative prompts, and
— most importantly — its always-denoise-30-s-then-crop design structurally eliminates the
short-duration collapse that we now believe caused the >91 % silence and 30–50 ms clicks in all three
previous text-to-audio attempts. Verified in source: flash-attn, xformers, triton and bitsandbytes are
all absent from its dependencies, attention falls back to MPS-compatible SDPA, and the device string
reaches the engine unmodified, so there is a credible MPS path.

The honest reservations are that MPS is untested by the authors, four hard-coded
`autocast("cuda", float32)` blocks will behave differently on our machine, generation will take tens
of minutes, and **no official example demonstrates drinking specifically**.

Every one of those reservations costs 11.2 GB and a Python 3.12 toolchain to discover locally — or
two minutes on a Space that is already running. Test there first.

**Awaiting your explicit approval before installing anything.**

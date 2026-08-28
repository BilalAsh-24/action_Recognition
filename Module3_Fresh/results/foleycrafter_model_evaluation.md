# FoleyCrafter — Model Evaluation for Module 3

**Date:** 2026-08-25
**Target machine:** Apple M4, 17.18 GB unified memory, macOS (Darwin 25.2.0)
**Candidate role:** primary audio-generation model for Module3_Fresh
**Test case:** `drink from cup`, 5.50 – 8.50 s (3.00 s)
**Status:** read-only evaluation — nothing installed, downloaded, generated, or modified.

---

## How this evaluation was performed

- Source read at `03-FoleyCrafter-Test/foleycrafter` (upstream `open-mmlab/FoleyCrafter`, commit
  `b4526d1`) — **read-only**.
- `venv-foley` queried read-only for installed versions. Not activated, not modified.
- Prior experiment artefacts recovered from `03-FoleyCrafter-Test/action-recognition/results/`:
  `foley_integration_test/`, `foley_quality_experiment/`, `listening_comparison/`,
  `synchronization_test/`.
- **The two existing WAVs were re-analysed independently** using Module3_Fresh's own environment,
  rather than accepting the previous run's conclusions. This matters — see §17.

Nothing outside `Module3_Fresh/results/` was written.

---

## 1. Existing installation and checkpoint availability

**Fully installed and complete.** `venv-foley` exists with a working dependency set, and every
checkpoint is present in the shared Hugging Face cache.

| Component | Source | Size | Present |
|---|---|---|---|
| `temporal_adapter.ckpt` | `ymzhang319/FoleyCrafter` | 4.34 GB | yes (symlink → HF cache) |
| `timestamp_detector.pth.tar` | `ymzhang319/FoleyCrafter` | 377 MB | yes (symlink) |
| `semantic/semantic_adapter.bin` | `ymzhang319/FoleyCrafter` | 89 MB | yes (symlink) |
| `vocoder/vocoder.pt` + config | `ymzhang319/FoleyCrafter` | 55 MB | yes (symlink) |
| Auffusion base (UNet/VAE/text encoder) | `auffusion/auffusion-full-no-adapter` | 4.0 GB | yes (HF cache) |
| IP-Adapter CLIP image encoder | `h94/IP-Adapter` | 2.4 GB | yes (HF cache) |

**Total cached: ~10.9 GB.** The `checkpoints/` directory holds symlinks into
`~/.cache/huggingface/hub`, so the weights are shared, not duplicated.

**One important caveat about the existing install:** the repository has **local modifications to
four source files**, without which it does not run on this machine at all:

```
 M app.py
 M foleycrafter/pipelines/auffusion_pipeline.py
 M foleycrafter/utils/util.py
 M inference.py
```

The patches are: `map_location="cpu"` on two `torch.load` calls (checkpoints were saved on CUDA
machines), making `decord` an optional import (it does not build on Apple Silicon), MPS device
auto-detection, and — most significantly — **forcing the onset/timestamp detector onto CPU because
`Conv3d` is unsupported on MPS**. A clean Module3_Fresh install would need the same four patches
re-applied.

## 2. Can the existing checkpoint be reused?

**Yes — completely, with zero downloads.** All weights live in the shared HF cache and resolve by
repo id, so a fresh clone in `Module3_Fresh/` would find them automatically. The `checkpoints/`
symlink layout can be reproduced with `huggingface-cli download` hitting cache, or the four
symlinks recreated directly.

**Reuse is safe and read-only** — the cache is shared with the Auto-AVSR and MMAudio work, and
nothing here writes to it.

## 3. M4 / MPS compatibility

**Works, but only with patches, and the temporal branch cannot run on MPS.**

| Component | Device | Note |
|---|---|---|
| UNet, VAE, ControlNet, text encoder, CLIP image encoder, vocoder | `mps` | verified working in both prior runs |
| **Timestamp detector (`VideoOnsetNet`)** | **`cpu` — forced** | uses `Conv3d`, unsupported on MPS in torch 2.2.2 |

From the applied patch in `inference.py`:

> `# onset detector uses Conv3d, which is unsupported on MPS (torch 2.2.2); keep it on CPU regardless of config.device`

So the branch responsible for **temporal alignment** — the thing that would make a sip land on the
right frame — is the one branch that cannot use the GPU. It also forces a device round-trip for the
video frames each run.

Upstream provides no MPS support statement; the README documents CUDA usage only. MPS here is
entirely a local adaptation.

## 4. Actual RAM requirement on this 17.18 GB M4

**Measured, from the two prior runs — and it is the worst memory profile of any model tried in this
project.**

| | Run 1 (integration) | Run 2 (quality) |
|---|---|---|
| Baseline used | 6.76 GB | 9.04 GB |
| Baseline swap | 5.15 GB | 4.69 GB |
| After model load | 7.72 GB | 5.49 GB |
| Before generation | 10.37 GB | 10.63 GB |
| **Peak used** | **13.21 GB** | **15.07 GB** |
| **Min available** | 1.98 GB | **0.49 GB** |
| **Peak swap** | **11.19 GB** | **14.77 GB** |
| **Swap growth** | **+6.04 GB** | **+10.08 GB** |
| Outcome | `FOLEY_INTEGRATION_TEST_PASS` | **`ABORTED_MEMORY_GUARD`** |

Run 2 breached the same 1.5 GB guard we specified for MMAudio: *"available 1.25GB < 1.5GB"*.

**The swap figures are the real story.** +6 GB and +10 GB of swap growth is sustained thrashing, not
a brief transient. For comparison, the MMAudio attempt that we treated as a failure peaked at
**3.77 GB** swap. FoleyCrafter's measured profile is roughly **four times worse**.

Why it is so heavy — all components are resident simultaneously, and there is no phase separation
available:

- Auffusion UNet + VAE + CLIP text encoder (~4.0 GB of weights)
- ControlNet (a copy of the UNet encoder)
- IP-Adapter CLIP-H image encoder (~2.4 GB)
- Vocoder
- `read_frames_with_moviepy` loads **every** frame into a Python list, then subsamples to 150.
  At 720p that is a 414 MB uint8 array, immediately promoted to **1.66 GB of float32**
  (`torch.FloatTensor(frames)`), and then all 150 frames are pushed through CLIP-H in one batch.

## 5. Required versions

Read from the working `venv-foley`:

| Package | Version | Note |
|---|---|---|
| Python | 3.10 | |
| **torch** | **2.2.2** | old; `Conv3d` on MPS unsupported at this version |
| torchvision | 0.17.2 | must match torch 2.2.2 |
| torchaudio | 2.2.2 | must match torch 2.2.2 |
| **numpy** | **1.26.4** | 1.x required |
| **diffusers** | **0.25.1** | pipeline is written against this API |
| **transformers** | **4.30.2** | **from mid-2023** |
| accelerate | 0.25.0 | |
| soundfile | 0.12.1 | |
| imageio | 2.33.1 | |
| moviepy | (installed) | used for frame reading |
| decord | **absent** | does not build on Apple Silicon; patched to optional |

This stack is **old and tightly coupled**. `transformers 4.30.2` with `diffusers 0.25.1` is a
three-year-old combination that cannot be upgraded without rewriting pipeline code, and it pins
torch to 2.2.x — which is precisely why the `Conv3d`/MPS limitation cannot simply be fixed by
upgrading.

## 6. CUDA-only dependencies

**None that block execution.** The two `torch.load` calls that failed were CUDA-*saved* checkpoints,
fixed with `map_location="cpu"`. `xformers` is not installed and not required. No flash-attn, no
triton, no custom CUDA kernels.

The only genuine hardware limitation is `Conv3d` on MPS, which is a **PyTorch/MPS** gap, not a CUDA
dependency.

## 7. Can inference run entirely on MPS?

**No — but the exception is small in compute terms.** Everything runs on MPS except the timestamp
detector, which is pinned to CPU. That model is only 377 MB and runs once per clip, so the
performance cost is minor. The conceptual cost is larger: the temporal-alignment branch is the
degraded one.

## 8. Does the model accept the actual video as conditioning?

**Yes, but the conditioning is much weaker than it first appears.** Reading `inference.py`, video
reaches the model through exactly two channels:

**Semantic branch (IP-Adapter):**
```python
image_embeddings = image_encoder(**images).image_embeds
image_embeddings = torch.mean(image_embeddings, dim=0, keepdim=True).unsqueeze(0).unsqueeze(0)
```
CLIP embeddings for all 150 frames are **mean-pooled into a single vector**. Every trace of
temporal ordering, motion, and event structure is averaged away. The model sees the semantic
equivalent of one blurred frame.

**Temporal branch (ControlNet):**
```python
time_condition = [-1 if preds[0][...] < 0.5 else 1 for i in range(int(1024/10*duration))]
time_condition = time_condition + [-1] * (1024 - len(time_condition))
```
The onset detector's output is **thresholded to binary ±1** and repeated to fill a 256×1024 image.
The ControlNet therefore receives a **1-bit-per-timestep on/off gate** — not motion features, not
velocity, not visual detail.

So the answer to "does it see the video" is: it sees *one averaged semantic vector* plus *a binary
activity mask*. That is a genuinely weak conditioning signal for distinguishing "drinking from a
cup" from any other hand-to-face action.

## 9. Can text prompts control the generated Foley?

**In principle yes; in this project's measured evidence, barely.**

The prompt reaches the Auffusion UNet through the CLIP text encoder, and `--nprompt` supplies a
negative prompt. But the prior quality experiment was explicitly designed as a controlled test —
*only the prompt changed*, seed/steps/scales/checkpoints/input all identical — and the result was:

| Metric | Run 1 (short prompt) | Run 2 (long, detailed prompt) |
|---|---|---|
| Spectral centroid | 2985 Hz | **2984 Hz** |
| Rolloff (95%) | 6863 Hz | 6708 Hz |
| Spectral flatness | 0.120 | 0.126 |
| Noise floor (p10) | 0.00057 | **0.00923 (16× higher)** |
| Silence below 1% peak | 38.1 % | **18.2 %** |

**The elaborate prompt changed the timbre by 1 Hz of spectral centroid.** What it *did* change was
the envelope — and in the wrong direction. Run 2's prompt explicitly asked for *"clean isolated
Foley... no background noise"* and produced a result with a **16× higher noise floor and half the
silence**. Text conditioning is present but is not steering the output in the way the prompt asks.

## 10. Is temporal alignment supported?

**Nominally yes, functionally weak.** FoleyCrafter's README advertises *"Temporal Alignment with
Visual Cues"*, and `--temporal_scale` exposes the ControlNet strength.

Three findings temper this:

1. The conditioning is the binary gate described in §8 — an on/off mask, not motion features.
2. Both prior runs used **`temporal_scale = 0.2`**, i.e. the temporal ControlNet turned down to 20%.
3. The measured onset in both outputs was **0.000 s** — sound begins at the very first sample. The
   synchronization test's own note records this:
   > *"measured WAV internal onset = 0.0000s, so placement at 5.500s already yields perceptual onset 5.500s"*

An audio clip whose energy starts at sample zero and never stops has no internal temporal structure
to align. The sync test's excellent-looking numbers (onset error −10 ms, correlation 0.9993) measure
**where we pasted the clip**, not whether the model placed a sip at the right moment.

## 11. Can it generate a drinking-from-cup sound?

**On this project's evidence: it did not.** See §17 for the full analysis. Both attempts produced
broadband noise beds rather than recognisable drinking.

## 12. Is the 3-second 5.5–8.5 s segment suitable?

**This is a significant architectural mismatch.** From `inference.py`:

```python
sample = pipe(..., height=256, width=1024, ...)
audio = vocoder.inference(audio, lengths=160000)[0]   # 160000 / 16000 = 10.0 s
audio = audio[: int(duration * 16000)]                 # crop to 3.0 s
```

**FoleyCrafter always generates exactly 10 seconds, then throws away everything past the requested
duration.** For our 3 s segment:

- We pay the **full 10-second compute and memory cost** for 3 seconds of output.
- The model composes a 10-second event structure and we keep an arbitrary **first 30%**. If the
  model places its sip at t = 6 s within its 10 s canvas, we discard it and keep whatever ambience
  happened to occupy the opening.
- The temporal condition is live for only `int(1024/10 × 3.0)` = **307 of 1024** columns; the
  remaining 717 are padded `-1` ("no onset"). So 70% of the generation is explicitly conditioned as
  inactive, and the model still fills the retained 30% with continuous sound.

This is a plausible mechanistic explanation for the observed "starts at 0.000 s, never stops"
behaviour, and it is structural rather than a tuning problem.

## 13. Recommended inference settings for a first test

Provided for completeness — see the verdict before using them.

| Setting | Value | Rationale |
|---|---|---|
| `--prompt` | short and concrete | long prompts measurably did not help (§9) |
| `--nprompt` | `"music, speech, noise, hiss"` | prior runs used `""`; worth actually exercising |
| `--seed` | 42 | consistency with prior runs |
| `--num_inference_steps` | 25 | upstream default; both prior runs used it |
| `--semantic_scale` | 1.0 | upstream default |
| **`--temporal_scale`** | **0.75 – 1.0, not 0.2** | prior runs crippled the one branch that creates temporal structure |
| Input segment | **10 s, not 3 s** | the model generates 10 s regardless; give it the whole clip and crop afterwards |
| Device | `mps` (detector on CPU) | forced |

The two changes worth making relative to the prior runs are **raising `temporal_scale`** and
**feeding the full 10-second video** instead of a 3-second crop. Both target the failure mode
directly rather than re-rolling the prompt, which has already been shown not to work.

## 14. Expected output sample rate / channels

**16,000 Hz, mono, PCM_16.** This is fixed by the Auffusion vocoder and is not configurable — the
mel configuration and `lengths=160000` are baked into the checkpoint.

**This is a hard quality ceiling.** Nyquist is 8 kHz. Sip, swallow, and ceramic-contact sounds carry
substantial energy above 8 kHz — that is much of what makes Foley read as "crisp" and "close-miked".
For reference, MMAudio produces 44.1 kHz. Any 16 kHz output will sound dull and slightly muffled
next to the rest of the project's audio regardless of how good the generation is.

## 15. Expected generation time

Measured, 3 s output, 25 steps, MPS:

| | Model load | Generation | Total wall |
|---|---|---|---|
| Run 1 | 16.25 s | 62.99 s | 109.99 s |
| Run 2 | 17.44 s | 113.05 s | 165.01 s |

The variance is memory-driven: run 2's first diffusion step took **62 s** versus run 1's 23 s,
because the machine was already swapping. Steady-state is ~1.4 s/step once resident.

**Budget 2–3 minutes per generation**, worse under memory pressure. Note this buys 3 seconds of
audio from 10 seconds of computation (§12).

## 16. Memory safety strategy

Honestly assessed, the options are limited:

| Technique | Availability |
|---|---|
| Phase separation (load/free components in stages) | **Not available.** The diffusers pipeline needs UNet + VAE + ControlNet + text encoder + IP-Adapter co-resident for every denoising step. There is no disjoint-phase structure to exploit, unlike MMAudio. |
| `enable_attention_slicing()` / `enable_vae_slicing()` | Available via diffusers 0.25.1 — worth using, modest saving |
| `enable_model_cpu_offload()` | Available in principle, but relies on `accelerate` hooks that are unreliable on MPS and would add large per-step transfers |
| fp16 / bf16 | Risky on this old stack; the vocoder and VAE are sensitive, and torch 2.2.2 MPS bf16 coverage is weaker than 2.7's |
| Reduce frame memory | **Real and worthwhile** — cap `max_frame_nums` and downscale frames before `torch.FloatTensor()`; saves most of the 1.66 GB float32 blowup |
| Lower host baseline | Necessary regardless |
| Guard | 1.5 GB available floor, plus a swap-growth ceiling — the swap number is the one that actually predicts trouble here |

Even with all of these, the ceiling is set by co-resident weights, and the measured evidence is a
run that breached the guard from a 9.04 GB baseline. Launching would require a baseline near 4–5 GB
and would still be tight.

---

## 17. The previous FoleyCrafter experiment — independent re-analysis

This is the section that decides the verdict. Both prior runs targeted **exactly our test case**:
`drink from cup`, 5.50–8.50 s, from Module 2's confirmed segment.

### What was run

| | Run 1 — integration test | Run 2 — quality experiment |
|---|---|---|
| Checkpoint | FoleyCrafter + Auffusion full-no-adapter | identical |
| Prompt | *"realistic sound of a person drinking from a cup, subtle cup and drinking sounds, natural indoor recording"* | *"Natural realistic close-up Foley recording of a person drinking from a ceramic cup indoors... no music, no speech, no background noise, no exaggerated effects."* |
| Negative prompt | `""` | `""` |
| Seed / steps | 42 / 25 | 42 / 25 (identical) |
| Semantic / temporal scale | 1.0 / 0.2 | 1.0 / 0.2 (identical) |
| Input | 3.0 s segment, **video-only** (`-an`, verified: no audio stream) | identical |
| Output | 3.0 s, 16 kHz mono | identical |
| Recorded result | `FOLEY_INTEGRATION_TEST_PASS` | **`ABORTED_MEMORY_GUARD`** |

The source audio genuinely never reached the model — I re-verified the input segment has zero audio
streams. The poor output is not contamination; it is the model's actual behaviour.

### Independent acoustic analysis

Re-measured from the WAVs in Module3_Fresh's own environment:

| Metric | Run 1 | Run 2 | What a real 3 s drink should show |
|---|---|---|---|
| Dynamic range (p95−p5 frame dB) | 42.5 dB | **11.7 dB** | large — 30 dB+ |
| Frames below −20 dB | 34.6 % | **0.0 %** | substantial quiet between events |
| Frames below −30 dB | 29.8 % | **0.0 %** | some |
| Spectral flatness | 0.120 | 0.126 | low (<0.05) for structured Foley |
| Frame-to-frame spectral self-similarity | 0.877 | 0.864 | low — a drink changes character |
| Detected onsets in 3 s | 19 | **25** | ~2–5 (cup lift, sip, swallow, set-down) |
| Mean onset spacing | 0.156 s | 0.116 s | 0.3–1.0 s |
| Per-second RMS | 0.0298 / 0.0449 / 0.0015 | 0.0275 / 0.0206 / 0.0142 | strongly event-shaped |
| Spectral centroid | 2985 Hz | 2984 Hz | — |

**Run 2 is a continuous broadband noise bed.** Zero frames below −20 dB, 11.7 dB of dynamic range,
and 25 "onsets" at 8.6 Hz spacing is not drinking — it is texture. The spectrogram confirms it:
uniform full-band energy across the entire 3 seconds with regular vertical striping and no event
envelope whatsoever.

**Run 1 is better but still not drinking.** It has real dynamic range (42.5 dB) and genuinely decays
to near-silence in the final second — the spectrogram shows broadband energy that fades around the
two-thirds mark. But 19 onsets at 0.156 s spacing describes a granular crackle, and the flatness of
0.120 with 0.877 self-similarity still says "noise" rather than "discrete liquid and ceramic
events".

### Were the previous results good or bad?

**Bad — both of them, and the second is clearly worse than the first.**

This needs saying plainly because the artefacts are easy to misread:

- **`FOLEY_INTEGRATION_TEST_PASS` was a plumbing pass, not a quality pass.** Reading its own
  verification block, it checked: file exists, correct size, correct format, correct sample rate,
  correct duration, non-empty, finite, plausible RMS. Every one of those is satisfied by three
  seconds of hiss. No quality criterion was ever applied.
- **Run 2's WAV exists even though the run aborted.** The file was written *before* the guard breach
  was recorded, so `new_drink_from_cup.wav` being present does not mean the run succeeded — the
  recorded status is `ABORTED_MEMORY_GUARD`.
- **The synchronization test's excellent numbers measure the wrong thing.** Onset error −10 ms and
  correlation 0.9993 confirm that ffmpeg placed the clip where we asked. They say nothing about
  whether the audio contains a sip, and the test's own note records the clip's internal onset as
  0.0000 s — meaning there was no event to align.
- **The controlled prompt experiment produced a regression.** Same seed, same everything but the
  prompt, and the more careful prompt made the output measurably worse on every envelope metric.

### Human-quality verdict on the existing audio

**Category 3 — not recognisable as drinking**, for both runs. Run 1 has more plausible envelope
shape and might be charitably described as Category 2/3 borderline; Run 2 is unambiguously
Category 3.

---

## Risks

| # | Risk | Severity |
|---|---|---|
| 1 | Two attempts at this exact action both produced noise beds | **High** |
| 2 | 16 kHz mono ceiling — unfixable, and below the rest of the pipeline | **High** |
| 3 | Measured swap growth +6 to +10 GB; one run already breached the 1.5 GB guard | **High** |
| 4 | No phase separation possible — the MMAudio memory fix has no analogue here | **High** |
| 5 | Video conditioning is mean-pooled CLIP + a binary gate | **High** |
| 6 | Always generates 10 s and crops; 3 s costs full price and keeps an arbitrary slice | Medium-High |
| 7 | Prompt control demonstrated to be weak on exactly this action | Medium-High |
| 8 | Temporal branch forced to CPU (`Conv3d` unsupported on MPS) | Medium |
| 9 | Old pinned stack (torch 2.2.2 / transformers 4.30.2 / diffusers 0.25.1), not upgradable | Medium |
| 10 | Requires re-applying 4 source patches in any fresh install | Low-Medium |
| 11 | Checkpoints are non-commercial-licensed research weights | Low (non-technical) |

## What is genuinely good about FoleyCrafter

Stated fairly, because it is not nothing:

- **It is installed and it works.** Zero downloads, zero setup risk, a known-good venv, and a
  reproducible invocation.
- **It completes.** Both runs produced valid, finite, correctly-formatted 3 s WAVs.
- **It is fast enough** at ~2–3 minutes per generation.
- **The integration scaffolding around it already exists** — Module 2 → prompt → segment → WAV →
  muxed MP4 was demonstrated end to end.

If the goal were "produce some audio in the pipeline shape", FoleyCrafter already does that. The
problem is the audio.

---

## Final verdict

# ❌ DO NOT RECOMMEND FOLEYCRAFTER

Not as the primary Module 3 model.

The decisive evidence is not architectural speculation — it is that **FoleyCrafter has already been
given this exact task twice and failed both times.** Same action, same interval, same Module 2
segment, correct video-only input, sensible prompts, upstream-default sampler settings. Both outputs
are broadband noise beds rather than recognisable drinking, and the more carefully-prompted second
attempt was measurably *worse*: 11.7 dB of dynamic range, not one frame below −20 dB, and a 16×
higher noise floor than the run whose prompt said less.

The architecture explains why, and the explanation is not tunable:

- Video reaches the model as **one mean-pooled CLIP vector plus a 1-bit-per-timestep gate**. That is
  not enough signal to distinguish drinking from any other hand-to-face motion.
- The model **always generates 10 seconds and crops**, so a 3 s request keeps an arbitrary opening
  slice of a texture composed for a different timeline.
- Output is **locked at 16 kHz mono** — an unfixable ceiling below the rest of the pipeline.

The memory position also deserves stating directly, because MMAudio was set aside partly on memory
grounds: **FoleyCrafter's measured memory behaviour is substantially worse.** Peak swap of 11.19 GB
and 14.77 GB, with swap growth of +6.04 GB and +10.08 GB, against MMAudio's 3.77 GB — and one
FoleyCrafter run already breached the same 1.5 GB guard. Crucially, MMAudio's problem had an
identified fix (phase-separated loading via public constructor flags), whereas FoleyCrafter's
diffusers pipeline requires all components co-resident for every denoising step and offers no
equivalent remedy.

I want to be careful not to overstate one thing: this verdict rests on **two** generations, not a
sweep. It is possible that raising `temporal_scale` from 0.2 to ~0.8 and feeding the full 10-second
clip instead of a 3-second crop would improve matters — both prior runs got those two choices wrong,
and §13 records the settings if you want to test it. But that would be a rescue attempt on a model
that is still capped at 16 kHz and still conditions on a mean-pooled frame vector. The ceiling would
remain low even if the rescue worked.

**Recommendation:** keep FoleyCrafter as a **working fallback and baseline** — it is installed, it
runs, and it is useful for A/B comparison — but do not build Module 3 on it.

**Suggested next step:** rather than adopting FoleyCrafter, reconsider MMAudio with the
phase-separated strategy, which is fully implemented and preflight-verified in `Module3_Fresh/` and
was never actually executed. Its single blocker was a host baseline of 8.24 GB against a ≤5 GB
requirement — a condition that clears by closing applications, and one that FoleyCrafter would not
clear either. If MMAudio is genuinely off the table, the honest position is that **no evaluated
model currently has a demonstrated path to good 44.1 kHz drinking Foley on this machine**, and that
is worth deciding deliberately rather than by default.

---

*Evaluation complete. Read-only: nothing installed, downloaded, generated, or modified. No existing
WAV, MP4, environment, checkpoint, or Module 2 file was touched.*

# Text-to-Audio Model Evaluation — Drinking Foley on Apple M4 (17 GB)

**Date:** 2026-08-25
**Target:** `text prompt → realistic drinking Foley` (no video conditioning required)
**Constraint:** must run locally on Apple M4, 17.18 GB unified memory
**Status:** read-only evaluation — nothing installed, downloaded, or generated.

---

## First: what the five failures actually looked like

Before recommending a sixth model, I re-read the measured results from the five already tried. They
did **not** all fail the same way, and the pattern matters.

| Model | Output | Silence | Events | Failure mode |
|---|---|---|---|---|
| Stable Audio Open 1.0 (`drinking_v2`) | 44.1 kHz stereo, 4.5 s | **96.2 %** | 2 events, **0.04 s each** | isolated clicks |
| Stable Audio (`single_sip`) | 44.1 kHz stereo, 2.0 s | **93.0 %** | 2 events, **0.03–0.04 s** | isolated clicks |
| Stable Audio Open Small (`3B auto`) | 44.1 kHz stereo, 3.0 s | **95.6 %** | — | near-silence |
| AudioLDM 2 | 16 kHz mono, 10 s | **91.9 %** | events of **0.03 s** | isolated clicks |
| FoleyCrafter | 16 kHz mono, 3.0 s | **0 %** below −20 dB | 25 "events" at 8.6 Hz | continuous noise bed |
| MMAudio v1 / v2 | 44.1 kHz mono | 86 % / 96 % | 5 / 1 | sound on the wrong action |

**The three text-to-audio models all failed identically: >91 % silence punctuated by 30–40 ms
clicks.** That is a strikingly consistent signature, and it is worth naming a likely cause before
blaming the models.

**Every one of those runs requested 2.0–4.5 s of audio.** Stable Audio Open 1.0 is trained to
generate up to **47 s**; Stable Audio Open Small up to **11 s**; AudioLDM 2 at **10 s**. Asking a
model trained at 10–47 s to produce 2–4.5 s pushes it far outside its training regime, and
"near-silence with a couple of impulses" is a characteristic out-of-regime output.

I cannot prove this without generating, and I am not proposing to. But it means **the next attempt
should generate at the model's native duration (~10 s) and crop afterwards**, regardless of which
model is chosen. If that is not done, a sixth model may well reproduce the same signature.

---

## Candidates evaluated

Only models with public weights, local inference, and a plausible fit for a 17 GB M4 were considered.
Popularity was not a criterion — MusicGen, Bark, and the various TTS models were excluded as
category mismatches, and HunyuanVideo-Foley / LTX-Foley were excluded as video-conditioned.

| | **MOSS-SoundEffect v2.0** | **AudioGen medium** | TangoFlux | EzAudio |
|---|---|---|---|---|
| **1. Human Foley** | explicit "**Human actions**" category | trained for environmental/Foley | general T2A | "sound effects" focus |
| **2. Sipping/water** | plausible (human-action class) | plausible (AudioSet lineage) | plausible | plausible |
| **3. Text-to-audio** | yes, Qwen3 text encoder | yes, T5 conditioning | yes, FLAN-T5 | yes |
| **4. MPS** | **documented** — *"switch to 'mps' for apple devices"* | community-proven, no official support | via diffusers/torch | via torch |
| **5. Est. RAM** | **~5–7 GB** (bf16) | ~6–8 GB | ~4–5 GB | ~4–6 GB |
| **6. Size** | 1.3 B params, **~6–8 GB** download (or 4.7 GB MLX-4bit) | 1.5 B, **~6 GB** | 515 M, ~2–3 GB | ~1 B, ~4 GB |
| **7. Sample rate** | **48 kHz** | **16 kHz** | 44.1 kHz | 24 kHz |
| **8. Channels** | not documented (assume mono/stereo TBC) | mono | **stereo** | mono |
| **9. Local** | yes | yes | yes | yes |
| **10. License** | **Apache 2.0 — commercial OK** | CC-BY-NC-4.0 | Stability Community + WavCaps **non-commercial** | MIT |
| **11. Weights public** | yes (HF) | yes (HF) | yes (HF) | yes (HF) |
| **12. Documented Foley examples** | yes — footsteps, snow crunch, thunder, urban, creatures | yes — footsteps, dog barking, sirens | AudioCaps-style | sound-effect demos |
| **13. Multi-second continuous** | **yes — up to 30 s, duration-controllable** | yes, but autoregressive and slow | up to 30 s | ~10 s |

---

## Best candidate: **MOSS-SoundEffect v2.0** (OpenMOSS)

`OpenMOSS-Team/MOSS-SoundEffect-v2.0`

**Architecture:** Diffusion Transformer trained with a Flow Matching objective, Qwen3 text encoder,
DAC VAE. 1.3 B parameters.

| Requested item | Answer |
|---|---|
| **Estimated RAM** | **~5–7 GB** at bf16 — 1.3 B DiT ≈ 2.6 GB, plus Qwen3 text encoder and DAC VAE. Comfortably within our proven envelope (the successful MMAudio runs peaked at 9.25–10.25 GB). |
| **Estimated download** | **~6–8 GB** for the full-precision HF repo; a community **MLX 4-bit build is 4.7 GB**. |
| **MPS compatibility** | **Officially noted** — the model card's inference example carries the comment to *"switch to 'mps' for apple devices"*. |
| **Output sample rate** | **48 kHz** — the highest of any candidate, above MMAudio's 44.1 kHz and 3× AudioLDM 2 / FoleyCrafter / AudioGen. |
| **License** | **Apache 2.0.** Commercial use, redistribution and modification permitted, with no revenue threshold. |

### Why it is specifically appropriate for drinking Foley

1. **"Human actions" is a first-class documented category.** Its own documentation groups sounds into
   natural environments, urban environments, animals & creatures, and **human actions**, with worked
   Foley examples (snow crunching underfoot, footsteps echoing on concrete). Drinking is a human
   action Foley event. None of the other candidates advertise that category explicitly — they are
   general text-to-audio models that happen to cover sound effects.

2. **Duration is a controlled parameter, up to 30 s.** This directly addresses the failure signature
   above: we can generate 10 s inside the model's comfortable range and crop to 3 s, rather than
   asking for 3 s and receiving silence plus clicks. Stable Audio and AudioLDM 2 gave us no clean way
   to do this at the durations we requested.

3. **48 kHz materially matters for this particular sound.** Sipping, swallowing and wet mouth
   transients carry substantial energy above 8 kHz — exactly the band that 16 kHz models (AudioGen,
   AudioLDM 2, FoleyCrafter) cut off entirely. This is the difference between a sip that sounds
   close-miked and one that sounds muffled.

4. **The architecture is one we have already proven runs well on this machine.** DiT + flow matching
   + a VAE decoder is structurally the same shape as MMAudio, which ran cleanly on MPS at
   +0.33 GB swap growth. The mechanical risk is low; we know this class of model behaves.

5. **Apache 2.0 removes a constraint everything else imposes.** MMAudio, FoleyCrafter, AudioGen and
   TangoFlux are all non-commercial. If Module 3 ever ships, this is the only candidate that does not
   need relicensing.

### Honest risks

- **Python 3.12 + torch 2.9 required.** Our existing environments are Python 3.10.20 / torch 2.7.1,
  and pyenv currently has only 3.10.20 installed — a 3.12 install would be needed. New isolated venv,
  as always.
- **The repo's install docs are CUDA-first** (`cu128` wheels, Triton/TorchDynamo `torch.compile`).
  MPS is supported in the API but the compile path is not. The documented escape hatch is
  `TORCHDYNAMO_DISABLE=1`, which we would set from the start.
- **It is a recent model** with less community MPS validation than AudioGen. Mono/stereo output is
  not clearly documented.
- **Nothing is cached.** Unlike MMAudio and FoleyCrafter, this is a genuine 6–8 GB download.

---

## Second-best candidate: **AudioGen medium** (Meta / AudioCraft)

`facebook/audiogen-medium` — 1.5 B params, 16 kHz mono, CC-BY-NC-4.0.

**Its single strongest argument is that it is architecturally unlike everything that has failed.**
AudioGen is an **autoregressive transformer over EnCodec tokens**. All five failed models were latent
diffusion or flow matching. Every failure so far has produced the same diffusion-flavoured signature —
sparse impulses in near-silence, or a stationary noise bed. An autoregressive token model fails
differently, and after five same-family failures that diversification has real value.

It is also the most explicitly Foley-trained model available, with documented everyday-sound examples
(footsteps in a corridor, sirens, dog barking), and it has a well-trodden community path to MPS.

**Why it is second and not first:**

- **16 kHz mono** — the same ceiling that made FoleyCrafter's output unusable, and it removes exactly
  the high-frequency band that makes a sip read as wet and close.
- **CC-BY-NC-4.0** — non-commercial.
- **`audiocraft` declares `xformers` as a dependency**, which you have asked me not to install.
  Workarounds exist (it is only needed for CUDA), but it is real friction on a fresh install.
- **Autoregressive means slow** — community reports ~60 s of wall time for 5 s of audio on an M2 Max.

If the 48 kHz MOSS attempt fails in the same way as the others, AudioGen is the right next move
precisely *because* it is a different class of model.

---

## Why not the others

**TangoFlux** (515 M, 44.1 kHz stereo, fast) looks attractive on paper and I nearly ranked it second.
Two things pushed it down. It **reuses the Stable Audio Open VAE**, and Stable Audio Open has already
failed this exact task twice with the clicks-in-silence signature — sharing the decoder lineage makes
it a poor bet against *this specific* failure. And its licence is the Stability AI Community License
plus a WavCaps academic-only restriction, so it is research-only despite frequently being described
as open.

**EzAudio** has the cleanest licence (MIT) and a sensible architecture (DiT with a 1-D waveform VAE,
no separate vocoder). But its published specifications are thin — parameter count and sample rate are
not clearly documented — and at 24 kHz it sits below MOSS on the axis that matters most here. A
reasonable third choice.

**HunyuanVideo-Foley** and **LTX Foley LoRA** are video-conditioned, which you explicitly do not need,
and are far larger.

**MusicGen, Bark, TTS models** are category mismatches.

---

## One thing worth saying plainly

Five models have now failed at a three-second drinking sound. The measured evidence points at two
causes that are **not** model identity: the out-of-regime short durations described above, and — for
MMAudio specifically — the fact that the drinking in this footage has the lowest visual motion energy
in the entire clip.

So my recommendation is MOSS-SoundEffect v2.0 **together with** generating at ~10 s and cropping. If
you would rather not spend another install cycle on this, a CC0 drinking Foley sample from Freesound
would solve the immediate problem in minutes and is worth weighing against a sixth model — the rest of
Module 3 does not depend on the sound being generated rather than sourced. That is your call, not
mine, and I raise it once rather than pressing it.

---

## Summary

| | |
|---|---|
| **Best** | **MOSS-SoundEffect v2.0** — 48 kHz, Apache 2.0, explicit human-action Foley class, duration-controllable to 30 s, documented MPS support, ~5–7 GB RAM, ~6–8 GB download |
| **Second** | **AudioGen medium** — most Foley-specific, and architecturally different from all five failures; held back by 16 kHz mono, CC-BY-NC, and an xformers dependency |
| **Deciding reason** | MOSS is the only candidate that is simultaneously **highest-fidelity (48 kHz)**, **commercially licensed (Apache 2.0)**, **explicitly trained on human-action Foley**, and **duration-controllable** — the last of which directly targets the >91 % silence signature that sank all three previous text-to-audio attempts |

**Nothing installed, downloaded, or generated. Awaiting your approval before any install.**

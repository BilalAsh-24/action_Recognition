# MMAudio small_44k — Drinking Foley, Generation v2 (focused context)

**Date:** 2026-08-25
**Output:** `Module3_Fresh/mmaudio/results/drinking_mmaudio_v2.wav`
**Generations run:** exactly 1. No sweeps, no retries, no prompt variants. v1 files untouched.

---

# QUALITY VERDICT: ❌ FAIL

**More decisively than v1.** The clip is 4.3 seconds of near-silence followed by one 0.21 s event
at the very end — which falls *after* the drinking interval, on the cup set-down.

| Drinking window (clip 1.0–4.0 s = source 5.5–8.5 s) | |
|---|---|
| Events | **0** |
| Active frames | **0.00 %** |
| RMS | 0.00168 |
| Peak | 0.0197 (**−34 dBFS**) |

The only detected event is at clip **4.299–4.505 s** = **source 8.80–9.00 s**, 300 ms *after* the
drinking action ends. Its energy is 75 % concentrated in 200 Hz–1 kHz — a low-mid thud consistent
with ceramic contacting a table, not a sip.

---

## Run parameters (as requested)

| | |
|---|---|
| **Video context** | source **4.50 – 9.00 s** (cut to 4.625 s of frames, `-an`), drinking centred at 1.0–4.0 s within it |
| **Context clip** | `work/context_4.5_9.0.mp4` — 111 frames, 24 fps, **0 audio streams** |
| **Actual duration** | **4.5000 s** — no truncation (v1 lost 0.04 s) |
| **Positive prompt** | *"Realistic close-up Foley of a person drinking water from a ceramic cup, with repeated natural sips, audible swallowing, wet mouth sounds, gentle breathing, and subtle cup-to-lips sounds. Clearly recognizable continuous human drinking."* |
| **Negative prompt** | *"music, speech, talking, voice, footsteps, background ambience, room tone, cinematic effects, clicks, pops, electronic sounds, noise"* |
| **Token check** | positive **49/77**, negative **30/77** — **both fit, zero truncation** |
| **Seed** | 42 |
| **Model** | MMAudio `small_44k`, 44.1 kHz |
| **Precision** | bf16 CLIP + Synchformer · **fp32** diffusion · **fp32** VAE + BigVGAN · no fp16 |
| **Sampler** | 25 euler steps, CFG 4.5 (upstream defaults) |
| **Device** | Apple MPS |
| **Sequence lengths** | latent 194 · clip 36 · sync 104 |
| **Generation time** | **50.1 s total** — phase 1 32.4 s, phase 2 6.6 s, phase 3 11.1 s (diffusion itself 2.38 s) |
| **Peak RAM** | **9.25 GB** (baseline 6.96 GB) · min available **2.88 GB** |
| **Swap growth** | **+0.33 GB** (peak 1.52 GB) |
| Guard | 1.5 GB available / 6.0 GB swap growth — never breached |

Negative-text conditioning **is** supported by the official API (`generate(..., negative_text=...)`,
consumed via `net.get_empty_conditions`), so it was used for classifier-free guidance. No repository
modification was needed or made.

## WAV properties

| Property | Value |
|---|---|
| Duration | 4.5047 s |
| Sample rate | 44,100 Hz |
| Channels | 1 (mono, PCM_16) |
| RMS | 0.005630 |
| Peak | 0.19968 (−13.99 dBFS) |
| Crest factor | 31.00 dB |
| Clipping | **none** (0 samples ≥ 1.0) |
| NaN / Inf | **none**, all finite |
| Acoustic onset | **4.0083 s** |
| Acoustic offset | 4.5047 s |
| Silence | 95.5 % below −20 dB · 64.3 % below −30 dB · **95.8 % below acoustic threshold** |
| Dynamic range (p95−p5) | 11.92 dB |
| Spectral | centroid 5368 Hz · rolloff95 14.9 kHz · flatness 0.0588 · **75.1 % of energy in 200 Hz–1 kHz** |

Per-second RMS: `0.0015, 0.0014, 0.0016, 0.0020, 0.0162` — flat floor, then one burst in the final
half-second.

## Acoustic event timeline

| # | Start | End | Duration | Peak | Source time | Coincides with |
|---|---|---|---|---|---|---|
| 1 | 4.299 s | 4.505 s | 0.206 s | 0.1997 | **8.80–9.00 s** | *place cup on table* (starts 8.5 s) |

There is no second event, so event spacing is undefined.

```
   0dB |                                                                    ## |
  -12dB|                                                            #   ##  ###|
  -21dB|                                                        #   ##    #####|
  -27dB|##########  ###   #  # ## # ###################### ####################|
        |         ==============================================              |  <- DRINK window
         0s        1s        2s        3s        4s
```

## Relationship between generated events and the drinking action

**Zero overlap.** The drinking window is empty; the single event lands 300 ms after it ends.

Combined with v1, the pattern is now replicated:

| | v1 | v2 |
|---|---|---|
| Context | source 2.0–10.0 s | source 4.5–9.0 s |
| Prompt | 189 tokens, **59 % truncated** | 49 tokens, **no truncation** |
| Negative prompt | none | full, untruncated |
| Events in drinking window | **0** | **0** |
| Where the sound landed | source 2.02–4.03 s (*cup pickup*) | source 8.80–9.00 s (*cup set-down*) |

**Both times, MMAudio produced sound where the video has large visual motion, and silence during the
drinking itself.**

### The likely mechanism — now measured, not assumed

I analysed motion energy (mean absolute inter-frame difference) across the source video:

| Source interval | Module 2 action | Mean motion | Max |
|---|---|---|---|
| 0.0–1.5 s | stand | 1.33 | 1.90 |
| 1.5–2.5 s | walk around table | **1.52** | 2.03 |
| 2.5–5.5 s | pick up cup | 1.10 | **2.20** |
| **5.5–8.5 s** | **DRINK FROM CUP** | **0.40** | **0.71** |
| 8.5–10.0 s | place cup on table | 0.86 | 1.29 |

**The drinking action is the least visually active moment in the entire video** — roughly 3× less
motion than walking and 2.7× less than the cup pickup. The person raises a mug and holds it near
their face; almost nothing moves.

MMAudio's temporal conditioning comes from Synchformer, which keys on visual motion. With near-zero
motion across 5.5–8.5 s, it has essentially no onset evidence to condition on, and the model outputs
silence. In v1 it fired on the pickup; in v2, with the pickup mostly cropped out, the only motion
left in frame was the cup coming back down — and that is exactly where the one event landed.

### A hypothesis of mine that turned out to be wrong

After v1 I identified prompt truncation as the leading explanation and called it "the highest-value
single change." **That was incorrect.** v2 fixed the truncation completely — 49/77 tokens, plus a
full negative prompt — and the result did not improve; by every activity measure it got worse (5
events → 1, 18.7 dB dynamic range → 11.9 dB). The truncation was real, but it was not the cause.

Narrowing the context also hurt on its own terms: 4.5 s is a larger deviation from MMAudio's 8 s
training duration, and it removed most of the visual context the model had been keying on.

## What this is *not*

For completeness, the same negatives you asked me to screen for:

- **Not hiss or generic noise** — 95.8 % of frames sit below the acoustic threshold; flatness 0.059.
- **Not clicks or pops** — the single event is 206 ms, a sustained contact sound, not a transient.
- **Not electronic** — 93 % of energy below 1 kHz, smooth rolloff, physically plausible.
- **Technically clean** — correct 44.1 kHz mono, correct duration, no clipping, no NaN/Inf.

The one sound present is well-formed. It is simply not drinking, and it is in the wrong place.

## Files

| Path | Contents |
|---|---|
| `mmaudio/results/drinking_mmaudio_v2.wav` | the single generated audio, 4.50 s, 44.1 kHz mono |
| `mmaudio/results/drinking_mmaudio_v2_generation.json` | config, per-phase verification, memory telemetry |
| `mmaudio/results/drinking_mmaudio_v2_analysis.json` | all objective measurements |
| `mmaudio/results/drinking_mmaudio_v2_report.md` | this report |

v1 outputs, the source video (`a620ee58…`, unchanged), Module 2, the MMAudio repository, and all
existing environments are untouched. No synchronisation, no MP4, no mixing.

---

## Recommendation

**Do not synchronise.** As with v1, there is no drinking audio to place.

Please still listen — the verdict is measurement-based, and the final 200 ms is worth hearing. But
the drinking window peaks at −34 dBFS, which is inaudible in practice.

Two controlled attempts now agree, and the motion-energy measurement explains why: **the drinking in
this footage is too visually static for MMAudio's Synchformer conditioning to detect.** That is a
property of the source video interacting with the model, not of the prompt, the context window, or
the memory strategy — all three of which worked correctly this time.

I am stopping here as instructed and making no further changes. If you want a next step after your
listening verdict, the options worth considering are materially different from another prompt edit,
and I would rather discuss them than assume one.

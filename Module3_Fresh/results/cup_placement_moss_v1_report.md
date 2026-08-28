# MOSS-SoundEffect v2.0 — Cup Placement Foley, Generation v1

**Date:** 2026-08-25 · **Generations run: exactly 1** · No retries.
**Action:** a person places a ceramic mug down naturally on a wooden table.

# VERDICT: ⚠️ UNCERTAIN — leaning FAIL

**7 of 10 requirements pass.** The two that fail are the ones that define the action: there is no
measurable ceramic signature. Structurally this is the best of the three object-interaction attempts
— real, well-formed, cleanly separated impacts with 44 dB of contrast against the background — but
the impacts read as **low wooden knocks rather than ceramic-on-wood**.

Unlike cup pickup v2 (which was mathematically empty), this file contains genuine content. Your ears
should decide whether it passes as a mug being set down.

**Output:** `Module3_Fresh/audio/generated/cup_placement_moss_v1_seed42.wav`

---

## Locked assets — verified before and after

`shasum -c` passed both times; permissions unchanged at `r--r--r--`:
`drinking_moss_v2_local_seed42.wav` OK · `walking_moss_v1_seed42.wav` OK

## Configuration

Same validated pipeline — local MOSS v2.0 (`58b20a0` / `e35df4d8`), phased wrapper, MPS shims,
seed 42, 50 steps, cfg 4, sigma_shift 5, 48 kHz mono PCM16, 10 s output (30 s denoised internally).
Prompt and negative prompt exactly as supplied. MOSS repository pristine. No normalisation applied.

Generation: **264.0 s** (text 4.85 · diffusion 234.61 · decode 9.44) · peak RAM 11.74 GB ·
min available 1.87 GB · swap growth **+0.01 GB** · no guard breach.

## 10. Measurements

| | |
|---|---|
| Sample rate / channels / duration | 48,000 Hz / mono / **10.000 s** (480,000 samples) |
| **Peak** | 0.029907 (**−30.48 dBFS**) |
| **RMS** | 0.001289 (**−57.8 dBFS**) |
| Crest factor | 27.31 dB |
| Effective bits | 10.9 of 16 |
| Clipping / NaN / Inf | **0 / 0 / 0** |
| Background RMS | −74.7 dBFS |
| **Event-to-background ratio** | **44.2 dB** |
| Dynamic range (p95−p5) | 17.5 dB |
| Spectral flatness | 0.0299 |
| Harmonic ratio | 0.0205 |
| Energy 0–200 Hz | **64.5 %** |
| Energy 200 Hz–1 kHz | 37.6 % |
| **Energy 1–5 kHz** | **0.52 %** |
| Energy 5–15 kHz | 0.22 % |

## Event timeline — 8 impacts above −40 dBFS, in 5 clusters

| t (s) | dBFS | attack ms | decay→20 % ms | 1–5 kHz | Dominant Hz |
|---|---|---|---|---|---|
| 0.613 | −33.3 | 11.8 | — | 2.1 % | 188 / 164 / 211 |
| **0.821** | **−30.1** | 19.8 | 47.8 | 0.4 % | 94 / 70 / 188 |
| 3.755 | −34.8 | 10.9 | — | 0.3 % | 188 / 211 / 164 |
| 3.941 | −34.8 | 6.6 | 16.8 | 0.4 % | 188 / 211 / 94 |
| 6.213 | −33.0 | 2.3 | — | 1.8 % | 375 / 398 / 188 |
| 6.299 | −31.3 | 18.9 | 49.2 | 0.3 % | 94 / 70 / 117 |
| 7.739 | −37.0 | 19.5 | 16.6 | 0.4 % | 117 / 141 / 94 |
| 9.216 | −32.7 | 2.5 | 27.1 | 0.3 % | 211 / 188 / 141 |

Per-second RMS shows clean separation — impacts at seconds 0, 3, 6, 7, 9 with near-silence between:

```
0-1s  -52.4 dBFS  #############
1-2s  -74.3 dBFS  ##
2-3s  -75.2 dBFS  ##
3-4s  -56.9 dBFS  ###########
4-5s  -73.5 dBFS  ###
5-6s  -75.1 dBFS  ##
6-7s  -53.2 dBFS  #############
7-8s  -60.0 dBFS  ##########
8-9s  -75.4 dBFS  ##
9-10s -55.4 dBFS  ############
```

## Requirement-by-requirement

| # | Requirement | Result |
|---|---|---|
| 1 | Strong, clearly identifiable **ceramic**-on-wood impact | ❌ **FAIL** — impacts are strong but not ceramic (see below) |
| 2 | Impact substantially stronger than background | ✅ **PASS** — **44.2 dB** event-to-background |
| 3 | Short natural resonance/decay after contact | ✅ **PASS** — decay to −20 % of 16.6–49.2 ms |
| 4 | Temporally compact | ✅ **PASS** — attacks 2.3–19.8 ms, clusters ~200–300 ms |
| 5 | Ceramic/high-frequency content present | ❌ **FAIL** — **0.52 %** in 1–5 kHz |
| 6 | No continuous ambience or noise bed | ✅ **PASS** — background −74.7 dBFS, 95.8 % of frames below −20 dB |
| 7 | No speech/music/electronic/unrelated Foley | ✅ **PASS** — harmonic ratio 0.0205, no tonal or synthetic artefacts |
| 8 | No clipping, NaN/Inf, corruption | ✅ **PASS** — 0 / 0 / 0, valid WAV |
| 9 | Resembles *placing*, not dropping or smashing | ⚠️ **PARTIAL** — restrained and unclipped, but 8 impacts where one was requested |
| 10 | Full reporting | ✅ done |

## Why requirements 1 and 5 fail

Ceramic contact is defined by 1–5 kHz content. Measured across every asset in the project:

| File | 1–5 kHz | 5–15 kHz | <200 Hz |
|---|---|---|---|
| **drinking (approved)** — same ceramic mug | **28.96 %** | 0.31 % | 8.7 % |
| cup_pickup v1 | 1.68 % | 1.11 % | 58.3 % |
| walking (approved) — wood, no ceramic | 1.63 % | 0.00 % | 55.8 % |
| **cup_placement v1 (new)** | **0.52 %** | 0.22 % | **64.5 %** |

**This is the lowest ceramic-band content of anything generated in this project** — a factor of 56
below the drinking sample, and three times lower than the walking footsteps, which contain no
ceramic at all.

The dominant frequencies of all eight strong impacts are **70–398 Hz**. Event at 0.821 s has
dominant 94/70/188 Hz with spectral flatness **0.000** — an almost pure low-frequency thud, not a
contact transient. A ceramic mug meeting wood produces a bright broadband "clack" over the wood
resonance; only the wood component is present here.

## The multiple-impact issue

The prompt asked for "**one** clear ceramic-on-wood contact" and the negative prompt explicitly
excluded "multiple impacts". The result contains **8 strong impacts in 5 clusters**, and the loudest
is only **1.2 dB** above the second loudest — so no single event dominates.

For synchronisation this is less damaging than it sounds: a single cluster could be selected and the
rest discarded. The clusters at **0.61–0.91 s** and **6.21–6.38 s** are the strongest, and 6.21 s has
the highest-frequency content of any strong event (dominant 375/398 Hz, 1.8 % in 1–5 kHz). I have
not cropped or selected anything.

## Why UNCERTAIN rather than FAIL

The file is technically clean, has genuine impulsive structure, excellent background separation, and
plausible attack/decay for object contact. It is a competent Foley recording — the question is only
whether it reads as *ceramic on wood* or as a generic wooden knock. A heavy stoneware mug placed
gently on thick timber, close-miked, can genuinely be dominated by low wood resonance, and the prompt
did ask for "no exaggerated impact". The measurements say the ceramic character is absent; my ears
cannot check that, so I will not overrule you.

**Listen at raised volume** (peak −30.5 dBFS, roughly **+23 dB** to match the walking asset). Judge
whether any of the five impacts reads as a mug being set down on wood.

## Pattern across all three object-interaction attempts

| Attempt | Peak | 1–5 kHz | Verdict |
|---|---|---|---|
| cup_pickup v1 | −36.0 dBFS | 1.68 % | UNCERTAIN / unapproved |
| cup_pickup v2 | −61.7 dBFS | 1.50 % | FAIL |
| cup_placement v1 | −30.5 dBFS | 0.52 % | UNCERTAIN / leaning FAIL |

MOSS has produced strong ceramic character once — in the approved drinking sample (28.96 %) — but
not in any of the three ceramic-object interactions. That is worth noting before deciding next steps,
though I am not proposing any.

## Files

| Path | Contents |
|---|---|
| `audio/generated/cup_placement_moss_v1_seed42.wav` | the generated audio, 10 s |
| `results/cup_placement_moss_v1_generation.json` | config, timing, memory |
| `results/cup_placement_moss_v1_analysis.json` | full 15-event analysis |
| `results/cup_placement_moss_v1_report.md` | this report |

No synchronisation, no MP4, no mixing, no normalisation, no regeneration. Approved assets untouched.

# MOSS-SoundEffect v2.0 — Cup Pickup Foley, Generation v1

**Date:** 2026-08-25 · **Generations run: exactly 1** · No retries.
**Action:** picking up a ceramic mug from a wooden table.

# VERDICT: ⚠️ UNCERTAIN — leaning FAIL

Technically valid, but two objective measurements argue against it, and both are the kind that
usually survive listening. Your ears decide.

**Output:** `Module3_Fresh/audio/generated/cup_pickup_moss_v1_seed42.wav`

---

## Locked assets — untouched and verified

| File | SHA-256 | Perms |
|---|---|---|
| `drinking_moss_v2_local_seed42.wav` | `a59f38c9…` | `r--r--r--` |
| `walking_moss_v1_seed42.wav` | `0eae125b…` | `r--r--r--` |

Both write-protected at the filesystem level and hash-recorded in `results/APPROVED_ASSETS.lock`.
Write attempts were tested and correctly refused.

## Configuration

Same validated pipeline: local MOSS v2.0 (`58b20a0` / `e35df4d8`), phased wrapper, MPS shims,
seed 42, 50 steps, cfg 4, sigma_shift 5, 48 kHz mono PCM16, 10 s (30 s denoised internally).
Prompt and negative prompt exactly as supplied. MOSS repo pristine.

Generation: **245.82 s** (text 4.97 · diffusion 216.83 · decode 8.95) · peak RAM 11.69 GB ·
min available 1.90 GB · swap growth **+0.04 GB** · no guard breach.

## 7. Technical validity — ✅ PASS

| Check | Value |
|---|---|
| Sample rate / channels | 48,000 Hz / mono ✅ |
| Duration | 10.000 s / 480,000 samples ✅ |
| Clipping | 0 samples ✅ |
| NaN / Inf | 0 / 0 ✅ |
| Valid WAV | yes ✅ |
| Peak | 0.015869 (**−36.0 dBFS**) |
| RMS | **−65.1 dBFS** |
| Crest factor | 29.1 dB |
| **Effective bits used** | **10.0 of 16** |

## The two concerns

### 1. It is very quiet — 28.7 dB below the approved walking asset

| File | Peak dBFS | Audible-band RMS | Effective bits |
|---|---|---|---|
| walking (approved) | −7.3 | −35.1 | 14.8 |
| drinking (approved) | −23.5 | −55.4 | 12.1 |
| **cup pickup** | **−36.0** | **−65.9** | **10.0** |

At 10 effective bits, PCM16 quantisation noise is no longer negligible. Most detected events sit at
−56 to −70 dBFS; only about seven reach −35 to −44 dBFS. At normal playback this will be close to
inaudible without a large gain increase.

### 2. The ceramic signature is largely absent

Ceramic contact and ring live in the 1–5 kHz band. Measured energy there:

| File | 1–5 kHz | 5–15 kHz |
|---|---|---|
| **drinking (approved)** — same ceramic mug | **28.96 %** | 0.31 % |
| walking (approved) — wooden floor, no ceramic | 1.63 % | 0.00 % |
| **cup pickup** | **1.68 %** | 1.11 % |

**The cup pickup has no more ceramic-band content than the footsteps do.** The approved drinking
sample demonstrates that this model *can* produce strong 1–5 kHz ceramic character — it simply did
not here. Spectral distribution is 58.8 % below 200 Hz and 38.4 % in 200 Hz–1 kHz: a low thud
profile, closer to wood than to ceramic.

### A correction to my own first reading

My initial pass flagged per-event "dominant frequencies" of 0/23/47 Hz and I suspected subsonic
rumble. **That was a measurement artefact** — those were low STFT bins in a magnitude-weighted
readout. The correct figures: only **13.0 %** of energy is below 20 Hz and **17.4 %** below 40 Hz, so
**87 % is audible**, and high-passing at 40 Hz barely moves anything (peak −36.0 → −35.8 dBFS).
This is not a rumble file. DC offset is negligible (−0.000126).

## 1–4. Event timeline

27 events detected (min gap 80 ms, gate 25 dB below peak). Loudest 8:

| # | t (s) | dBFS | attack ms | decay→20 % ms | centroid Hz | 0–200 / 200–1k / 1–5k / 5–15k (%) |
|---|---|---|---|---|---|---|
| 5 | 0.837 | −38.1 | 5.1 | 10.0 | 5320 | 59.2 / 39.7 / 0.7 / 0.4 |
| 8 | 1.936 | −41.3 | 3.4 | — | 4968 | 38.3 / 58.8 / 2.4 / 0.5 |
| 9 | 2.032 | −41.3 | 3.4 | 16.8 | 5483 | 50.9 / 46.3 / 1.8 / 0.9 |
| 13 | 3.808 | −42.8 | 7.2 | — | 5178 | 43.9 / 54.8 / 0.8 / 0.5 |
| 14 | 3.941 | −42.8 | 6.5 | 11.7 | 5713 | 53.7 / 43.1 / 1.6 / 1.5 |
| 16 | 6.155 | −38.1 | 4.4 | — | 5552 | 47.0 / 49.2 / 3.5 / 0.3 |
| 17 | 6.299 | −35.7 | 48.6 | 20.2 | 5292 | 51.2 / 47.1 / 1.5 / 0.2 |
| 20–21 | 7.808 / 7.915 | −36.1 | 67.9 / 6.3 | 15.4 | 4182 / 5579 | ~47 / ~52 / 0.4 / 0.2 |
| 24 | 9.296 | −43.6 | 43.9 | 18.9 | 3810 | 46.6 / 51.6 / 1.5 / 0.3 |

Full 27-event table in `results/cup_pickup_moss_v1_analysis.json`.

**2. Distinct initial contact** — partially. There is no single dominant onset that reads as *the*
cup-meets-hand moment; instead ~7 comparable transients spread across all 10 s, in pairs 100–150 ms
apart (e.g. 1.936/2.032, 3.808/3.941, 7.808/7.915). Those pairs are plausibly contact-then-lift, but
no one event dominates.

**3. Hand/grip/lift movement** — attacks of 3–7 ms on the louder events are consistent with small
tactile contacts. Reasonable.

**4. Short decay/resonance** — decay to −20 % of 10–20 ms. Short and dry, as prompted. But ceramic
resonance would show sustained 1–5 kHz ringing, and that is what is missing (§2).

**5. Background ambience** — ✅ good. Background RMS −73.7 dBFS, event-to-background ratio **37.7 dB**,
92.4 % of frames below −20 dB. Not an ambience bed.

**6. Music / speech / electronic** — ✅ none. Harmonic ratio 0.1635 (elevated vs walking's 0.0041 but
far from tonal music), envelope modulation 1.3 Hz (not the ~4–5 Hz of speech), spectral flatness
0.0316 (structured, not noise). No electronic artefacts.

## Why UNCERTAIN rather than FAIL

The file is clean, correctly formed, free of ambience and artefacts, and contains real transients
with plausible attack times. What it lacks is level and ceramic character. If a gentle mug lift on
a soft cloth-free wooden table genuinely sounds this understated, this may be acceptable once
amplified. If you expect an audible ceramic *clink*, the measurements say it is not there.

I cannot hear it, so I will not call it FAIL on measurement alone.

## Please listen with this in mind

**Raise the volume substantially** — roughly **+29 dB** to match the walking asset's level. At native
level you will likely hear almost nothing, and that alone should not decide the verdict.

Then judge: is there a recognisable ceramic-on-wood pickup, or only soft low thuds?

I have not normalised the file. Say the word and I will produce a gain-adjusted copy for listening
without touching the original — but that is your call, and no regeneration will happen unless you
ask.

## Files

| Path | Contents |
|---|---|
| `audio/generated/cup_pickup_moss_v1_seed42.wav` | the generated audio, 10 s |
| `results/cup_pickup_moss_v1_generation.json` | config, timing, memory |
| `results/cup_pickup_moss_v1_analysis.json` | full 27-event analysis |
| `results/cup_pickup_moss_v1_report.md` | this report |
| `results/APPROVED_ASSETS.lock` | hashes of the two locked assets |

No synchronisation, no MP4, no mixing, no regeneration.

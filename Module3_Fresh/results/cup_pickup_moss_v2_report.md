# MOSS-SoundEffect v2.0 — Cup Pickup, Generation v2 (replacement attempt)

**Date:** 2026-08-25 · **Generations run: exactly 1** · No retries.

# VERDICT: ❌ FAIL

The generation collapsed to a **near-constant low-frequency tone at −61.7 dBFS**. It is not a cup
pickup, and it is worse than v1 on the gate it was meant to fix.

Unlike v1 — where I deferred to your ears — this verdict does not require listening. The file is
mathematically near-empty: 40 distinct sample values, 1.06 dB of dynamic range, and 95 % harmonic
content. There is no transient structure present to perceive.

**Output:** `Module3_Fresh/audio/generated/cup_pickup_moss_v2_seed42.wav` (v1 retained, not overwritten)

---

## Locked assets — verified intact

`shasum -c` passed for both; permissions still `r--r--r--`:

| File | Status |
|---|---|
| `drinking_moss_v2_local_seed42.wav` | OK — unchanged |
| `walking_moss_v1_seed42.wav` | OK — unchanged |

Nothing was regenerated, overwritten, normalised, edited, deleted or unlocked.

## Configuration

Same validated pipeline — local MOSS v2.0 (`58b20a0` / `e35df4d8`), phased wrapper, MPS shims,
seed 42, 50 steps, cfg 4, sigma_shift 5, 48 kHz mono PCM16, 10 s output (30 s denoised internally).
Prompt and negative prompt exactly as supplied. MOSS repo pristine.

Generation: **262.23 s** · peak RAM 11.71 GB · min available 1.87 GB · swap growth **+0.00 GB** · no breach.

## The measurements

| File | Peak dBFS | RMS dBFS | Eff. bits | Peak LSB | 1–5 kHz | 5–15 kHz | <200 Hz | Dyn range |
|---|---|---|---|---|---|---|---|---|
| **v2 (new)** | **−61.7** | **−68.7** | **5.8** | **27** | **1.50 %** | 1.62 % | **96.5 %** | **1.1 dB** |
| v1 (previous) | −36.0 | −65.1 | 10.0 | 520 | 1.68 % | 1.11 % | 58.3 % | 15.6 dB |
| drinking (approved) | −23.5 | −55.1 | 12.1 | 2192 | **28.96 %** | 0.31 % | 8.7 % | 29.2 dB |
| walking (approved) | −7.3 | −35.1 | 14.8 | 14144 | 1.63 % | 0.00 % | 55.8 % | 50.7 dB |

### Why this is degenerate output, not quiet Foley

- **Only 40 distinct sample values** in the whole file, spanning −27 to +12 LSB out of ±32768.
- **Per-second RMS is flat**: `0.000372, 0.000369, 0.000363, 0.000364, 0.000363, 0.000361, 0.000362,
  0.000365, 0.000368, 0.000363` — under 3 % variation across all ten seconds.
- **Dynamic range 1.06 dB.** Foley is impulsive; the approved walking asset measures 50.7 dB.
- **Harmonic ratio 0.9501** — 95 % harmonic content. That is a *tone*, not an impact. Walking measures
  0.0041, v1 measured 0.1635.
- Spectral flatness 0.00601 with 96.5 % of energy below 200 Hz.

The 83 "events" my detector reported are all at −66.3 to −66.8 dBFS — an identical level, because it
is picking ripples in a steady signal rather than discrete events. That count is an artefact and
should not be read as structure.

## Quality gate results

| # | Gate | Result |
|---|---|---|
| 1 | At least one clearly identifiable ceramic-mug pickup | ❌ FAIL — 1.06 dB dynamic range, no discrete event |
| 2 | Ceramic-on-wood contact/lift character | ❌ FAIL — 1.50 % in 1–5 kHz, 96.5 % below 200 Hz |
| 3 | Clear contact → lift sequence | ❌ FAIL — constant tone, no sequence |
| 4 | Useful audible level without extreme gain | ❌ FAIL — needs **+54.4 dB** to match walking; 5.8 effective bits |
| 5 | Ceramic/HF measurably stronger than v1 | ❌ FAIL — 1–5 kHz went **1.68 % → 1.50 %** (weaker) |
| 6 | No continuous ambience/noise bed | ❌ FAIL — a continuous bed is all that is present |
| 7 | No speech/music/electronic artifacts | ❌ FAIL — 95 % harmonic content is a tonal artefact |
| 8 | No clipping, NaN/Inf, WAV corruption | ✅ PASS — 0 clipped, 0 NaN/Inf, valid 48 kHz mono PCM16, 10.000 s |
| 9 | Temporally compact, physically plausible | ❌ FAIL — uniform across all 10 s |
| 10 | Report timestamps, level, spectrum, v1 comparison | ✅ done above |

**8 of 10 gates failed.**

On gate 5 specifically: 5–15 kHz did rise from 1.11 % to 1.62 %, but at −61.7 dBFS that band sits at
the PCM16 quantisation floor — it is noise, not ceramic detail. The band that actually carries
ceramic character, 1–5 kHz, moved the wrong way.

## Hypothesis for the collapse — not acted upon

The negative prompt grew from 17 terms (v1) to **24** (v2), adding `bass rumble`, `hiss`,
`heavy impact`, `wooden knocks without ceramic`, `reverb` and others. With CFG 4.0 pushing away from
all of them simultaneously — while the positive prompt also carries `no speech, no music, no
ambience` — the sampler may have been steered into a degenerate low-energy solution. Output level
tracked the negative-prompt length: 17 terms → −36.0 dBFS, 24 terms → −61.7 dBFS.

That is a pattern across two data points, not a finding. I am not acting on it, and I have not
regenerated.

## Reference point that still stands

The approved **drinking** sample contains **28.96 %** of its energy in 1–5 kHz, recorded from the same
ceramic mug. The model can clearly produce strong ceramic character. Neither cup-pickup attempt has
come close: v1 at 1.68 %, v2 at 1.50 % — both indistinguishable from the walking asset's 1.63 %,
which contains no ceramic at all.

## Status

- **v1** (`cup_pickup_moss_v1_seed42.wav`, −36.0 dBFS): UNCERTAIN, unapproved, retained.
- **v2** (`cup_pickup_moss_v2_seed42.wav`, −61.7 dBFS): **FAIL**.
- Neither is suitable for synchronisation.

Listening to v2 is not necessary — at 27 LSB peak with 1.06 dB dynamic range there is effectively
nothing to hear — but the file is at the path above if you want to confirm.

No synchronisation, no MP4, no mixing, no normalisation, no regeneration. Nothing else in the
project was changed.

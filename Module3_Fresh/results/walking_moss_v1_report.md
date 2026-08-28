# MOSS-SoundEffect v2.0 — Walking Foley, Generation v1

**Date:** 2026-08-25 · **Generations run: exactly 1** · No retries, no alternatives.
**Action:** a person walking naturally around a table on a hard wooden floor.

# VERDICT: ✅ PASS (objective) — pending your listening confirmation

Every measurable criterion is met, and the objective signature is a strong match for footsteps
rather than clicks, noise, speech, music or ambience. One reservation is noted in §6 that only
listening can settle.

**Output:** `Module3_Fresh/audio/generated/walking_moss_v1_seed42.wav` — full 10 s, uncropped.

---

## Configuration

| | |
|---|---|
| Model | MOSS-SoundEffect v2.0 (commit `58b20a0`, revision `e35df4d8`) — local, phased wrapper |
| Prompt | `close-up realistic Foley recording of natural human footsteps walking around a wooden table on a hard wooden floor, clearly audible alternating left and right footsteps with realistic heel and toe impacts, natural walking rhythm and slight variation between steps, subtle shoe contact and floor resonance, isolated dry Foley recording, no speech, no music, no ambience, no room tone, no cinematic sound design` |
| Prompt actually sent | above **+ `" duration: 10.0s"`** (upstream training-time convention) |
| Negative prompt | `music, speech, talking, voice, singing, background ambience, room tone, environmental noise, crowd, traffic, cinematic sound design, electronic sounds, synthetic sounds, exaggerated impacts, reverb` |
| Seed / steps / CFG / sigma_shift | 42 / 50 / 4 / 5 |
| Output | 48 kHz · mono · PCM16 · 10.000 s (engine denoises 30 s internally, then crops) |
| Device / dtype | mps · bfloat16 params · complex64 RoPE · no fp16 · no CUDA |

Same validated wrapper and MPS fixes as the approved drinking run. MOSS repository **pristine**
(`git status --porcelain` empty). Drinking WAV and the Space reference both **unchanged**.

## Generation

| | |
|---|---|
| Total | **240.10 s** (text 4.75 · diffusion **211.73** · decode 8.20) |
| Peak RAM | 11.68 GB · min available **1.85 GB** (guard floor 1.5) |
| Swap growth | **+0.01 GB** |
| Guard breach | none |

## 7. Technical integrity

| Check | Value |
|---|---|
| Sample rate | **48,000 Hz** ✅ |
| Channels | **1 (mono)** ✅ |
| Duration | **10.000 s** / 480,000 samples ✅ |
| RMS | 0.017646 |
| Peak | 0.43164 (**−7.30 dBFS**) ✅ healthy level |
| Crest factor | 27.77 dB |
| Clipping | **0 samples** ✅ |
| NaN / Inf | **0 / 0** ✅ |

Note this sits **16 dB louder** than the drinking sample (−7.3 vs −23.5 dBFS) — no gain adjustment
needed here.

## 1 & 8. Detected footstep events

Detection: onset-strength peak picking, minimum step spacing 0.25 s, level gate 30 dB below the
loudest transient. 38 candidates → **18 accepted**.

| # | t (s) | peak | dBFS | attack ms | decay→20% ms | centroid Hz | <200 / 200–800 / 800–3k / >3k (%) |
|---|---|---|---|---|---|---|---|
| 1 | 0.000 | 0.2148 | −13.4 | 3.7 | 10.7 | 3020 | 47.9 / 51.6 / 0.5 / 0.0 |
| 2 | 0.293 | 0.0169 | −35.5 | 2.0 | 30.1 | 4238 | 97.6 / 2.2 / 0.1 / 0.2 |
| 3 | 0.811 | 0.2695 | −11.4 | 2.0 | 30.1 | 3606 | 39.7 / 55.9 / 4.4 / 0.0 |
| 4 | 1.419 | 0.1621 | −15.8 | — | — | 3961 | 60.8 / 37.3 / 1.9 / 0.0 |
| 5 | 1.920 | 0.4004 | −8.0 | 2.2 | 34.6 | 3187 | 34.2 / 53.3 / 12.5 / 0.0 |
| 6 | 2.421 | 0.1494 | −16.5 | 7.2 | 31.9 | 3457 | 59.3 / 40.6 / 0.2 / 0.0 |
| 7 | 3.259 | 0.3164 | −10.0 | 7.8 | 28.1 | 3608 | 63.5 / 33.9 / 2.5 / 0.0 |
| 8 | 3.760 | 0.1572 | −16.1 | 66.6 | 23.8 | 2883 | 49.8 / 49.9 / 0.3 / 0.0 |
| 9 | 4.571 | 0.2012 | −13.9 | 8.0 | 33.7 | 3783 | 80.1 / 18.3 / 1.6 / 0.0 |
| 10 | 5.072 | 0.4316 | −7.3 | 3.7 | 21.7 | 3076 | 49.3 / 47.3 / 3.4 / 0.0 |
| 11 | 5.573 | 0.1289 | −17.8 | 60.9 | 24.9 | 4229 | 34.3 / 64.5 / 1.1 / 0.1 |
| 12 | 5.867 | 0.1289 | −17.8 | — | — | 3730 | 53.8 / 45.6 / 0.6 / 0.0 |
| 13 | 6.368 | 0.1895 | −14.4 | 3.8 | 23.1 | 3208 | 51.8 / 46.3 / 1.9 / 0.0 |
| 14 | 7.189 | 0.2793 | −11.1 | 6.6 | 34.4 | 3642 | 56.3 / 43.4 / 0.2 / 0.0 |
| 15 | 7.691 | 0.2383 | −12.5 | 50.9 | 22.6 | 2949 | 62.2 / 36.6 / 1.2 / 0.0 |
| 16 | 8.192 | 0.1445 | −16.8 | 7.1 | 33.5 | 5471 | 22.0 / 69.1 / 8.1 / 0.7 |
| 17 | 8.443 | 0.1934 | −14.3 | 7.1 | 33.5 | 3499 | 76.9 / 22.3 / 0.8 / 0.0 |
| 18 | 9.013 | 0.1680 | −15.5 | 9.2 | 7.0 | 3422 | 77.4 / 22.6 / 0.0 / 0.0 |

Attack/decay measured from a Hilbert amplitude envelope. Events 4 and 12 return no reliable
attack/decay — their analysis windows abut neighbouring transients; the detections themselves stand.

## 2. At least 5 clearly separated footsteps — ✅ PASS

**18 events**, well above the threshold, each separated by ≥0.25 s.

## 3. Alternating / natural walking rhythm — ✅ PASS

| | |
|---|---|
| Inter-onset intervals | 0.293, 0.517, 0.608, 0.501, 0.501, 0.837, 0.501, 0.811, 0.501, 0.501, 0.293, 0.501, 0.821, 0.501, 0.501, 0.251, 0.571 s |
| Mean IOI | **0.530 s** → **1.8 steps/s ≈ 108 steps/min** |
| Std / CV | 0.165 s / 0.311 |
| Range | 0.251 – 0.837 s |
| **Peak autocorrelation (successive)** | **−0.344** |

108 steps/min is squarely a natural walking cadence. The dominant IOI is a recurring 0.501 s with
genuine variation around it — the "slight variation between steps" the prompt asked for, not a
metronome.

The **negative** peak-to-peak correlation (−0.344) is the notable result: successive impacts tend to
alternate loud/quiet. That is the expected signature of left/right gait asymmetry, and it is what
"alternating footsteps" should look like objectively.

Caveat: the 0.25–0.29 s intervals (#1→#2, #10→#11) may be heel-then-toe of a *single* step rather
than two steps. If so the true step count is nearer 15–16, still comfortably above the gate.

## 4. Coverage across the audio — ✅ PASS

Events per second: `[3, 2, 1, 2, 1, 3, 1, 2, 2, 1]` — **10 of 10 seconds contain events.**
First 0.000 s, last 9.013 s, longest gap 0.837 s. No dead region.

Per-second RMS: `0.0192, 0.0105, 0.0225, 0.0233, 0.0155, 0.0212, 0.0114, 0.0218, 0.0129, 0.0114`
— consistent activity, no fade-out.

## 5. Impact / decay realism — ✅ PASS

| | |
|---|---|
| Attack (median) | **7.2 ms** — within the 1–15 ms natural range for a footstep transient |
| Decay to −20 dB (median) | 29.1 ms |
| Decay to −60 dB | 160–410 ms |

Sharp attacks with a 160–410 ms tail are impacts with body, not clicks. The short −20 dB decay is
consistent with a **dry, close-miked recording on hard wood** — exactly what was prompted, with
`reverb` in the negative prompt.

## 6. Is it footsteps, or something else? — ✅ PASS, with one reservation

| Measure | Value | Reading |
|---|---|---|
| Harmonic ratio (HPSS) | **0.0041** | essentially no harmonic content → **not music, not speech** |
| Envelope modulation peak | **1.5 Hz** | walking cadence; speech would peak near 4–5 Hz |
| Spectral flatness | 0.0138 | structured → **not white noise / hiss** |
| Dynamic range (p95−p5) | **50.72 dB** | discrete impacts → **not ambience or room tone** |
| Frames below −20 / −30 dB | 89.3 % / 79.6 % | sparse events with quiet between → not a continuous bed |
| Energy < 800 Hz | **96.9 %** | low-frequency dominated, consistent with wooden-floor thumps |

Together these rule out every failure mode you listed.

### The one reservation

**Energy above 3 kHz is 0.00 %.** Real footsteps normally carry some high-frequency transient — heel
click, sole scuff, floor creak. Its complete absence suggests the result may sound **dull or thumpy
— body without "snap"**. That could equally be a faithful rendering of a soft-soled shoe on solid
wood, which is plausible for the scene. Only listening can decide.

(The reported spectral centroid of 3857 Hz looks inconsistent with 96.9 % of power below 800 Hz.
It is magnitude-weighted across the whole spectrum and is misleading here; the power-band
distribution is the honest measure.)

## Method corrections made during this analysis

Two flaws in my first analysis pass, both fixed before any verdict:

1. **Over-detection.** The initial detector reported 58 "events", many in pairs ~0.165 s apart with
   *identical* peak values — a fixed 0.40 s analysis window was catching the same transient twice,
   and the `wait` parameter was quantising detections. Fixed with a 0.25 s minimum step gap, a 30 dB
   level gate, and per-event windows bounded by the next onset. 38 candidates → 18 real events.
2. **Broken decay metric.** Decay was measured on the raw waveform, which crosses zero constantly,
   producing meaningless sub-millisecond values. Re-measured from a Hilbert amplitude envelope.

## Files

| Path | Contents |
|---|---|
| `audio/generated/walking_moss_v1_seed42.wav` | the generated audio, full 10 s |
| `results/walking_moss_v1_generation.json` | config, timing, memory telemetry |
| `results/walking_moss_v1_analysis.json` | full objective analysis |
| `results/walking_moss_v1_report.md` | this report |
| `moss/scripts/moss_generate.py` | parameterised driver (drinking script untouched) |
| `moss/scripts/analyze_walking.py` | footstep analysis |

Not done, as instructed: no synchronisation, no MP4, no mixing, no cropping, no second sample.

---

**Objective PASS on all nine criteria. Awaiting your listening verdict — the thing to listen for is
whether the steps have enough high-end definition, since the analysis shows none above 3 kHz.**

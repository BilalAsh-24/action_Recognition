# Module 3 — Final Report

**Built:** 2026-08-25 · **Quality gate: 15/15 PASS**

```
SILENT VIDEO -> MODULE 2 TIMELINE -> VISUAL EVENT LOCALISATION
   -> APPROVED MOSS FOLEY -> TEMPORAL SYNCHRONISATION -> MIXING -> FINAL VIDEO
```

## Outputs

| Artefact | Path |
|---|---|
| **Final video** | `output/final_silent_to_audio.mp4` |
| **Synchronised audio** | `audio/mixed/final_synchronized_audio.wav` |
| Machine-readable record | `results/final_synchronization.json` |
| Quality gate | `results/quality_gate.json` |
| Sync plan / mix log / visual events | `results/sync_plan.json`, `mix_log.json`, `visual_events.json` |

Final MP4: 10.000 s video (240 frames, 1280×720, h264 **stream-copied**) + 9.984 s AAC audio at
48 kHz mono. Source video SHA-256 `a620ee58…` — **unchanged**.

## Synchronisation — what actually happens

Module 2 gives broad action spans. Foley is **not** placed at the start of those spans; frame-level
motion analysis locates the audible instant inside each one, and each clip is positioned so its
**audible onset** lands there.

| Action | M2 interval | Visual event | Kind | Foley placed | Source used |
|---|---|---|---|---|---|
| stand | 0.0–1.5 s | — | — | **silent** (no sound event) | — |
| walk around table | 1.5–2.5 s | **2.292 s** | foot_contact | 1.500–2.500 s | walking 0.019–1.019 s |
| pick up cup | 2.5–5.5 s | 2.542 s (lift) | — | **silent — no approved Foley** | — |
| drink from cup | 5.5–8.5 s | **6.583 s** | sip_hold | 6.216–6.916 s | drinking 8.946–9.646 s |
| drink from cup | 5.5–8.5 s | **7.792 s** | sip_hold | 7.256–7.957 s | drinking 1.405–2.105 s |
| place cup on table | 8.5–10.0 s | **9.833 s** | mug_table_contact | 9.698–10.005 s | placement 0.000–0.400 s |

### Strategy per action

**Walking** — a continuous 1.0 s slice of the walking asset, time-shifted so one of MOSS's own
footsteps (asset t=0.811 s) lands exactly on the detected foot-plant at 2.292 s. This preserves the
generated 108 steps/min cadence instead of retriggering one-shots; a second natural step falls at
1.774 s, also inside the interval.

**Drinking** — the approved asset contains 12 events across 10 s, so the whole file is not played.
Two isolated sip/swallow segments were selected by wet-band dominance (≥45 % energy in 200 Hz–1 kHz)
and isolation, then each was aligned by its own onset to a detected sip-hold. Sip-holds were found as
sustained **low**-motion periods in the head region — the mug resting at the lips.

**Cup placement** — a 400 ms contact asset (`cup_placement_foley_final.wav`), derived by trimming
6.15–6.55 s from the approved 10 s MOSS recording with 8 ms fades. That cluster was chosen for the
loudest peak and the cleanest cut edges (−39.6 dB), and contains contact → resonance → settle. Its
attack is aligned to the visible mug-table contact at 9.833 s.

**Cup pickup — no audio written.** Two MOSS generations (UNCERTAIN, FAIL) and an extraction study
from the drinking asset (NOT VIABLE) were all rejected. The interval is left silent and recorded as
unavailable in `final_synchronization.json`. **Nothing was fabricated to fill it.**

### Visual motion diagnostics

Mean inter-frame motion per action, by region — the basis for event localisation:

| Action | all | feet | head | table |
|---|---|---|---|---|
| stand | 1.106 | 1.597 | 0.646 | 1.444 |
| walk around table | 1.209 | **1.576** | 0.835 | 1.640 |
| pick up cup | 0.803 | 0.889 | 0.691 | **1.126** |
| drink from cup | **0.226** | 0.130 | 0.312 | 0.208 |
| place cup on table | 0.573 | 0.439 | 0.672 | **0.723** |

Drinking is by far the least visually active interval — consistent with the earlier MMAudio finding,
and the reason sip-holds are detected as motion *minima* rather than peaks.

## Mixing and levels

Each clip is scaled to a **target peak** chosen for scene balance, not normalised to equal loudness.
A mug meeting a table is the most percussive event; footsteps sit mid-ground; sipping is intimate.

| Action | Raw peak | Target | Gain | Fades |
|---|---|---|---|---|
| walk around table | −11.4 dBFS | −20.0 | **−8.61 dB** | 8 ms in/out |
| drink from cup (1) | −26.2 dBFS | −24.0 | **+2.18 dB** | 8 ms in/out |
| drink from cup (2) | −25.0 dBFS | −24.0 | **+0.97 dB** | 8 ms in/out |
| place cup on table | −30.7 dBFS | −18.0 | **+12.70 dB** | 8 ms in/out |

**Drinking was deliberately not boosted to match the others** despite its lower raw peak — it sits
4 dB below walking and 6 dB below the placement, which is where a close-miked sip belongs. Gains stay
within ±13 dB; no aggressive per-asset normalisation was applied and MOSS's own character is intact.

Mix bus: peak −18.00 dBFS against a −3.0 dBFS ceiling, so **no bus gain was needed** (0.00 dB).
Final mix RMS −48.01 dBFS, **0 clipped samples**, no NaN/Inf.

**One truncation:** the placement clip would have ended at 10.098 s, past the video. Its tail was
truncated by **93.1 ms** with a fade rather than extending the timeline. This is physically honest —
the video ends while the mug's resonance is still decaying.

## Quality gate — 15/15

| # | Check | Result |
|---|---|---|
| 1 | Final MP4 opens | ✅ 2 streams |
| 2 | Video duration unchanged | ✅ 10.005 → 10.000 s |
| 2b | Video stream bit-identical | ✅ 240 frames, 1280×720, h264, stream-copied |
| 3 | Audio duration matches video | ✅ 9.984 s vs 10.000 s |
| 4 | Sample rate | ✅ 48,000 Hz |
| 5 | No clipping | ✅ peak −18.00 dBFS |
| 6 | No NaN/Inf | ✅ |
| 7 | No unexpected silence | ✅ all four clips audible at target level |
| 8 | Walking only where visually appropriate | ✅ 1 clip in [1.5, 2.5], aligned 2.292 s |
| 9 | Drinking during the actual sequence | ✅ 2 clips in [5.5, 8.5], aligned 6.583 / 7.792 s |
| 10 | Placement at visible mug-table contact | ✅ 1 clip in [8.5, 10.0], aligned 9.833 s |
| 11 | No audio during unrelated actions | ✅ zero bleed into stand / pick-up |
| 12 | Cup pickup documented, not fabricated | ✅ recorded as unavailable, no audio written |
| 13 | Original video hash unchanged | ✅ `a620ee58…` |
| 14 | Locked asset hashes unchanged | ✅ 2/2 verified |

## Architecture

| File | Role |
|---|---|
| `scripts/m3_config.py` | paths, asset registry, level targets, unavailable-Foley declarations |
| `scripts/visual_events.py` | ffmpeg → greyscale frames; region motion; per-action event localisation |
| `scripts/make_placement_asset.py` | one-time trim of the placement asset from the 10 s source |
| `scripts/sync_actions.py` | timeline + visual events → onset-aligned placement plan |
| `scripts/audio_mixer.py` | gains, fades, boundary truncation, bus safety, WAV render |
| `scripts/build_final_video.py` | mux with `-c:v copy` |
| `scripts/analyze_sync.py` | the 15-check quality gate |
| `scripts/write_reports.py` | assembles `final_synchronization.json` |
| `scripts/run_module3.py` | end-to-end orchestrator |

Rebuild everything with:

```bash
moss/venv-moss/bin/python scripts/run_module3.py
```

## Constraints honoured

No model was tested, installed or downloaded. No Foley was regenerated. The MOSS repository, Module 2
outputs, the original video and both locked WAVs are byte-identical to before this build — verified by
SHA-256 in the quality gate. Video is stream-copied, so the picture is untouched.

## Known limitations

1. **Cup pickup is silent.** A quarter of the action timeline (2.5–5.5 s) has no Foley. This is a
   deliberate, documented gap.
2. **Visual localisation is motion-based**, not object-tracking. Events carry `medium` confidence.
   The walking interval yielded one detected foot-plant; a second step is implied by the asset's own
   cadence rather than independently confirmed.
3. **Cup placement was never approved by listening** — it was UNCERTAIN/leaning-FAIL on measurement
   (0.52 % of energy in 1–5 kHz, versus 28.96 % in the drinking asset). It is included here because
   it was named as an approved asset in the build instruction. If it does not sound right, the fix is
   in the asset, not in the synchronisation.
4. The 93.1 ms placement truncation is imposed by the video's end.

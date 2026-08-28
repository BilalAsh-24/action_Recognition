# Module 3 — Polished Final Output

**Built:** 2026-08-25 · **QA: 17/17 PASS** · **Worst sync error: 20 ms**

No Foley regenerated. No approved MOSS asset altered. Module 2 boundaries unmodified. v1 outputs preserved.

## Outputs

| Artefact | Path |
|---|---|
| **Polished video** | `output/final_silent_to_audio_polished.mp4` |
| **Polished audio** | `audio/mixed/final_synchronized_audio_polished.wav` |
| Machine-readable record | `results/final_synchronization_polished.json` |
| QA record | `results/qa_polished.json` |
| Post-processing log | `results/polish_log.json` |

v1 preserved: `output/final_silent_to_audio.mp4`, `audio/mixed/final_synchronized_audio.wav`.

---

## 1. The walking fix — the sound started too late

The reported problem was real: he begins walking well before the footstep audio came in.

Frame-by-frame analysis of the lower-body band (0.62–1.00 of frame height, 320×180) across the whole
pre-cup region found **four foot plants, not one**:

| Plant | 0.458 s | 1.083 s | 1.667 s | 2.208 s |
|---|---|---|---|---|
| interval | — | 0.625 | 0.584 | 0.541 |

A natural, slightly decelerating gait — and the first contact lands at **0.458 s**, more than a second
before the audio previously started.

### Why v1 missed it

**Module 2's label was misleading.** It marks 0.0–1.5 s as *"stand"*, but flags that segment
`status: suspect` with `flags: ["first_segment (window sees pre-action framing)"]`. The footage
disagrees with the label outright:

| Interval | Module 2 label | Mean lower-body motion |
|---|---|---|
| 0.0–1.5 s | stand | **1.708** |
| 1.5–2.5 s | walk around table | **1.711** |
| 2.5–5.5 s | pick up cup | 0.954 |

Motion during "stand" is indistinguishable from the labelled walk, and only collapses once he stops
at the table. The v1 pipeline had searched for foot contacts **only inside the Module 2 walk
interval**, so everything before 1.5 s was invisible to it.

**Two detector faults compounded it.** The feet band was too tall (0.55–1.00), and the prominence
threshold was set from the window's own range — at 0.25 it found only 2 of 4 plants. Testing both
bands across three prominence settings showed 0.62–1.00 finds all four **at every setting**, so it
was adopted for robustness rather than tuning.

### The fix

- Foot contacts are now searched across the whole walking sequence (`WALK_SEARCH_SPAN = 0.0–2.50 s`),
  documented in `m3_config.py` with the motion evidence above.
- The walking clip spans **0.158 → 2.500 s**, covering all four plants.
- Alignment matches a **consecutive run of four asset footsteps** to the four visible plants —
  every candidate run is scored on how well its internal spacing matches the visible gait, and the
  best is translated into place. The clip is **shifted only**: no stretching, resampling, or
  regeneration.
- The decay tail is clamped at 2.500 s so it never bleeds into the silent cup-pickup interval.

### Result — measured on the rendered audio

| Visible plant | Rendered attack | Error |
|---|---|---|
| 0.458 s | **0.458 s** | **−0 ms** |
| 1.083 s | 1.063 s | −20 ms |
| 1.667 s | 1.675 s | +8 ms |
| 2.208 s | 2.221 s | +13 ms |

The −20 ms residual is the asset's own step spacing differing slightly from the filmed gait. It was
**absorbed rather than corrected**, because correcting it would require time-stretching the approved
audio.

### A second bug fixed along the way

The planner had been aligning **onset-*strength* peaks**, which lag or lead the true transient attack
by −96 to +250 ms. Asset step "3.760 s" actually attacks at 3.856 s — so aligning it to a visual event
misplaced the audible footstep by exactly 96 ms, which is what v1's rendered audio showed. Onsets are
now **true envelope attack times**: each envelope maximum back-tracked to where it last rose through
20 % of that maximum.

## 2. Mix polish

Per clip, in order: DC removal → cut points snapped to the nearest zero crossing within ±3 ms
(removing edit clicks at source) → **12 ms raised-cosine** fades → level set by **active RMS** →
per-clip peak cap at −12 dBFS.

| Action | Active RMS | Target | Gain | Out peak | Snap |
|---|---|---|---|---|---|
| walk around table | −30.5 dBFS | −34.0 | **−4.05 dB** | −12.0 (capped) | +0.167 ms |
| drink from cup (1) | −46.0 dBFS | −38.0 | **+7.95 dB** | −18.2 | −0.021 ms |
| drink from cup (2) | −46.8 dBFS | −38.0 | **+8.75 dB** | −16.2 | +0.083 ms |
| place cup on table | −45.3 dBFS | −32.0 | **+13.27 dB** | −17.4 | +0.021 ms |

Drinking sits 4 dB under walking by design — a close-miked sip should not match footsteps in level.

**Bus:** summed peak −12.00 dBFS → **+6.00 dB of purely linear normalisation** to −6.0 dBFS. The
safety limiter (threshold −6, ceiling −3) **did not engage — 0.00 dB gain reduction**. No compression
of any kind was applied, so the balance above is exactly what is heard.

Final: peak **−6.00 dBFS**, RMS −36.87 dBFS, **crest factor 30.9 dB**.

## 3. Drinking and placement — timing unchanged

| Action | Visible event | Rendered attack | Error |
|---|---|---|---|
| drink from cup (1) | 6.625 s | 6.638 s | +13 ms |
| drink from cup (2) | 7.792 s | 7.803 s | +11 ms |
| place cup on table | 9.833 s | 9.833 s | **−0 ms** |

The placement keeps its 400 ms contact segment and natural decay; its tail is truncated 93.1 ms by
the end of the video, faded rather than extended.

## 4. QA — 17/17

| # | Check | Result |
|---|---|---|
| 1 | MP4 opens | ✅ 2 streams |
| 2 | Video duration preserved | ✅ 10.005 → 10.000 s |
| 3 | Video stream untouched | ✅ 240 frames, stream-copied |
| 4 | Audio duration matches video | ✅ 9.984 s vs 10.000 s |
| 5 | Sample rate | ✅ 48,000 Hz |
| 6 | Mono | ✅ 1 channel |
| 7 | No clipping | ✅ peak −6.00 dBFS |
| 8 | No NaN/Inf | ✅ |
| 9a | Walking sync | ✅ −0 / −20 / +8 / +13 ms across four contacts |
| 9b | Drinking sync | ✅ +13 / +11 ms |
| 9c | Placement sync | ✅ −0 ms |
| 10 | No edit clicks | ✅ all 8 boundaries clean |
| 11 | No bleed into silent actions | ✅ |
| 12 | Cup pickup still unavailable | ✅ silent, documented |
| 13 | Not over-compressed | ✅ limiter GR 0.0 dB, never engaged |
| 14 | Healthy crest factor | ✅ 30.9 dB |
| 15 | Original video unchanged | ✅ `a620ee58…` |
| 16 | Locked assets unchanged | ✅ 2/2 |
| 17 | v1 outputs not overwritten | ✅ both present |

## 5. Code

| File | Change |
|---|---|
| `scripts/m3_config.py` | `WALK_SEARCH_SPAN` with motion evidence; "stand" removed from the silent-action list |
| `scripts/visual_events.py` | feet band 0.62–1.00, prominence factor 0.15, widened walking search |
| `scripts/sync_actions.py` | true-attack onsets; N-contact consecutive-run matching; lead-in and tail clamped |
| `scripts/polish_mix.py` | **new** — DC removal, zero-crossing snap, raised-cosine fades, active-RMS balance, transparent normalisation, safety limiter |
| `scripts/build_polished_video.py` | **new** — mux polished audio, `-c:v copy` |
| `scripts/qa_polished.py` | **new** — 17-check gate, sync measured on rendered audio |
| `scripts/write_polished_report.py` | **new** — assembles the polished JSON record |
| `scripts/run_module3.py` | orchestrator now runs the full 10-step chain |

Rebuild everything: `moss/venv-moss/bin/python scripts/run_module3.py`

## Unchanged limitations

- **Cup pickup remains silent** (2.5–5.5 s) — no approved Foley, not fabricated.
- **Cup placement was never approved by listening** — 0.52 % energy in 1–5 kHz versus 28.96 % in the
  drinking asset. Included as instructed; if it sounds wrong the fix belongs in that asset.
- Drinking and placement visual events remain `medium` confidence; the four walking contacts are `high`.

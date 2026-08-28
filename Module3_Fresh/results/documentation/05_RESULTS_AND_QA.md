# Module 3 — Results and Quality Assurance

**Document version:** 1.0 (final)
**Verification date:** 2026-08-25
**Overall result:** all automated checks passed

---

## 1. Results table

| Action | Interval (Module 2) | Visual Event | Foley Used | Source Range | Synchronisation Error | Status |
|---|---|---|---|---|---|---|
| Stand | 0.0 – 1.5 s | *(covered by walking — see note)* | walking asset | — | — | Covered |
| Walk around table | 1.5 – 2.5 s | 4 foot plants:<br/>0.458 · 1.083 · 1.667 · 2.208 s | `walking_moss_v1_seed42.wav` | 0.498 – 2.839 s | −0 / **−20** / +8 / +13 ms | **Synchronised** |
| Pick up cup | 2.5 – 5.5 s | lift at 2.542 s | **none** | — | — | **Silent — no approved Foley** |
| Drink from cup | 5.5 – 8.5 s | sip hold 6.625 s | `drinking_moss_v2_local_seed42.wav` | 8.976 – 9.676 s | **+13 ms** | **Synchronised** |
| Drink from cup | 5.5 – 8.5 s | sip hold 7.792 s | `drinking_moss_v2_local_seed42.wav` | 1.601 – 2.301 s | **+11 ms** | **Synchronised** |
| Place cup on table | 8.5 – 10.0 s | mug-table contact 9.833 s | `cup_placement_foley_final.wav` | 0.000 – 0.400 s | **−0 ms** | **Synchronised** |

**Worst synchronisation error: 20 ms.** The video runs at 24 fps, so one frame is 41.7 ms; all
errors are below half a frame interval.

**Note on "Stand".** Module 2 labels 0.0–1.5 s as standing, but frame measurement shows lower-body
motion of 1.708 in that interval against 1.711 in the labelled walk — statistically indistinguishable.
The subject is walking from approximately 0.2 s, and the first two of four foot plants fall inside
the "stand" label. Footstep audio therefore spans 0.158 – 2.500 s. The Module 2 timeline itself was
not modified.

---

## 2. Placement detail

| Action | Placed at (video) | Duration | Raw active RMS | Target | Gain | Output peak |
|---|---|---|---|---|---|---|
| Walk around table | 0.158 – 2.500 s | 2.342 s | −30.5 dBFS | −34.0 dBFS | **−4.05 dB** | −12.0 dBFS |
| Drink from cup (1) | 6.288 – 6.988 s | 0.700 s | −46.0 dBFS | −38.0 dBFS | **+7.95 dB** | −18.2 dBFS |
| Drink from cup (2) | 7.453 – 8.153 s | 0.700 s | −46.8 dBFS | −38.0 dBFS | **+8.75 dB** | −16.2 dBFS |
| Place cup on table | 9.698 – 10.005 s | 0.307 s | −45.3 dBFS | −32.0 dBFS | **+13.27 dB** | −17.4 dBFS |

The placement clip was truncated by 93.1 ms with a fade because it would otherwise extend to 10.098 s,
past the end of the video.

---

## 3. Visual motion measurements

Mean absolute inter-frame difference per region band, by Module 2 action interval. These values are
the empirical basis for the detection strategies and for the "stand" finding above.

| Action interval | All | Feet | Head | Table |
|---|---|---|---|---|
| Stand (0.0–1.5 s) | 1.195 | **1.708** | 0.730 | 1.599 |
| Walk around table (1.5–2.5 s) | 1.358 | **1.711** | 0.959 | 1.882 |
| Pick up cup (2.5–5.5 s) | 0.935 | 0.954 | 0.845 | **1.272** |
| Drink from cup (5.5–8.5 s) | **0.277** | 0.145 | 0.387 | 0.247 |
| Place cup on table (8.5–10.0 s) | 0.672 | 0.446 | 0.801 | **0.807** |

Two observations follow directly:

- Feet motion is essentially equal across the "stand" and "walk" labels (1.708 vs 1.711), and falls
  by 44 % only at the cup pick-up. This is what justified widening the footstep search span.
- Drinking is by a wide margin the least visually active interval (0.277 overall). This is why sip
  holds are detected as motion *minima* rather than peaks.

---

## 4. Final audio measurements

| Property | Value |
|---|---|
| File | `audio/mixed/final_synchronized_audio_polished.wav` |
| Sample rate | 48,000 Hz |
| Channels | 1 (mono) |
| Format | PCM_16 |
| Duration | 10.005 s |
| Peak | −6.00 dBFS |
| RMS | −36.87 dBFS |
| Crest factor | 30.87 dB |
| Samples at or above full scale | 0 |
| NaN values | 0 |
| Inf values | 0 |

### Bus processing

| Stage | Value |
|---|---|
| Summed peak before processing | −12.00 dBFS |
| Linear normalisation applied | **+6.00 dB** |
| Normalisation target | −6.00 dBFS |
| Limiter threshold / ceiling | −6.0 / −3.0 dBFS |
| **Limiter gain reduction** | **0.00 dB — did not engage** |
| Final peak | −6.00 dBFS |

Because the limiter did not engage, no dynamic-range processing was applied. The crest factor of
30.87 dB confirms the transient structure of the source material is intact.

---

## 5. Quality gate

19 automated checks across 17 numbered categories. The synchronisation check is evaluated separately
for walking, drinking and placement, which accounts for the difference in counts.

| # | Check | Result | Measured value |
|---|---|---|---|
| 1 | Final MP4 opens | **PASS** | 2 streams |
| 2 | Video duration preserved | **PASS** | 10.005 s → 10.000 s |
| 3 | Video stream untouched | **PASS** | 240 frames, 1280×720, h264, stream-copied |
| 4 | Audio duration matches video | **PASS** | audio 9.984 s vs video 10.000 s (AAC frame granularity) |
| 5 | Sample rate | **PASS** | 48,000 Hz |
| 6 | Channel count | **PASS** | 1 (mono) |
| 7 | No clipping | **PASS** | peak −6.00 dBFS, 0 samples at full scale |
| 8 | No NaN/Inf | **PASS** | all samples finite |
| 9a | Walking synchronisation | **PASS** | −0 / −20 / +8 / +13 ms |
| 9b | Drinking synchronisation | **PASS** | +13 / +11 ms |
| 9c | Placement synchronisation | **PASS** | −0 ms |
| 10 | No edit-boundary discontinuities | **PASS** | all 8 clip boundaries clean |
| 11 | No bleed into silent intervals | **PASS** | zero overlap with the pick-up interval |
| 12 | Cup pickup documented unavailable | **PASS** | recorded in plan; no audio written |
| 13 | Not over-compressed | **PASS** | limiter gain reduction 0.00 dB |
| 14 | Healthy crest factor | **PASS** | 30.87 dB |
| 15 | Original video unchanged | **PASS** | SHA-256 `a620ee58…` |
| 16 | Locked assets unchanged | **PASS** | 2 of 2 verified |
| 17 | Earlier outputs not overwritten | **PASS** | first-pass mix and MP4 both present |

Synchronisation accuracy is measured on the **rendered audio**, by detecting envelope attack times in
the final WAV and comparing against the visual event timestamps. It is not asserted from the
synchronisation plan.

---

## 6. Integrity verification

| Artefact | SHA-256 (prefix) | Status |
|---|---|---|
| `input/test_video.mp4` | `a620ee5820ab9dfc…` | unchanged |
| `drinking_moss_v2_local_seed42.wav` | `a59f38c96bc15f6c…` | unchanged, write-protected |
| `walking_moss_v1_seed42.wav` | `0eae125b00cdbec0…` | unchanged, write-protected |

Both approved assets are held at filesystem permissions `r--r--r--` and recorded in
`results/APPROVED_ASSETS.lock`. Write attempts against them are refused by the operating system, and
this was tested rather than assumed.

The MOSS repository at `moss/MOSS-TTS` returns an empty `git status --porcelain`, confirming no source
file was modified. All MPS compatibility handling resides in the project's own wrapper.

---

## 7. Generation performance (recorded during asset creation)

Not part of the final build, which does not run the model. Recorded for completeness.

| Metric | Walking generation |
|---|---|
| Total wall time | 240.1 s |
| Phase 1 — text encoding | 4.75 s |
| Phase 2 — diffusion (50 steps) | 224.0 s |
| Phase 3 — decode | 8.20 s |
| Peak RAM | 11.68 GB |
| Minimum available RAM | 1.85 GB |
| Swap growth | **+0.01 GB** |
| Memory guard breach | none |

The 30-second internal latent is denoised regardless of the requested output duration, so generation
time is independent of the requested length.

---

## 8. Summary of outcomes by action

| Action | Foley obtained | In final output | Basis |
|---|---|---|---|
| Stand | n/a | covered by walking audio | frame measurement shows walking |
| Walk around table | yes | **yes** | approved on listening |
| Pick up cup | **no** | **no — silent** | 2 generations rejected; extraction not viable |
| Drink from cup | yes | **yes** | approved on listening |
| Place cup on table | yes, with reservation | **yes** | accepted on measurement, not approved on listening |

Four of the five action intervals carry synchronised audio. One is silent by decision rather than by
omission, and is documented as such in both the machine-readable record and this report.

---

*End of results and QA document.*

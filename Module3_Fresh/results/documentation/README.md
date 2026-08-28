# Module 3 — Documentation Package

**Project:** Silent Video → Synchronised Foley Audio
**Module:** 3 — Action-Conditioned Foley Generation and Visual Synchronisation
**Status:** final implementation, verified
**Build date:** 2026-08-25

---

## Purpose

Module 3 converts the action labels produced by Module 2 into synchronised Foley audio and combines
that audio with the original silent video to produce a final audio-visual output.

Its distinguishing design decision is that audio is aligned to **measured visual events** — the
instant a foot plants, a mug reaches the lips, a mug meets the table — rather than to Module 2's
action-label boundaries.

---

## Documents

| # | Document | Contents |
|---|---|---|
| 01 | [`01_MODULE3_TECHNICAL_DOCUMENTATION.md`](01_MODULE3_TECHNICAL_DOCUMENTATION.md) | Objective, inputs, action timeline, generation model, audio processing, visual synchronisation, final mix, limitations, technical contribution, reproducibility |
| 02 | [`02_SYSTEM_ARCHITECTURE.md`](02_SYSTEM_ARCHITECTURE.md) | Block diagram specification with per-block input/processing/output definitions |
| 03 | [`03_PROCESSING_FLOWCHART.md`](03_PROCESSING_FLOWCHART.md) | Complete pipeline flowchart, execution stages, decision points, per-action detection logic |
| 04 | [`04_PROMPTS_REFERENCE.md`](04_PROMPTS_REFERENCE.md) | Verbatim prompts and sampler settings for every generated asset, including the rejected cup-pickup attempts |
| 05 | [`05_RESULTS_AND_QA.md`](05_RESULTS_AND_QA.md) | Results table, measurements, 19-check quality gate, integrity verification |

Diagrams in documents 02 and 03 are specified in Mermaid, which renders in GitHub, VS Code, Typora and
most Markdown viewers. Document 02 also includes a plain-text equivalent of the block diagram.

---

## Final deliverables

| Artefact | Path |
|---|---|
| **Final video** | `Module3_Fresh/output/final_silent_to_audio_polished.mp4` |
| **Final audio** | `Module3_Fresh/audio/mixed/final_synchronized_audio_polished.wav` |
| Machine-readable record | `Module3_Fresh/results/final_synchronization_polished.json` |
| Quality-gate record | `Module3_Fresh/results/qa_polished.json` |
| Build report | `Module3_Fresh/results/final_module3_polished_report.md` |

---

## Headline results

| Metric | Value |
|---|---|
| Quality gate | all 19 automated checks passed |
| Worst synchronisation error | **20 ms** (< half a frame at 24 fps) |
| Walking foot plants located | 4, at 0.458 / 1.083 / 1.667 / 2.208 s |
| Walking alignment errors | −0 / −20 / +8 / +13 ms |
| Drinking alignment errors | +13 / +11 ms |
| Placement alignment error | −0 ms |
| Final audio | 48 kHz, mono, PCM_16, 10.005 s |
| Peak / RMS / crest factor | −6.00 dBFS / −36.87 dBFS / 30.87 dB |
| Clipping · NaN · Inf | none |
| Limiter gain reduction | 0.00 dB (did not engage) |
| Source video | unchanged, stream-copied |
| Approved Foley assets | unchanged, write-protected |
| MOSS repository | unmodified |

---

## Stated limitation

**Cup pickup (2.5 – 5.5 s) has no approved Foley and is silent in the final output.** Two model
generations and one extraction study were attempted; all three were rejected on measured evidence.
No substitute sound was fabricated. Full detail in document 01, §10.1.

A secondary reservation is recorded for the cup-placement asset, which was accepted on measurement
rather than on listening (document 01, §10.2).

---

## Reproducing the build

```bash
moss/venv-moss/bin/python scripts/run_module3.py
```

This rebuilds the synchronisation, mix, video and verification from the approved Foley assets. It
does **not** regenerate audio — assets are read from `audio/generated/`.

---

## Scope note

The pipeline has been implemented and verified on one 10-second test video. Generalisation to other
footage, camera angles or subjects has not been established, and the visual localisation method is
motion-based rather than pose- or object-tracking based.

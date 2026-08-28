# Action Recognition and Sound Generation

**Transform silent videos into synchronized sound.**

A web application that takes a silent video, recognises the physical actions in it,
generates matching Foley audio, aligns each sound to the exact frame where the action is
visible, mixes it, and returns a playable video with sound.

```
SILENT VIDEO → VIDEO VALIDATION → ACTION RECOGNITION → ACTION TIMELINE
→ FOLEY GENERATION → QUALITY VALIDATION → VISUAL EVENT LOCALIZATION
→ TEMPORAL ALIGNMENT → MIXING / POLISH → FFMPEG MERGE → FINAL VIDEO
```

Nine stages, each reporting real progress from the backend.

---

## What makes it more than stock sound effects

Action recognition returns broad intervals — *"walking, 1.5–2.5 s"*. But a footstep is
audible at one instant, not across a span. The system runs an **independent frame-level
motion analysis** to find the exact frames where a foot plants, a mug reaches the lips,
or a mug meets a table, and anchors each generated sound to those instants.

Generated clips are **shifted, never time-stretched**, and alignment uses true envelope
attack times rather than onset-strength peaks — the latter lead or lag the real transient
by −96 to +250 ms.

Every generated asset passes a **multi-criteria quality gate** (effective bits, dynamic
range, tonality, pure-tone detection, gain headroom) before it is allowed into the mix.
Up to three seeds are tried per sound class. An action with no usable Foley is left
**silent and reported** — never filled with a substitute.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 · Vite 6 · TypeScript · Tailwind CSS |
| Backend | FastAPI · Uvicorn · background jobs with real progress polling |
| Action recognition | Qwen2.5-VL-3B-Instruct (2.0 s windows, 1.0 s stride) |
| Sound generation | MOSS-SoundEffect v2.0 (DiT + flow matching, 48 kHz mono) |
| Analysis / render | librosa · NumPy · OpenCV · FFmpeg |
| Hardware | Apple Silicon (MPS) — M4, 16 GB |

Models run as **isolated subprocesses**, never imported into the API process: they need
incompatible PyTorch versions and each peaks near 12 GB of memory.

---

## Model selection

Five text-to-audio models were evaluated. MOSS-SoundEffect v2.0 was chosen after
listening tests backed by measurement. The discriminator is **harmonic ratio** — Foley
must be inharmonic; a musical tone is a failure.

| Sound class | MOSS score / harmonic | Stable Audio score / harmonic |
|---|---|---|
| Walking | 97.1 / **0.00** | 92.7 / 0.03 |
| Drinking | 70.9 / **0.06** | 75.6 / 0.09 |
| Cup pickup | 85.8 / **0.00** | 53.1 / **0.88** |
| Cup placement | 49.8 / **0.02** | 53.4 / **0.87** |

Stable Audio Open produced *musical tones* for object contacts — one output was a pure
346 Hz sine wave for "cup placed on a table". It remains available as a switchable
backend (`FOLEY_BACKEND=stable_audio`).

Also evaluated and rejected: **MMAudio**, **FoleyCrafter**, **AudioLDM 2**, **Stable
Audio Open Small**. The full written evaluations are in
[`Module3_Fresh/results/`](Module3_Fresh/results/).

---

## Repository layout

```
Module3_Fresh/                  the delivered system
├── backend/                    FastAPI service, 9-stage pipeline, tests
│   ├── api/                    HTTP routes
│   ├── core/                   config, job store
│   ├── services/               pipeline stages
│   ├── runners/                subprocess entry points (isolated envs)
│   └── tests/                  59 automated tests
├── frontend/src/               React + TypeScript UI
├── scripts/                    validated synchronisation & mixing implementation
├── moss/scripts/               MOSS wrappers (phase separation, MPS compatibility)
├── docs/                       architecture · api · pipeline · deployment
├── results/                    engineering record: evaluations, QA, analyses
├── audio/ · output/ · input/   demo assets and rendered results
└── HANDOFF.md                  full engineering context

03-FoleyCrafter-Test/action-recognition/    Module 2 source + evaluation record
```

---

## Setup

**Not in this repository** (reproducible, and too large or licence-restricted to
redistribute):

| Excluded | Size | How to obtain |
|---|---|---|
| Virtual environments | ~3 GB | `pip install` per `Module3_Fresh/docs/deployment.md` |
| MOSS-SoundEffect v2.0 weights | 10 GB | Hugging Face, per the deployment doc |
| `moss/MOSS-TTS/` | 26 MB | Clone upstream, pin commit `58b20a0` |
| Stable Audio Open 1.0 weights | 5 GB | Hugging Face — Stability AI Community licence, **non-commercial** |
| `node_modules/` | 80 MB | `npm install` |

Requires Python 3.12, Node 24, FFmpeg, and Apple Silicon with MPS.
Full instructions: [`Module3_Fresh/docs/deployment.md`](Module3_Fresh/docs/deployment.md).

## Running

```bash
cd Module3_Fresh
moss/venv-moss/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
cd Module3_Fresh/frontend && npm run dev     # http://localhost:5173
```

## Tests

```bash
cd Module3_Fresh
moss/venv-moss/bin/python backend/tests/test_suite.py             # 36 tests
moss/venv-moss/bin/python backend/tests/test_foley_validation.py  # 22 tests
moss/venv-moss/bin/python backend/tests/e2e_gate.py               # end-to-end
```

---

## Known limitations

- **Action recognition is the weakest link.** On one test video it missed a cup placement
  entirely and emitted a single action under three different labels. Sound generation can
  only be as good as the timeline it is given.
- Output is **sparse by design** — roughly 18% of a 10 s timeline carries audio for
  discrete object interactions. The silence between events is correct.
- A ~1.3B text-to-audio model on a laptop has a quality ceiling. Walking and drinking are
  strong; quiet ceramic contacts are the hardest class.
- **Apple Silicon only** — no CUDA or CPU path.
- Single-machine demonstrator: no authentication, queueing, or multi-user isolation.
- Visual localisation is motion-based, not pose or object tracking, and is validated on
  limited footage.

---

Final-year engineering project.

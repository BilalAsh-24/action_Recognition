# ACTION RECOGNITION AND SOUND GENERATION

**Transform silent videos into synchronized sound**

A web application that takes a silent video, recognises the physical actions in it,
generates matching Foley audio, aligns each sound to the exact frame where the action
is visible, mixes everything, and returns a playable video with sound.

```
SILENT VIDEO → VIDEO VALIDATION → MODULE 2 (ACTION RECOGNITION) → ACTION TIMELINE
→ MODULE 3 (SOUND GENERATION) → FOLEY QUALITY VALIDATION → VISUAL EVENT LOCALIZATION
→ AUDIO SYNCHRONIZATION → AUDIO MIXING / POLISH → FFMPEG MERGE → FINAL VIDEO WITH SOUND
```

Nine stages, every one reporting real progress from the backend.

---

## Project objective

Silent footage carries information about what is happening, but no sound. This project
reconstructs plausible, temporally correct audio from the picture alone.

The part that distinguishes it from attaching stock sound effects is **where** the audio
is placed. Action recognition returns broad intervals ("walking, 1.5–2.5 s"), but a
footstep is audible at one instant, not across a span. The system therefore runs an
independent frame-level analysis to find the exact frames where a foot plants, a mug
reaches the lips, or a mug meets a table, and anchors each sound to those instants.

## Module 2 — Action Recognition

| | |
|---|---|
| Model | `Qwen/Qwen2.5-VL-3B-Instruct` |
| Method | 2.0 s windows at 1.0 s stride, 8 frames per window, 448×252 |
| Output | per-window action + evidence → merged spans → deterministic non-overlapping timeline |
| Device | Apple Silicon MPS, bfloat16 |

The **video stream only** is decoded (`ffmpeg -map 0:v:0`); any audio already in the
upload is never read. Overlapping raw spans are resolved to a non-overlapping timeline
by midpoint boundary resolution before Module 3 consumes them.

## Module 3 — Sound Generation

| | |
|---|---|
| Model | `OpenMOSS-Team/MOSS-SoundEffect-v2.0` (Apache-2.0) |
| Architecture | Diffusion Transformer + Flow Matching · Qwen3 text encoder · DAC VAE |
| Output | 48 kHz mono, 10 s (30 s denoised internally, then cropped) |
| Device | Apple Silicon MPS, bfloat16 parameters |
| Defaults | seed 42 · 50 steps · cfg 4 · sigma_shift 5 |

Generation is **text-conditioned**: an action label is mapped to a Foley prompt, and the
model produces audio from that text. It runs in three memory-separated phases (text
encoder → DiT → VAE), so the three components are never co-resident.

## System architecture

```
┌───────────── React + Vite + TypeScript + Tailwind ─────────────┐
│  Upload · Preview · Live pipeline · Timeline · Results         │
└───────────────────────────┬────────────────────────────────────┘
                            │ REST (JSON + file streams)
┌───────────────────────────▼────────────────────────────────────┐
│                    FastAPI backend (Python 3.12)               │
│  jobs · video_service · action_recognition · sound_generation  │
│  synchronization · audio_processing · video_render             │
└──────┬───────────────────────────────┬─────────────────────────┘
       │ subprocess                    │ subprocess
┌──────▼─────────────┐        ┌────────▼──────────────┐
│ venv-qwen          │        │ venv-moss             │
│ Qwen2.5-VL-3B      │        │ MOSS-SoundEffect v2.0 │
│ (Module 2)         │        │ (Module 3)            │
└────────────────────┘        └───────────────────────┘
```

Each model runs in its own validated virtual environment, invoked as a subprocess. They
are never loaded into the same process, and never at the same time. No model inference
runs in the browser.

## Technologies

**Frontend** React 18 · Vite 6 · TypeScript · Tailwind CSS
**Backend** Python 3.12 · FastAPI · Uvicorn · NumPy · SciPy · soundfile · librosa
**AI** Qwen2.5-VL-3B-Instruct · MOSS-SoundEffect v2.0 · PyTorch 2.9.1 (MPS)
**Video** FFmpeg / FFprobe

---

## Requirements

| Requirement | Detail |
|---|---|
| Hardware | Apple Silicon (M-series). Built and verified on an Apple M4 with 17 GB unified memory |
| macOS | 26.2 verified; MPS required |
| Python | 3.12 (backend + MOSS), 3.10 (Module 2 environment) |
| PyTorch | 2.9.1 with working MPS |
| Node.js | 18+ (built with 24.8) |
| FFmpeg | must be on `PATH` |
| Disk | ~19 GB of model checkpoints (MOSS 11.2 GB, Qwen 7 GB) |
| Memory | 16 GB minimum. Peak observed 11.7 GB with a 1.5 GB guard |

The model environments and checkpoints are expected to be already installed — see
`docs/deployment.md`.

## Installation

```bash
# backend dependencies (into the existing MOSS environment)
moss/venv-moss/bin/python -m pip install fastapi "uvicorn[standard]" python-multipart

# frontend dependencies
cd frontend && npm install
```

## Running

**Backend** (terminal 1):

```bash
moss/venv-moss/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Frontend** (terminal 2):

```bash
cd frontend && npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` to the backend.
Interactive API docs are at <http://127.0.0.1:8000/docs>.

## Processing a video

1. Drag a silent video onto the upload panel (MP4 / MOV / AVI / M4V / MKV, ≤ 200 MB, ≤ 60 s).
2. Check the preview — duration, resolution, and whether an audio track was detected.
3. Optionally open **Advanced settings** to change seed, steps, CFG, sigma shift or duration.
4. Press **Generate Sound**. The pipeline runs eight stages with real backend progress.
5. When it finishes, preview the result and download the video or the audio.

**Demo mode** runs the same pipeline on the validated sample clip. It reuses the stored
Module 2 timeline for that specific video; Foley generation, synchronisation, mixing and
rendering all execute for real.

## Output format

| | |
|---|---|
| Video | original stream copied (`-c:v copy`) — no re-encoding, no quality loss |
| Audio | AAC 192 kbps, 48 kHz mono, generated from a 48 kHz mono PCM_16 master |
| Duration | identical to the source |
| Filename | `final_silent_to_audio.mp4` |

## Expected processing time

| Stage | Typical |
|---|---|
| Validation | < 1 s |
| Action recognition | ~5 s per window (≈1 min for a 10 s clip) |
| **Foley generation** | **~4 min per candidate** (cached afterwards) |
| Foley quality validation | < 2 s |
| Visual sync + mixing + render | < 20 s |

Generated Foley is cached by `action + prompt + seed + settings`, so a repeated request
reuses the asset and returns in seconds. A fully cached run completes in about 80 seconds.

**Multi-candidate generation.** MOSS occasionally collapses to degenerate output for a
given seed — near-silent, near-constant audio with no usable signal. Rather than accept
it, the system generates up to three candidates with successive seeds and keeps the
best that passes quality validation. Candidates are produced one at a time and the loop
stops as soon as one scores well, so a class that works on the first seed costs exactly
one generation. This measurably rescues classes that would otherwise be silent: cup
pickup failed on seeds 42 and 43 and succeeded on seed 44 with a quality score of 85.8
out of 100.

## Limitations

- **Apple Silicon only.** The pipeline depends on MPS; there is no CUDA or CPU path.
- **Foley generation is slow.** MOSS denoises a fixed 30-second latent regardless of the
  requested duration, so a short request costs the same as a long one.
- **Supported actions are a fixed set.** Sixteen Foley classes are defined in
  `backend/services/prompt_map.py`, covering walking, running, drinking, stirring, cup
  and spoon handling, doors, sitting, clapping, typing and pouring, plus generic object
  pickup/placement fallbacks. Unrecognised actions leave their interval silent and are
  reported to the user rather than filled with a substitute sound.
- **Output is sparse by nature.** These are discrete contact events, not continuous
  sound. A ten-second clip of object handling typically has audible audio across roughly
  a fifth of its timeline. Silence between events is correct, not a defect.
- **Action recognition is the limiting factor.** Module 3 can only sound as good as the
  timeline Module 2 supplies. In testing, Module 2 has missed events entirely and emitted
  the same action under several different labels.
- **Sound quality varies by action class.** Walking and drinking have been validated by
  listening; ceramic contact events measured weaker (see `results/documentation/`).
- **Visual localisation is motion-based**, not pose or object tracking. It has been
  validated on one clip; other camera angles and subjects are unverified.
- **Single-machine, single-job.** Jobs run in-process with no queue or multi-user
  isolation. This is a project demonstrator, not a production service.
- **Video length is capped at 60 s** because recognition cost grows linearly.

## Documentation

| Document | Contents |
|---|---|
| `docs/architecture.md` | components, data flow, design decisions |
| `docs/api.md` | every endpoint with request/response shapes |
| `docs/pipeline.md` | the eight processing stages in detail |
| `docs/deployment.md` | installation, environments, troubleshooting |
| `results/documentation/` | the underlying Module 3 engineering documentation |

## Testing

```bash
moss/venv-moss/bin/python backend/tests/test_suite.py            # 36 unit + integration
moss/venv-moss/bin/python backend/tests/test_foley_validation.py # 22 quality-gate tests
moss/venv-moss/bin/python backend/tests/e2e_gate.py              # cached-asset pipeline
moss/venv-moss/bin/python backend/tests/e2e_demo.py              # full run (regenerates)
```

59 automated tests in total.

## Project layout

```
Module3_Fresh/
├── frontend/          React + Vite + TypeScript + Tailwind
├── backend/
│   ├── main.py        FastAPI application
│   ├── api/           REST routes
│   ├── core/          config, job store
│   ├── services/      video, recognition, generation, sync, mixing, render
│   ├── runners/       scripts executed inside each model environment
│   └── tests/         unit + end-to-end tests
├── data/              uploads · jobs · generated (cache) · outputs
├── moss/              MOSS environment, checkpoints, phased wrapper
├── scripts/           validated Module 3 synchronisation implementation
└── results/           engineering documentation and validated build records
```

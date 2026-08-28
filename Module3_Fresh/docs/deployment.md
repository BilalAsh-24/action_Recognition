# Deployment and Setup

## Target platform

Built and verified on:

| | |
|---|---|
| Hardware | Apple M4, 17.18 GB unified memory |
| OS | macOS 26.2 (Darwin 25.2.0), arm64 |
| Node | 24.8.0 · npm 11.6.0 |

**Apple Silicon is required.** Both models run on MPS; there is no CUDA or CPU path.

## Prerequisites

| Component | Version | Check |
|---|---|---|
| FFmpeg + FFprobe | any recent | `ffmpeg -version` |
| Node.js | ≥ 18 | `node -v` |
| Python (backend/MOSS) | 3.12 | `moss/venv-moss/bin/python -V` |
| Python (Module 2) | 3.10 | `.../qwen/venv-qwen/bin/python -V` |

## Model environments

Two pre-existing virtual environments are used and must not be merged:

**`moss/venv-moss`** — Python 3.12, torch 2.9.1, transformers 4.57.1, diffusers 0.37.1,
numpy 1.26.4, descript-audiotools 0.7.2. Also hosts the FastAPI backend.

**`.../action-recognition/qwen/venv-qwen`** — Python 3.10, torch 2.13.0,
transformers 4.57.1. Module 2 only.

Verify MPS in both:

```bash
moss/venv-moss/bin/python -c "import torch; print(torch.backends.mps.is_available())"
```

## Checkpoints

| Model | Location | Size |
|---|---|---|
| MOSS-SoundEffect v2.0 | `moss/checkpoints/MOSS-SoundEffect-v2.0/` | 11.23 GB |
| Qwen2.5-VL-3B-Instruct | `~/.cache/huggingface/hub/` | 7.0 GB |

Both are expected to be present. The application does not download models at runtime.

## Backend dependencies

```bash
moss/venv-moss/bin/python -m pip install fastapi "uvicorn[standard]" python-multipart
```

Nothing else is added — NumPy, SciPy, soundfile and librosa are already present.

## Frontend

```bash
cd frontend
npm install
npm run build      # production bundle in dist/
```

## Running

```bash
# terminal 1 — backend
moss/venv-moss/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend
cd frontend && npm run dev
```

`http://localhost:5173` (UI) · `http://127.0.0.1:8000/docs` (API).

For a single-port deployment, serve `frontend/dist` from any static server and point it
at the backend, or mount it with `StaticFiles` in `backend/main.py`.

## Verifying the installation

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

All of `ffmpeg`, `action_recognition_env`, `sound_generation_env` and `moss_checkpoints`
should be `true`. The UI shows a **Degraded** badge if any is false.

```bash
moss/venv-moss/bin/python backend/tests/test_suite.py   # 31 tests
moss/venv-moss/bin/python backend/tests/e2e_demo.py     # full pipeline
```

## Resource behaviour

| Stage | Peak RAM | Duration |
|---|---|---|
| Action recognition | ~12 GB | ~5 s per window |
| Foley generation | ~11.7 GB | ~4 min per action |
| Sync + mix + render | < 1 GB | < 20 s |

Both model stages arm a 1.5 GB available-RAM guard and abort cleanly rather than driving
the machine into swap. Close other applications before processing; a low baseline is the
single biggest factor in reliability.

## Storage

| Directory | Contents | Growth |
|---|---|---|
| `data/uploads/` | source videos | per upload |
| `data/jobs/` | job records, Module 2 output, reports | small |
| `data/generated/` | **Foley cache** | ~960 KB per asset |
| `data/outputs/` | final MP4 and WAV | per job |

Nothing is deleted automatically. `data/generated/` is safe to clear — assets regenerate
on demand, at the cost of several minutes each.

## Troubleshooting

**Degraded badge in the UI** — call `/api/health` and check which component is false.

**"The action-recognition environment is unavailable"** — `venv-qwen` is missing or moved.
Confirm the path in `backend/core/config.py`.

**Processing stops during Foley generation** — usually memory. The job message will say
so. Close other applications; peak demand is ~11.7 GB.

**MPS reported unavailable** — verify with the command above. PyTorch issue #167679
affects torch 2.9.1 on macOS 26.0; it does not reproduce on 26.2.

**Upload rejected as undecodable** — the container may be valid but the codec unreadable
by the installed FFmpeg build. Re-encode to H.264 MP4.

**Generation seems to hang** — a single asset takes ~4 minutes on an unloaded machine and
longer under load. Check the backend log; the MOSS subprocess prints per-step progress.

## Security note

This is a project demonstrator, not a hardened service. There is no authentication, no
per-user isolation, no rate limiting, and CORS is fully open. Uploaded files are stored
unencrypted. Run it on localhost or a trusted network only.

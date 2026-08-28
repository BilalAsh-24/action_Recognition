"""Central configuration. All paths absolute; nothing outside these is written."""
from __future__ import annotations
import os
from pathlib import Path

MODULE3 = Path(__file__).resolve().parents[2]          # Module3_Fresh/
PROJECT = MODULE3.parent                                # Silent-Video-Project/

# ---- interpreters (each model runs in its own validated environment) --------
PY_MOSS = MODULE3 / "moss" / "venv-moss" / "bin" / "python"          # Py 3.12, torch 2.9.1
PY_QWEN = PROJECT / "03-FoleyCrafter-Test/action-recognition/qwen/venv-qwen/bin/python"
PY_STABLE = PROJECT / ("03-FoleyCrafter-Test/action-recognition/stable-audio/"
                       "venv-stable-audio/bin/python")

# ---- existing validated implementations (imported, never modified) ---------
MODULE2_SRC = PROJECT / "03-FoleyCrafter-Test" / "action-recognition"
MOSS_SCRIPTS = MODULE3 / "moss" / "scripts"
M3_SCRIPTS = MODULE3 / "scripts"
MOSS_CKPT = MODULE3 / "moss" / "checkpoints" / "MOSS-SoundEffect-v2.0"

RUNNERS = MODULE3 / "backend" / "runners"

# ---- data ------------------------------------------------------------------
DATA = MODULE3 / "data"
UPLOADS = DATA / "uploads"
JOBS = DATA / "jobs"
GENERATED = DATA / "generated"        # Foley cache, keyed by content hash
OUTPUTS = DATA / "outputs"
for d in (UPLOADS, JOBS, GENERATED, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)

# ---- demo asset (the validated test video) --------------------------------
DEMO_VIDEO = MODULE3 / "input" / "test_video.mp4"
DEMO_MODULE2 = MODULE3 / "module2" / "module2_action_segments.json"

# ---- generation defaults (validated settings) ------------------------------
DEFAULTS = {
    "model": "MOSS-SoundEffect-v2.0",
    "sample_rate": 48000,
    "channels": 1,
    "duration": 10.0,
    "steps": 50,
    "cfg_scale": 4.0,
    "sigma_shift": 5.0,
    "seed": 42,
    "max_candidates": 3,
}

# ---- Foley generation backends ---------------------------------------------
# Which model generates the Foley. Switchable at runtime via FOLEY_BACKEND, so both
# can be compared on the same pipeline without code changes.
# MOSS selected after A/B listening: its object-contact Foley is percussive
# (harmonic ratio 0.00-0.02) where Stable Audio produced tonal output (0.87-1.00).
# Stable Audio remains available via FOLEY_BACKEND=stable_audio.
GENERATION_BACKEND = os.environ.get("FOLEY_BACKEND", "moss")

BACKENDS = {
    "moss": {
        "label": "MOSS-SoundEffect v2.0",
        "model": "MOSS-SoundEffect-v2.0",
        "python": MODULE3 / "moss" / "venv-moss" / "bin" / "python",
        "native_sample_rate": 48000, "native_channels": 1,
        "defaults": {"steps": 50, "cfg_scale": 4.0, "sigma_shift": 5.0},
        "licence": "Apache-2.0",
    },
    "stable_audio": {
        "label": "Stable Audio Open 1.0",
        "model": "stabilityai/stable-audio-open-1.0",
        "python": PY_STABLE,
        "native_sample_rate": 44100, "native_channels": 2,   # converted to 48k mono
        "defaults": {"steps": 100, "cfg_scale": 7.0, "sigma_shift": 5.0},
        "licence": "Stability AI Community (non-commercial)",
    },
}


def backend(name: str | None = None) -> dict:
    return BACKENDS[name or GENERATION_BACKEND]


# the active backend's own sampler defaults become the request defaults
DEFAULTS["backend"] = GENERATION_BACKEND
DEFAULTS.update(BACKENDS[GENERATION_BACKEND]["defaults"])


# ---- limits ----------------------------------------------------------------
MAX_UPLOAD_MB = 200
MAX_VIDEO_SECONDS = 60          # Qwen windowing cost grows linearly
ALLOWED_SUFFIX = {".mp4", ".mov", ".avi", ".m4v", ".mkv"}
MIN_AVAILABLE_GB = 1.5          # memory guard shared by both model runners

# ---- audio / mix -----------------------------------------------------------
FADE_MS = 12.0
# Outlier guard only. At -12 dBFS this cap was binding on most clips, which made it —
# not the active-RMS targets — the thing setting relative level, flattening the
# dynamics between events. Raised so that per-class RMS balancing actually governs.
CLIP_PEAK_CEILING_DBFS = -6.0
BUS_TARGET_DBFS = -6.0
BUS_CEILING_DBFS = -3.0
LIMIT_THRESH_DBFS = -6.0

ENV_NO_PYC = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
              "TORCHDYNAMO_DISABLE": "1"}

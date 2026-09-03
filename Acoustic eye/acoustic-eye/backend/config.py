"""
Central configuration for the Acoustic Eye backend.

Nothing in the processing code hard-codes tunable numbers: everything that a
user might reasonably want to change lives here (or in an optional
``config.json`` placed next to this file).

The processing defaults intentionally mirror the "cheap" configuration used by
the reference Visual Microphone implementation (few pyramid scales /
orientations and aggressive spatial down-sampling) so that the demo runs on an
ordinary Windows laptop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------- #
# Paths – always resolved relative to the repository root, never absolute.
# --------------------------------------------------------------------------- #
BACKEND_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = BACKEND_DIR.parent

UPLOAD_DIR: Path = PROJECT_ROOT / "uploads"
OUTPUT_DIR: Path = PROJECT_ROOT / "outputs"
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"

for _d in (UPLOAD_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Upload / validation limits
# --------------------------------------------------------------------------- #
#: Accepted container extensions (lower-case, incl. leading dot).
ALLOWED_VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".avi", ".mov", ".mkv", ".webm")

#: Hard upper bound on the uploaded file size.
MAX_UPLOAD_MB: int = 250
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

#: A video must yield at least this many *successfully decoded* frames,
#: otherwise acoustic reconstruction is meaningless.
MIN_USABLE_FRAMES: int = 30

#: Frames beyond this count are ignored to keep processing time / memory bounded
#: on a typical PC.  Raise it in config.json if you have the resources.
#: High-speed captures need a lot of headroom: at 20 000 fps a single second of
#: footage is 20 000 frames.  Small ROIs (e.g. 192x192) build a steerable
#: pyramid in ~2 ms, so ~150 000 frames is a few minutes of CPU time.
MAX_PROCESS_FRAMES: int = 150_000


# --------------------------------------------------------------------------- #
# Local-file ingestion (for videos too large to upload through the browser)
# --------------------------------------------------------------------------- #
#: Allow the /process-local endpoint to read a video straight from a path on the
#: machine running the server (no HTTP upload, no size limit).  Set to False in
#: config.json to disable the feature entirely.
ALLOW_LOCAL_PATH_INGEST: bool = True

#: A local path passed to /process-local must resolve to a file *inside* one of
#: these directories.  Defaults to the current user's home folder, which covers
#: Desktop / Videos / Downloads etc.  Override with absolute paths in config.json
#: ("local_path_allowed_roots": ["D:\\footage", ...]).
LOCAL_PATH_ALLOWED_ROOTS: tuple[Path, ...] = (Path.home(), PROJECT_ROOT)

#: Default / maximum length (seconds) of the segment cut from a local file.
#: The Visual Microphone only needs a few seconds of footage; a long segment
#: mostly just costs processing time (one steerable pyramid per frame).
SEGMENT_DEFAULT_SECONDS: float = 10.0
SEGMENT_MAX_SECONDS: float = 30.0

# --------------------------------------------------------------------------- #
# Misc server settings (declared before the disk-config load so config.json may
# override them)
# --------------------------------------------------------------------------- #
#: How long (seconds) a finished job's files are kept before cleanup.
RESULT_TTL_SECONDS: int = 60 * 60 * 6  # 6 hours

#: CORS origins allowed to call the API (the bundled frontend is same-origin,
#: so this only matters if you serve the frontend elsewhere during development).
CORS_ORIGINS: tuple[str, ...] = ("http://localhost:8000", "http://127.0.0.1:8000")


# --------------------------------------------------------------------------- #
# Processing parameters
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProcessingConfig:
    """Tunable parameters for the Visual Microphone pipeline."""

    #: Spatial down-sampling applied to every frame before building the
    #: steerable pyramid.  1.0 = full resolution.  The reference code uses 0.1.
    downsample: float = 0.25

    #: Number of pyramid scales (``nscale`` in the reference code).
    scales: int = 1

    #: Number of pyramid orientations (``norientation`` in the reference code).
    #: Passed to pyrtools as ``orientations - 1`` (its "order" argument).
    orientations: int = 2

    #: High-pass cutoff for the final Butterworth filter, expressed as a
    #: fraction of the Nyquist frequency (0 < f < 1).  The reference code
    #: hard-codes 0.05; at 30 fps that removes everything below ~0.75 Hz, i.e.
    #: slow drift / DC.  Keep it small.
    high_pass_frequency: float = 0.05

    #: Butterworth filter order.
    high_pass_order: int = 3

    #: Apply Abe Davis' spectral-subtraction denoising as a second output.
    spectral_subtraction: bool = True

    #: Quantile used as the per-frequency noise floor in spectral subtraction.
    spec_sub_quantile: float = 0.5

    #: TRUE capture frame rate, used when the container's metadata is wrong.
    #: High-speed cameras routinely store a *playback* rate (e.g. 30 or 60 fps)
    #: in the AVI/MP4 header while having actually recorded at several kHz.
    #: Because the Visual Microphone emits one audio sample per frame, this
    #: number IS the output sample rate -- getting it wrong makes the result
    #: useless.  ``None`` means "trust the container".
    capture_fps: Optional[float] = None

    #: Mains frequency (50 or 60 Hz) whose harmonic comb should be notched out.
    #: Studio lighting for high-speed capture pulses at twice this, and that
    #: flicker is recovered as a huge tone that masks the acoustic signal.
    #: ``None``/0 disables the notch.
    mains_notch_hz: Optional[float] = None

    #: Low-pass cutoff in Hz applied to the recovered signal.  The phase
    #: estimate's noise is broadband, so on kHz-rate captures most output
    #: energy can be hiss well above the real content.  ``None``/0 disables it.
    low_pass_hz: Optional[float] = None

    #: Run optional offline speech-to-text (faster-whisper) on the result.
    #: Only meaningful for very high frame-rate captures; off by default and a
    #: no-op unless the package is installed.
    enable_transcription: bool = False

    # -- validation ------------------------------------------------------- #
    def validated(self) -> "ProcessingConfig":
        """Return a copy with every field clamped to a safe range."""
        return replace(
            self,
            downsample=_clamp(float(self.downsample), 0.02, 1.0),
            scales=int(_clamp(self.scales, 1, 6)),
            orientations=int(_clamp(self.orientations, 1, 8)),
            high_pass_frequency=_clamp(float(self.high_pass_frequency), 1e-4, 0.95),
            high_pass_order=int(_clamp(self.high_pass_order, 1, 8)),
            spectral_subtraction=bool(self.spectral_subtraction),
            spec_sub_quantile=_clamp(float(self.spec_sub_quantile), 0.05, 0.95),
            enable_transcription=bool(self.enable_transcription),
            mains_notch_hz=(
                None
                if self.mains_notch_hz in (None, 0)
                else _clamp(float(self.mains_notch_hz), 10.0, 1000.0)
            ),
            low_pass_hz=(
                None
                if self.low_pass_hz in (None, 0)
                else _clamp(float(self.low_pass_hz), 20.0, 200_000.0)
            ),
            capture_fps=(
                None
                if self.capture_fps in (None, 0)
                else _clamp(float(self.capture_fps), 1.0, 500_000.0)
            ),
        )

    def with_overrides(self, overrides: Dict[str, Any] | None) -> "ProcessingConfig":
        """Merge a partial dict of user overrides on top of these defaults."""
        if not overrides:
            return self.validated()
        allowed = {f for f in asdict(self)}
        clean = {k: v for k, v in overrides.items() if k in allowed and v is not None}
        return replace(self, **clean).validated()

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# Optional on-disk overrides (config.json next to this file)
# --------------------------------------------------------------------------- #
def _load_disk_config() -> ProcessingConfig:
    cfg_path = BACKEND_DIR / "config.json"
    base = ProcessingConfig()
    if not cfg_path.is_file():
        return base.validated()
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return base.validated()
    _apply_toplevel_overrides(data)
    return base.with_overrides(data.get("processing", data))


def _apply_toplevel_overrides(data: Dict[str, Any]) -> None:
    """Let config.json override the simple module-level server settings."""
    global MAX_UPLOAD_MB, MAX_UPLOAD_BYTES, MIN_USABLE_FRAMES, MAX_PROCESS_FRAMES
    global ALLOW_LOCAL_PATH_INGEST, LOCAL_PATH_ALLOWED_ROOTS
    global SEGMENT_DEFAULT_SECONDS, SEGMENT_MAX_SECONDS, RESULT_TTL_SECONDS

    if isinstance(data.get("max_upload_mb"), (int, float)):
        MAX_UPLOAD_MB = int(data["max_upload_mb"])
        MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
    if isinstance(data.get("min_usable_frames"), int):
        MIN_USABLE_FRAMES = max(2, data["min_usable_frames"])
    if isinstance(data.get("max_process_frames"), int):
        MAX_PROCESS_FRAMES = max(2, data["max_process_frames"])
    if isinstance(data.get("allow_local_path_ingest"), bool):
        ALLOW_LOCAL_PATH_INGEST = data["allow_local_path_ingest"]
    roots = data.get("local_path_allowed_roots")
    if isinstance(roots, list) and roots:
        LOCAL_PATH_ALLOWED_ROOTS = tuple(Path(r).expanduser().resolve() for r in roots)
    if isinstance(data.get("segment_default_seconds"), (int, float)):
        SEGMENT_DEFAULT_SECONDS = float(data["segment_default_seconds"])
    if isinstance(data.get("segment_max_seconds"), (int, float)):
        SEGMENT_MAX_SECONDS = float(data["segment_max_seconds"])
    if isinstance(data.get("result_ttl_seconds"), int):
        RESULT_TTL_SECONDS = data["result_ttl_seconds"]


#: Import this everywhere instead of instantiating ProcessingConfig directly.
DEFAULT_PROCESSING: ProcessingConfig = _load_disk_config()

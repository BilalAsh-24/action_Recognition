"""
REST API for Acoustic Eye.

Endpoints
---------
GET  /                       -- serves the frontend (index.html)
GET  /health                 -- dependency / capability report
POST /upload                 -- store + validate a video, return its metadata
POST /process                -- start reconstruction for a stored upload -> job id
POST /process-local          -- reconstruct a segment of a file already on disk
                                (for videos too large to upload) -> job id
GET  /status/{job_id}        -- poll pipeline stage progress
GET  /result/{filename}      -- download / stream a produced file (WAV / PNG)

Jobs run in a background thread.  Progress is reported per named stage; when a
true fraction is available (phase extraction) it is included, otherwise the
stage is 'running' with ``fraction: null`` and the UI shows an indeterminate
animation -- never a fabricated percentage.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import config as _cfg
from ..config import (
    DEFAULT_PROCESSING,
    MAX_PROCESS_FRAMES,
    MAX_UPLOAD_MB,
    MIN_USABLE_FRAMES,
    OUTPUT_DIR,
    SEGMENT_DEFAULT_SECONDS,
    SEGMENT_MAX_SECONDS,
)
from ..processing.pipeline import STAGES, PipelineError, PipelineResult, run_pipeline
from ..processing.video_reader import VideoValidationError, probe_video
from ..processing.text_report import transcription_available, transcription_import_error
from ..processing.visual_microphone import pyrtools_available, pyrtools_import_error
from ..utils.file_handler import (
    LocalIngestError,
    UploadError,
    cleanup_old_files,
    find_upload,
    new_job_id,
    resolve_local_video_path,
    resolve_output_file,
    save_stream_to_upload,
)

router = APIRouter()

# --------------------------------------------------------------------------- #
# In-memory job store (single-process; fine for a local demo server).
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    job_id: str
    status: str = "queued"  # queued | running | done | error
    stages: Dict[str, Dict[str, object]] = field(default_factory=dict)
    error: Optional[str] = None
    result: Optional[Dict[str, object]] = None
    created_at: float = field(default_factory=time.time)

    def init_stages(self) -> None:
        self.stages = {s: {"state": "pending", "fraction": None} for s in STAGES}


_JOBS: Dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _get_job(job_id: str) -> Job:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job


# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #
class ProcessOptions(BaseModel):
    downsample: Optional[float] = Field(None, ge=0.02, le=1.0)
    scales: Optional[int] = Field(None, ge=1, le=6)
    orientations: Optional[int] = Field(None, ge=1, le=8)
    high_pass_frequency: Optional[float] = Field(None, gt=0, lt=1)
    mains_notch_hz: Optional[float] = Field(
        None, ge=10, le=1000,
        description="Mains frequency (50 or 60) whose harmonic comb should be "
                    "notched out to remove lighting-flicker contamination.")
    low_pass_hz: Optional[float] = Field(
        None, ge=20, le=200_000,
        description="Low-pass cutoff in Hz for the recovered signal.")
    capture_fps: Optional[float] = Field(
        None, gt=0, le=500_000,
        description="True capture frame rate, when the file's own header is "
                    "wrong (common for high-speed cameras). This becomes the "
                    "output audio sample rate.")
    spectral_subtraction: Optional[bool] = None
    enable_transcription: Optional[bool] = None


class ProcessRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=64)
    options: ProcessOptions = Field(default_factory=ProcessOptions)


class LocalProcessRequest(BaseModel):
    """Process a segment of a video that already lives on the server machine."""

    path: str = Field(..., min_length=1, max_length=4096,
                      description="Absolute path to a video file on this computer.")
    start_seconds: float = Field(0.0, ge=0.0, le=86_400,
                                 description="Where in the source video to start.")
    duration_seconds: Optional[float] = Field(
        None, gt=0.0,
        description="Length of the segment to analyse (defaults to the server's "
                    "SEGMENT_DEFAULT_SECONDS, capped at SEGMENT_MAX_SECONDS).")
    options: ProcessOptions = Field(default_factory=ProcessOptions)


class UploadResponse(BaseModel):
    job_id: str
    video: Dict[str, object]
    limits: Dict[str, object]


class ProcessResponse(BaseModel):
    job_id: str
    status: str


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> JSONResponse:
    ok = pyrtools_available()
    return JSONResponse(
        {
            "status": "ok" if ok else "degraded",
            "pyrtools_available": ok,
            "pyrtools_error": pyrtools_import_error(),
            "max_upload_mb": MAX_UPLOAD_MB,
            "min_usable_frames": MIN_USABLE_FRAMES,
            "max_process_frames": MAX_PROCESS_FRAMES,
            "default_processing": DEFAULT_PROCESSING.as_dict(),
            "local_ingest": {
                "enabled": bool(getattr(_cfg, "ALLOW_LOCAL_PATH_INGEST", False)),
                "allowed_roots": [str(r) for r in getattr(_cfg, "LOCAL_PATH_ALLOWED_ROOTS", ())],
                "segment_default_seconds": SEGMENT_DEFAULT_SECONDS,
                "segment_max_seconds": SEGMENT_MAX_SECONDS,
            },
            "transcription_available": transcription_available(),
            "transcription_error": transcription_import_error(),
        }
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)) -> UploadResponse:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    cleanup_old_files()  # opportunistic housekeeping

    try:
        stored_path, job_id = save_stream_to_upload(file.file, file.filename)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    try:
        info = probe_video(
            stored_path,
            min_frames=MIN_USABLE_FRAMES,
            max_frames=MAX_PROCESS_FRAMES,
        )
    except VideoValidationError as exc:
        Path(stored_path).unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        Path(stored_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=f"The video could not be validated: {exc}",
        ) from exc

    with _JOBS_LOCK:
        job = Job(job_id=job_id)
        job.init_stages()
        _JOBS[job_id] = job

    return UploadResponse(
        job_id=job_id,
        video=info.as_dict(),
        limits={
            "min_usable_frames": MIN_USABLE_FRAMES,
            "max_process_frames": MAX_PROCESS_FRAMES,
            "pyrtools_available": pyrtools_available(),
        },
    )


@router.post("/process", response_model=ProcessResponse)
def start_processing(req: ProcessRequest) -> ProcessResponse:
    try:
        video_path = find_upload(req.job_id)
    except (FileNotFoundError, UploadError) as exc:
        raise HTTPException(
            status_code=404,
            detail="No validated upload found for this job id. Please upload again.",
        ) from exc

    if not pyrtools_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "pyrtools is not installed on the server, so the Visual "
                "Microphone algorithm cannot run. Install it with "
                "`pip install pyrtools` and restart the server."
            ),
        )

    with _JOBS_LOCK:
        job = _JOBS.get(req.job_id)
        if job is None:
            job = Job(job_id=req.job_id)
            _JOBS[req.job_id] = job
        if job.status == "running":
            raise HTTPException(status_code=409, detail="This job is already running.")
        job.init_stages()
        job.status = "running"
        job.error = None
        job.result = None

    cfg = DEFAULT_PROCESSING.with_overrides(req.options.model_dump(exclude_none=True))

    thread = threading.Thread(
        target=_run_job,
        args=(req.job_id, str(video_path), cfg),
        daemon=True,
        name=f"acoustic-eye-job-{req.job_id[:8]}",
    )
    thread.start()

    return ProcessResponse(job_id=req.job_id, status="running")


@router.post("/process-local")
def start_processing_local(req: LocalProcessRequest) -> JSONResponse:
    """Reconstruct a time segment of a video that already exists on the server
    machine -- no HTTP upload, no file-size limit.  Intended for footage that is
    too large to upload (e.g. multi-GB high-speed clips)."""
    if not pyrtools_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "pyrtools is not installed on the server, so the Visual "
                "Microphone algorithm cannot run. Install it with "
                "`pip install pyrtools` and restart the server."
            ),
        )

    try:
        video_path = resolve_local_video_path(req.path)
    except LocalIngestError as exc:
        # 403 when the feature is off, 400 for a bad/blocked path.
        disabled = "disabled on this server" in str(exc)
        raise HTTPException(status_code=403 if disabled else 400, detail=str(exc)) from exc

    duration = req.duration_seconds or SEGMENT_DEFAULT_SECONDS
    duration = float(max(1.0, min(duration, SEGMENT_MAX_SECONDS)))

    # Resolve the processing config first: the capture-rate override changes how
    # the requested time window maps onto frames, so validation needs it too.
    cfg = DEFAULT_PROCESSING.with_overrides(req.options.model_dump(exclude_none=True))

    # Validate the requested window up front so the user gets an immediate,
    # friendly error instead of a failed background job.
    try:
        info = probe_video(
            video_path,
            min_frames=MIN_USABLE_FRAMES,
            max_frames=MAX_PROCESS_FRAMES,
            start_seconds=req.start_seconds,
            window_seconds=duration,
            fps_override=cfg.capture_fps,
        )
    except VideoValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422, detail=f"The video could not be validated: {exc}"
        ) from exc

    job_id = new_job_id()
    with _JOBS_LOCK:
        job = Job(job_id=job_id)
        job.init_stages()
        job.status = "running"
        _JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, str(video_path), cfg),
        kwargs={"start_seconds": float(req.start_seconds), "max_seconds": duration},
        daemon=True,
        name=f"acoustic-eye-job-{job_id[:8]}",
    )
    thread.start()

    return JSONResponse(
        {
            "job_id": job_id,
            "status": "running",
            "video": info.as_dict(),
            "segment": {
                "start_seconds": round(float(req.start_seconds), 3),
                "duration_seconds": round(duration, 3),
            },
        }
    )


@router.get("/status/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    job = _get_job(job_id)
    with _JOBS_LOCK:
        payload = {
            "job_id": job.job_id,
            "status": job.status,
            "stages": [
                {"key": k, **v} for k, v in job.stages.items()
            ],
            "error": job.error,
            "result": job.result,
        }
    return JSONResponse(payload)


@router.get("/result/{filename}")
def get_result(filename: str):
    try:
        path = resolve_output_file(filename)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Result file not found.") from exc

    media = "application/octet-stream"
    if path.suffix.lower() == ".wav":
        media = "audio/wav"
    elif path.suffix.lower() == ".png":
        media = "image/png"
    return FileResponse(path, media_type=media, filename=path.name)


# --------------------------------------------------------------------------- #
# Background worker
# --------------------------------------------------------------------------- #
def _run_job(
    job_id: str,
    video_path: str,
    cfg,
    *,
    start_seconds: float = 0.0,
    max_seconds: Optional[float] = None,
) -> None:
    def stage_cb(stage: str, state: str, fraction: Optional[float]) -> None:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return
            entry = job.stages.setdefault(stage, {"state": "pending", "fraction": None})
            entry["state"] = state
            entry["fraction"] = (
                None if fraction is None else max(0.0, min(1.0, float(fraction)))
            )

    try:
        result: PipelineResult = run_pipeline(
            job_id=job_id,
            video_path=video_path,
            output_dir=OUTPUT_DIR,
            config=cfg,
            min_frames=MIN_USABLE_FRAMES,
            max_frames=MAX_PROCESS_FRAMES,
            start_seconds=start_seconds,
            max_seconds=max_seconds,
            stage_cb=stage_cb,
        )
    except PipelineError as exc:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job:
                job.status = "error"
                job.error = str(exc)
        return
    except Exception as exc:  # noqa: BLE001 - last-resort guard, never leak a traceback
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job:
                job.status = "error"
                job.error = (
                    "An unexpected error occurred during processing. "
                    f"({type(exc).__name__}: {exc})"
                )
        return

    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job:
            job.status = "done"
            job.result = result.as_dict()

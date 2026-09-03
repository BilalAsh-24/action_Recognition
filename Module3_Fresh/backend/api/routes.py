"""REST API for the Action Recognition and Sound Generation pipeline."""
from __future__ import annotations
import json, shutil, sys, uuid
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile, Body
from fastapi.responses import FileResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C
from core.jobs import STORE, STAGES
from services import video_service as VS
from services.prompt_map import supported_actions, vocabulary_mode
from services.pipeline import run_pipeline

router = APIRouter(prefix="/api")


def _job_or_404(job_id: str):
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job


@router.get("/health")
def health():
    ok_ff = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    active = C.backend()
    return {
        "status": "ok",
        "ffmpeg": ok_ff,
        "generation_backend": C.GENERATION_BACKEND,
        "backends": [{"key": k, "label": b["label"], "model": b["model"],
                      "licence": b["licence"],
                      "native": f"{b['native_sample_rate']} Hz / "
                                f"{'mono' if b['native_channels'] == 1 else 'stereo'}",
                      "available": Path(b["python"]).exists(),
                      "active": k == C.GENERATION_BACKEND}
                     for k, b in C.BACKENDS.items()],
        "active_backend_label": active["label"],
        "action_recognition_env": C.PY_QWEN.exists(),
        "sound_generation_env": C.PY_MOSS.exists(),
        "moss_checkpoints": C.MOSS_CKPT.is_dir(),
        "demo_available": C.DEMO_VIDEO.is_file(),
        "stages": [{"key": k, "label": l} for k, l in STAGES],
        "defaults": C.DEFAULTS,
        "limits": {"max_upload_mb": C.MAX_UPLOAD_MB,
                   "max_video_seconds": C.MAX_VIDEO_SECONDS,
                   "allowed": sorted(C.ALLOWED_SUFFIX)},
    }


@router.get("/actions/supported")
def actions_supported():
    # The curated list is no longer the limit of what can be sounded, so the
    # vocabulary block tells the caller that explicitly.
    return {"actions": supported_actions(), "vocabulary": vocabulary_mode()}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in C.ALLOWED_SUFFIX:
        raise HTTPException(400, f"Unsupported format '{suffix or 'unknown'}'. "
                                 f"Supported: {', '.join(sorted(C.ALLOWED_SUFFIX))}.")
    uid = uuid.uuid4().hex[:12]
    dest = C.UPLOADS / f"{uid}{suffix}"
    size = 0
    limit = C.MAX_UPLOAD_MB * 1024 * 1024
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                out.close(); dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds the {C.MAX_UPLOAD_MB} MB limit.")
            out.write(chunk)
    try:
        info = VS.probe(dest)
        warnings = VS.validate(info)
    except VS.VideoError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    job = STORE.create(video_path=str(dest), video_info=info.dict(),
                       warnings=warnings, settings=dict(C.DEFAULTS))
    return {"job_id": job.id, "video": info.dict(), "warnings": warnings,
            "original_filename": file.filename}


@router.post("/demo")
def demo():
    if not C.DEMO_VIDEO.is_file():
        raise HTTPException(404, "The demo video is not available on this installation.")
    info = VS.probe(C.DEMO_VIDEO)
    job = STORE.create(video_path=str(C.DEMO_VIDEO), video_info=info.dict(),
                       warnings=VS.validate(info), settings=dict(C.DEFAULTS), is_demo=True)
    return {"job_id": job.id, "video": info.dict(), "demo": True,
            "original_filename": C.DEMO_VIDEO.name,
            "note": "Demo mode reuses the validated Module 2 timeline for this clip. "
                    "Foley generation, synchronisation, mixing and rendering all run for real."}


@router.post("/process/{job_id}")
def process(job_id: str, settings: dict | None = Body(default=None)):
    job = _job_or_404(job_id)
    if job.status == "running":
        return {"job_id": job.id, "status": "running", "note": "Already processing."}
    if settings:
        allowed = {"seed", "steps", "cfg_scale", "sigma_shift", "duration",
                   "sample_rate", "max_candidates", "backend"}
        merged = {**(job.settings or C.DEFAULTS),
                  **{k: v for k, v in settings.items() if k in allowed}}
        STORE.update(job_id, settings=merged)
    STORE.update(job_id, status="queued", errors=[])
    STORE.run(job_id, run_pipeline)
    return {"job_id": job.id, "status": "queued"}


@router.get("/status/{job_id}")
def status(job_id: str):
    j = _job_or_404(job_id)
    return {"job_id": j.id, "status": j.status, "progress": j.progress,
            "current_stage": j.current_stage, "stages": j.stages,
            "errors": j.errors, "warnings": j.warnings,
            "counts": (j.report or {}).get("counts", {}),
            "generated_audio": [{"key": g["key"], "label": g["label"], "cached": g["cached"]}
                                for g in j.generated_audio],
            "updated_at": j.updated_at}


@router.get("/actions/{job_id}")
def actions(job_id: str):
    j = _job_or_404(job_id)
    return {"job_id": j.id, "actions": j.actions, "visual_events": j.visual_events,
            "unsupported": j.unsupported}


@router.get("/audio/{job_id}")
def audio(job_id: str):
    j = _job_or_404(job_id)
    if not j.final_audio or not Path(j.final_audio).is_file():
        raise HTTPException(404, "Audio is not ready yet.")
    return FileResponse(j.final_audio, media_type="audio/wav",
                        filename=f"{j.id}_audio.wav")


@router.get("/result/{job_id}")
def result(job_id: str):
    j = _job_or_404(job_id)
    if j.status != "completed":
        raise HTTPException(409, f"Job is '{j.status}', not completed.")
    r = j.report or {}
    return {"job_id": j.id, "video_url": f"/api/video/{j.id}",
            "audio_url": f"/api/audio/{j.id}",
            "download_url": f"/api/download/{j.id}",
            "counts": r.get("counts", {}), "sync": r.get("sync", {}),
            "mix": (r.get("mix") or {}).get("output", {}),
            "render": r.get("render", {}), "actions": j.actions,
            "generated": [{"key": g["key"], "label": g["label"], "cached": g["cached"]}
                          for g in j.generated_audio],
            "unsupported": j.unsupported}


@router.get("/video/{job_id}")
def video(job_id: str):
    j = _job_or_404(job_id)
    if not j.final_video or not Path(j.final_video).is_file():
        raise HTTPException(404, "The final video is not ready yet.")
    return FileResponse(j.final_video, media_type="video/mp4")


@router.get("/preview/{job_id}")
def preview(job_id: str):
    """Serve the uploaded source video for the pre-processing preview."""
    j = _job_or_404(job_id)
    if not j.video_path or not Path(j.video_path).is_file():
        raise HTTPException(404, "Source video not found.")
    return FileResponse(j.video_path, media_type="video/mp4")


@router.get("/download/{job_id}")
def download(job_id: str):
    j = _job_or_404(job_id)
    if not j.final_video or not Path(j.final_video).is_file():
        raise HTTPException(404, "The final video is not ready yet.")
    return FileResponse(j.final_video, media_type="video/mp4",
                        filename="final_silent_to_audio.mp4")


@router.get("/report/{job_id}")
def report(job_id: str):
    j = _job_or_404(job_id)
    if not j.report:
        raise HTTPException(404, "No report available yet.")
    return JSONResponse(j.report)


@router.get("/jobs")
def jobs(limit: int = 20):
    return {"jobs": [{"id": j.id, "status": j.status, "progress": j.progress,
                      "created_at": j.created_at, "is_demo": j.is_demo}
                     for j in STORE.list(limit)]}

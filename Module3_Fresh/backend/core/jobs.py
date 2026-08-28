"""In-process job store with a background worker. Persisted to disk so status
survives a reload and can be inspected after the fact."""
from __future__ import annotations
import json, threading, traceback, uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C

STAGES = [
    ("upload",             "Video uploaded"),
    ("validation",         "Video validation"),
    ("action_recognition", "Action recognition"),
    ("timeline",           "Action timeline generation"),
    ("foley_generation",   "Foley generation"),
    ("foley_validation",   "Foley quality validation"),
    ("visual_sync",        "Visual synchronization"),
    ("audio_mixing",       "Audio mixing"),
    ("rendering",          "Final video rendering"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: str = "created"              # created|queued|running|completed|failed|cancelled
    progress: float = 0.0                # 0..100
    current_stage: str = "upload"
    stages: dict[str, str] = field(default_factory=dict)   # stage -> pending|active|done|skipped|failed
    video_path: Optional[str] = None
    video_info: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    visual_events: list[dict] = field(default_factory=list)
    generated_audio: list[dict] = field(default_factory=list)
    unsupported: list[dict] = field(default_factory=list)
    mix: dict = field(default_factory=dict)
    final_video: Optional[str] = None
    final_audio: Optional[str] = None
    report: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    is_demo: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def dict(self) -> dict:
        return asdict(self)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}

    # ---------------------------------------------------------------- lifecycle
    def create(self, **kw) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(id=jid, stages={k: "pending" for k, _ in STAGES}, **kw)
        job.stages["upload"] = "done"
        with self._lock:
            self._jobs[jid] = job
        self._persist(job)
        return job

    def get(self, jid: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(jid)
        if job:
            return job
        f = C.JOBS / f"{jid}.json"
        if f.is_file():
            try:
                data = json.loads(f.read_text())
                job = Job(**data)
                with self._lock:
                    self._jobs[jid] = job
                return job
            except Exception:
                return None
        return None

    def list(self, limit: int = 50) -> list[Job]:
        with self._lock:
            js = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return js[:limit]

    # ------------------------------------------------------------------ updates
    def update(self, jid: str, **kw) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return None
            for k, v in kw.items():
                setattr(job, k, v)
            job.updated_at = _now()
        self._persist(job)
        return job

    def stage(self, jid: str, stage: str, state: str, progress: Optional[float] = None,
              **extra) -> None:
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return
            job.stages[stage] = state
            if state == "active":
                job.current_stage = stage
            if progress is not None:
                job.progress = round(max(job.progress, min(100.0, progress)), 1)
            for k, v in extra.items():
                setattr(job, k, v)
            job.updated_at = _now()
        self._persist(job)

    def fail(self, jid: str, message: str, stage: Optional[str] = None) -> None:
        with self._lock:
            job = self._jobs.get(jid)
            if not job:
                return
            job.status = "failed"
            job.errors.append(message)
            if stage:
                job.stages[stage] = "failed"
            job.finished_at = _now(); job.updated_at = _now()
        self._persist(job)

    def _persist(self, job: Job) -> None:
        try:
            (C.JOBS / f"{job.id}.json").write_text(json.dumps(job.dict(), indent=2))
        except Exception:
            pass

    # ------------------------------------------------------------------ running
    def run(self, jid: str, fn: Callable[[Job, "JobStore"], Any]) -> None:
        job = self.get(jid)
        if not job or job.status == "running":
            return
        self.update(jid, status="running", started_at=_now(), progress=2.0)

        def _target():
            try:
                fn(self.get(jid), self)
                j = self.get(jid)
                if j and j.status == "running":
                    self.update(jid, status="completed", progress=100.0,
                                finished_at=_now(), current_stage="done")
            except Exception as exc:
                # Full detail to the backend log; a readable message to the user.
                traceback.print_exc()
                msg = str(exc) or exc.__class__.__name__
                self.fail(jid, msg, stage=(self.get(jid).current_stage if self.get(jid) else None))

        t = threading.Thread(target=_target, daemon=True, name=f"job-{jid}")
        self._threads[jid] = t
        t.start()


STORE = JobStore()

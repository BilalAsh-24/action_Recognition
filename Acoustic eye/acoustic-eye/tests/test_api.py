"""Smoke tests for the FastAPI layer (no pyrtools required)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "pyrtools_available" in body
    assert "default_processing" in body
    assert "local_ingest" in body
    assert "enabled" in body["local_ingest"]
    assert "transcription_available" in body


def test_index_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "ACOUSTIC EYE" in res.text


def test_upload_rejects_bad_extension(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    res = client.post("/upload", files={"file": ("note.txt", f.read_bytes(), "text/plain")})
    assert res.status_code == 400


def test_upload_rejects_empty_file():
    res = client.post("/upload", files={"file": ("clip.mp4", b"", "video/mp4")})
    assert res.status_code == 400


def test_upload_accepts_and_validates_real_video(valid_video: Path):
    data = valid_video.read_bytes()
    res = client.post("/upload", files={"file": ("valid.avi", data, "video/x-msvideo")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["video"]["frames_read"] >= 40
    assert "job_id" in body


def test_result_path_traversal_blocked():
    res = client.get("/result/..%2F..%2Fbackend%2Fmain.py")
    assert res.status_code in (400, 404)


def test_status_unknown_job():
    res = client.get("/status/deadbeefdeadbeef")
    assert res.status_code == 404


# --------------------------- /process-local --------------------------- #
def test_process_local_missing_path_is_400():
    res = client.post("/process-local", json={"path": "   "})
    assert res.status_code in (400, 422)


def test_process_local_nonexistent_path_is_400():
    res = client.post("/process-local", json={"path": "Z:\\nope\\missing.mp4"})
    assert res.status_code == 400


def test_process_local_outside_allowed_roots_blocked(valid_video: Path, monkeypatch):
    # Restrict allowed roots to the project dir; the pytest tmp file is outside it.
    from backend import config as cfg
    from backend.api import routes

    proj_only = (cfg.PROJECT_ROOT.resolve(),)
    monkeypatch.setattr(cfg, "LOCAL_PATH_ALLOWED_ROOTS", proj_only)
    monkeypatch.setattr(routes._cfg, "LOCAL_PATH_ALLOWED_ROOTS", proj_only)

    res = client.post("/process-local", json={"path": str(valid_video)})
    assert res.status_code == 400
    assert "allowed folder" in res.json()["detail"].lower()


def test_process_local_runs_when_root_allowed(long_video: Path, monkeypatch, pyrtools_required):
    import time
    from backend import config as cfg
    from backend.api import routes

    monkeypatch.setattr(cfg, "LOCAL_PATH_ALLOWED_ROOTS", (long_video.parent.resolve(),))
    monkeypatch.setattr(routes._cfg, "LOCAL_PATH_ALLOWED_ROOTS", (long_video.parent.resolve(),))

    res = client.post("/process-local", json={
        "path": str(long_video),
        "start_seconds": 0.5,
        "duration_seconds": 2.0,
        "options": {"downsample": 1.0, "scales": 1, "orientations": 2},
    })
    assert res.status_code == 200, res.text
    body = res.json()
    jid = body["job_id"]
    assert body["video"]["segment_start_seconds"] == pytest.approx(0.5, abs=0.25)

    for _ in range(120):
        s = client.get(f"/status/{jid}").json()
        if s["status"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert s["status"] == "done", s.get("error")
    assert s["result"]["frames_processed"] >= 20
    assert client.get("/result/" + s["result"]["wav_filename"]).status_code == 200

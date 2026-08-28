"""Module 2 wrapper. Runs Qwen2.5-VL in its own validated environment (venv-qwen)."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C


class ActionRecognitionError(Exception):
    pass


def run(video: Path, out_json: Path, progress_file: Path | None = None,
        timeout_s: int = 3600) -> dict:
    """Execute Module 2 and return its payload. Blocking; call from a worker thread."""
    if not C.PY_QWEN.exists():
        raise ActionRecognitionError(
            "The action-recognition environment is unavailable on this machine.")
    cmd = [str(C.PY_QWEN), str(C.RUNNERS / "run_module2.py"),
           "--video", str(video), "--out", str(out_json),
           "--min-avail-gb", str(C.MIN_AVAILABLE_GB)]
    if progress_file:
        cmd += ["--progress", str(progress_file)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                       env=C.ENV_NO_PYC, cwd=str(C.MODULE3))
    if p.returncode != 0:
        detail = (p.stderr or "").strip().splitlines()
        msg = detail[-1] if detail else "unknown error"
        try:
            msg = json.loads(msg).get("error", msg)
        except Exception:
            pass
        if "MemoryError" in msg or "available RAM" in msg:
            raise ActionRecognitionError(
                "Action recognition stopped because the machine ran low on memory. "
                "Close other applications and try again.")
        raise ActionRecognitionError(f"Action recognition failed: {msg}")
    if not Path(out_json).is_file():
        raise ActionRecognitionError("Action recognition produced no output.")
    return json.loads(Path(out_json).read_text())


def load_existing(path: Path) -> dict:
    """Load a Module 2 payload that already exists (demo mode)."""
    return json.loads(Path(path).read_text())

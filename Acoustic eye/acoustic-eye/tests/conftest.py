"""
Shared pytest fixtures.

The heavy Visual Microphone run is expensive, so the fixtures here build *tiny*
synthetic videos (64x64, a few dozen frames) with a known, moving brightness
pattern that stands in for a sound-induced vibration.  That is enough to
exercise every code path without a multi-minute test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Make ``import backend...`` work when pytest is run from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2 as cv  # noqa: E402


def _write_video(path: Path, n_frames: int, size: int = 64, fps: int = 30) -> Path:
    """Write a synthetic AVI (MJPG) with a horizontally drifting sine grating.

    MJPG/AVI is used because it is available on essentially every OpenCV build,
    including headless wheels on Windows.
    """
    fourcc = cv.VideoWriter_fourcc(*"MJPG")
    writer = cv.VideoWriter(str(path), fourcc, fps, (size, size), isColor=True)
    if not writer.isOpened():  # pragma: no cover - environment dependent
        pytest.skip("OpenCV has no usable MJPG/AVI encoder in this environment.")

    xx = np.arange(size, dtype=np.float64)
    for i in range(n_frames):
        phase = 2.0 * np.pi * (0.06 * i)          # sub-pixel drift over time
        row = 0.5 + 0.4 * np.sin(2.0 * np.pi * xx / 12.0 + phase)
        img = np.tile(row, (size, 1))
        img8 = np.clip(img * 255.0, 0, 255).astype(np.uint8)
        writer.write(cv.cvtColor(img8, cv.COLOR_GRAY2BGR))
    writer.release()
    if not path.is_file() or path.stat().st_size == 0:  # pragma: no cover
        pytest.skip("Synthetic video could not be written by OpenCV.")
    return path


@pytest.fixture
def valid_video(tmp_path: Path) -> Path:
    return _write_video(tmp_path / "valid.avi", n_frames=48, size=64, fps=30)


@pytest.fixture
def short_video(tmp_path: Path) -> Path:
    return _write_video(tmp_path / "short.avi", n_frames=5, size=64, fps=30)


@pytest.fixture
def long_video(tmp_path: Path) -> Path:
    """~4 s clip so a mid-file segment can be requested."""
    return _write_video(tmp_path / "long.avi", n_frames=120, size=64, fps=30)


@pytest.fixture
def empty_video(tmp_path: Path) -> Path:
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    return p


@pytest.fixture
def corrupt_video(tmp_path: Path) -> Path:
    p = tmp_path / "corrupt.mp4"
    p.write_bytes(b"\x00\x01\x02not a real video\xff\xd8\xff" * 40)
    return p


@pytest.fixture
def pyrtools_required():
    pytest.importorskip("pyrtools", reason="pyrtools not installed")

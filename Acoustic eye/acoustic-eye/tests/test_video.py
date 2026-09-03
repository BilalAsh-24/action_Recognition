"""Tests for backend.processing.video_reader — robust reading + frame counting."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.processing.video_reader import (
    VideoValidationError,
    iter_gray_norm_frames,
    probe_video,
)

MIN_FRAMES = 10
MAX_FRAMES = 500


def test_probe_valid_video(valid_video: Path):
    info = probe_video(valid_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES)
    assert info.width == 64 and info.height == 64
    assert info.fps > 0
    # The real decoded count must be used, and be close to what we wrote (48).
    assert 40 <= info.frames_read <= 48
    assert info.duration_seconds > 0
    assert isinstance(info.as_dict(), dict)


def test_probe_empty_video_rejected(empty_video: Path):
    with pytest.raises(VideoValidationError):
        probe_video(empty_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES)


def test_probe_corrupt_video_rejected(corrupt_video: Path):
    with pytest.raises(VideoValidationError):
        probe_video(corrupt_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES)


def test_probe_too_few_frames_rejected(short_video: Path):
    with pytest.raises(VideoValidationError):
        probe_video(short_video, min_frames=30, max_frames=MAX_FRAMES)


def test_probe_missing_file():
    with pytest.raises(VideoValidationError):
        probe_video(Path("does-not-exist.mp4"), min_frames=MIN_FRAMES, max_frames=MAX_FRAMES)


def test_iter_frames_counts_and_shapes(valid_video: Path):
    frames = list(iter_gray_norm_frames(valid_video, downsample=1.0, max_frames=MAX_FRAMES))
    assert len(frames) >= 40
    f0 = frames[0]
    assert f0.ndim == 2
    assert f0.dtype.kind == "f"
    assert 0.0 <= float(f0.min()) <= float(f0.max()) <= 1.0


def test_iter_frames_respects_max_frames(valid_video: Path):
    frames = list(iter_gray_norm_frames(valid_video, downsample=1.0, max_frames=7))
    assert len(frames) == 7


def test_iter_frames_downsample_relaxed_for_small_input(valid_video: Path):
    # 0.1 * 64 = 6.4 px -> too small; reader should relax the factor upward.
    frames = list(iter_gray_norm_frames(valid_video, downsample=0.1, max_frames=MAX_FRAMES))
    assert len(frames) >= 40
    assert min(frames[0].shape) >= 16


# --------------------------- segment / local mode ----------------------- #
def test_probe_segment_limits_frame_count(long_video: Path):
    full = probe_video(long_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES)
    seg = probe_video(
        long_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES,
        start_seconds=1.0, window_seconds=1.0,
    )
    # ~30 fps * 1 s window -> ~30 frames, and fewer than the whole file.
    assert seg.frames_read < full.frames_read
    assert 20 <= seg.frames_read <= 40
    assert seg.segment_start_seconds == pytest.approx(1.0, abs=0.2)
    assert seg.source_duration_seconds > seg.duration_seconds


def test_probe_segment_start_past_end_rejected(long_video: Path):
    import pytest as _pt
    with _pt.raises(VideoValidationError):
        probe_video(long_video, min_frames=MIN_FRAMES, max_frames=MAX_FRAMES,
                    start_seconds=999.0, window_seconds=1.0)


def test_iter_frames_with_start_offset(long_video: Path):
    head = list(iter_gray_norm_frames(long_video, downsample=1.0, max_frames=20))
    tail = list(iter_gray_norm_frames(long_video, downsample=1.0, max_frames=20,
                                      start_seconds=1.5))
    assert len(head) == 20 and len(tail) == 20
    # Different point in the (drifting) synthetic video -> different pixels.
    assert not (head[0] == tail[0]).all()

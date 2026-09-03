"""
Robust video reading and validation.

Design notes
------------
The reference implementation (visual-mic-master/visualmic/sound_from_video.py)
allocates its output buffer with::

    nframes = int(video.get(cv.CAP_PROP_FRAME_COUNT))
    ...
    sound = np.zeros(nframes)

``CAP_PROP_FRAME_COUNT`` is frequently wrong: it is derived from the container
metadata (duration * fps) and does not account for corrupt / dropped frames,
truncated files, or variable-frame-rate encodes.  Acoustic Eye therefore never
trusts that number for allocation.  Instead it *decodes* frames and counts the
ones that actually come back, and every downstream array is sized from that
real count.

This module exposes:

* :class:`VideoInfo`      -- metadata + real frame count
* :func:`probe_video`     -- validate a file and gather :class:`VideoInfo`
* :func:`iter_gray_norm_frames` -- generator of pre-processed float frames
* :class:`VideoValidationError` -- raised with a user-friendly message
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterator, Optional

import cv2 as cv
import numpy as np


class VideoValidationError(Exception):
    """Raised when a video cannot be used for acoustic reconstruction.

    The message is safe to show directly to an end user.
    """


@dataclass
class VideoInfo:
    """Everything the frontend needs to describe an uploaded video."""

    filename: str
    path: str
    width: int
    height: int
    fps: float
    #: The frame rate actually used for all timing / sample-rate maths.  When a
    #: capture-rate override is supplied this is that override, and
    #: ``container_fps`` keeps whatever the file's own header claimed.
    container_fps: float
    fps_overridden: bool
    frame_count_metadata: int
    frames_read: int
    duration_seconds: float
    fourcc: str
    #: For local-file segment processing: where the analysed window starts, and
    #: the approximate length of the whole source file.  0 / equal-to-duration
    #: for a normal full upload.
    segment_start_seconds: float = 0.0
    source_duration_seconds: float = 0.0

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def _decode_fourcc(value: float) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return ""
    if code <= 0:
        return ""
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ").strip()


def _count_real_frames(cap: cv.VideoCapture, hard_cap: int) -> int:
    """Count frames that can actually be grabbed from the demuxer.

    Uses ``grab()`` (no pixel decode) for speed.  ``grab()`` succeeding is a
    good proxy for "this frame exists and is not truncated"; the heavier
    decode + colour-convert happens later in :func:`iter_gray_norm_frames`,
    which independently skips anything that fails to decode.
    """
    count = 0
    while count < hard_cap and cap.grab():
        count += 1
    return count


def _seek_to_frame(cap: cv.VideoCapture, target_frame: int) -> int:
    """Position ``cap`` at ``target_frame`` and report where it really landed.

    We deliberately seek by *frame index* rather than by ``CAP_PROP_POS_MSEC``:
    the millisecond timebase is derived from the container's declared frame
    rate, which for high-speed footage is a playback placeholder (e.g. 30 fps
    on a 20 000 fps capture).  Frame indices are unambiguous.

    Falls back to grab-skipping, which works on any codec/container and on
    files whose index is missing or truncated -- exactly the case for a
    partially downloaded OpenDML AVI.
    """
    if target_frame <= 0:
        return 0

    if cap.set(cv.CAP_PROP_POS_FRAMES, float(target_frame)):
        pos = cap.get(cv.CAP_PROP_POS_FRAMES)
        if pos and abs(pos - target_frame) <= 1.0:
            return int(pos)

    # Fallback: rewind and skip forward one frame at a time.
    cap.set(cv.CAP_PROP_POS_FRAMES, 0.0)
    skipped = 0
    while skipped < target_frame and cap.grab():
        skipped += 1
    return skipped


def _window_cap(window_seconds: Optional[float], fps: float, hard_cap: int) -> int:
    """Frame ceiling for a time-limited segment (never more than ``hard_cap``)."""
    if window_seconds and window_seconds > 0 and fps > 0:
        return max(1, min(hard_cap, int(round(window_seconds * fps)) + 1))
    return hard_cap


def probe_video(
    path: str | Path,
    *,
    min_frames: int,
    max_frames: int,
    start_seconds: float = 0.0,
    window_seconds: Optional[float] = None,
    fps_override: Optional[float] = None,
) -> VideoInfo:
    """Open, validate and describe a video file (optionally just a segment).

    Parameters
    ----------
    path:
        Location of the (already safely stored / whitelisted) video file.
    min_frames:
        Minimum number of real frames required; below this we refuse the job.
    max_frames:
        Frames are counted up to this ceiling (processing will also stop here).
    start_seconds:
        Offset to seek to before counting (local-file segment mode).
    window_seconds:
        If given, only count frames within this many seconds of ``start_seconds``.

    Raises
    ------
    VideoValidationError
        With a message suitable for display to the user.
    """
    p = Path(path)
    if not p.is_file():
        raise VideoValidationError("The video file could not be found on the server.")
    if p.stat().st_size == 0:
        raise VideoValidationError("The video file is empty.")

    cap = cv.VideoCapture(str(p))
    try:
        if not cap.isOpened():
            raise VideoValidationError(
                "This file could not be opened as a video. It may be corrupted, "
                "an unsupported codec, or not a video at all."
            )

        width = int(round(cap.get(cv.CAP_PROP_FRAME_WIDTH)))
        height = int(round(cap.get(cv.CAP_PROP_FRAME_HEIGHT)))
        fps_raw = float(cap.get(cv.CAP_PROP_FPS))
        meta_count = int(cap.get(cv.CAP_PROP_FRAME_COUNT) or 0)
        fourcc = _decode_fourcc(cap.get(cv.CAP_PROP_FOURCC))

        container_fps = fps_raw if (np.isfinite(fps_raw) and fps_raw > 0) else 0.0
        if container_fps == 0.0:
            container_fps = 30.0  # fall back to a common capture rate

        # A supplied capture rate always wins: the container's header is only a
        # hint, and for high-speed cameras it is routinely wrong.
        fps_overridden = bool(fps_override and fps_override > 0)
        fps = float(fps_override) if fps_overridden else container_fps

        source_duration = (meta_count / fps) if (meta_count > 0 and fps > 0) else 0.0

        start_seconds = max(0.0, float(start_seconds))
        if source_duration and start_seconds >= source_duration:
            raise VideoValidationError(
                f"The requested start time ({start_seconds:.1f}s) is at or past the "
                f"end of the video (~{source_duration:.1f}s). Pick an earlier start."
            )
        if start_seconds > 0:
            _seek_to_frame(cap, int(round(start_seconds * fps)))

        # Sanity-check a first decoded frame: guards against "opens fine but
        # every frame is garbage / audio-only container".
        ok, first = cap.read()
        if not ok or first is None or first.size == 0:
            raise VideoValidationError(
                "No image frames could be read from this file. Audio-only files "
                "and videos with no decodable video stream are not supported."
            )
        if first.ndim < 2:
            raise VideoValidationError("The video frames have an unexpected shape.")

        # We already consumed one frame with read(); count the rest with grab(),
        # bounded by both max_frames and the requested time window.
        ceiling = _window_cap(window_seconds, fps, max_frames)
        frames_read = 1 + _count_real_frames(cap, ceiling - 1)

        if width <= 0 or height <= 0:
            height, width = int(first.shape[0]), int(first.shape[1])

        duration = frames_read / fps if fps > 0 else 0.0

        if frames_read < min_frames:
            hint = (
                "Please choose a longer segment"
                if window_seconds
                else "Please upload a longer clip recorded at a suitable frame rate"
            )
            raise VideoValidationError(
                f"The video contains too few usable frames for acoustic "
                f"reconstruction (found {frames_read}, need at least {min_frames}). "
                f"{hint}."
            )

        return VideoInfo(
            filename=p.name,
            path=str(p),
            width=width,
            height=height,
            fps=round(fps, 4),
            container_fps=round(container_fps, 4),
            fps_overridden=fps_overridden,
            frame_count_metadata=meta_count,
            frames_read=frames_read,
            duration_seconds=round(duration, 3),
            fourcc=fourcc,
            segment_start_seconds=round(start_seconds, 3),
            source_duration_seconds=round(source_duration or duration, 3),
        )
    finally:
        cap.release()


def iter_gray_norm_frames(
    path: str | Path,
    *,
    downsample: float,
    max_frames: int,
    start_seconds: float = 0.0,
    fps_override: Optional[float] = None,
) -> Iterator[np.ndarray]:
    """Yield pre-processed frames ready for the steerable pyramid.

    Each yielded array is:

    * spatially down-sampled by ``downsample`` (skipped when >= 1.0, and
      automatically relaxed if it would shrink a side below 24 px),
    * converted to single-channel grayscale,
    * min-max normalised to ``[0, 1]`` as ``float64``.

    Frames that fail to decode are silently skipped (corrupt / truncated),
    exactly the robustness the reference code lacks.  The caller is
    responsible for counting what it receives.

    ``start_seconds`` seeks into the file first (local-file segment mode).
    """
    cap = cv.VideoCapture(str(Path(path)))
    if not cap.isOpened():
        raise VideoValidationError("The video could not be re-opened for processing.")

    # Relax an over-aggressive downsample factor so the pyramid still has
    # something to work with on small inputs.
    eff_downsample = float(downsample)
    w = cap.get(cv.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv.CAP_PROP_FRAME_HEIGHT)
    if 0 < eff_downsample < 1.0 and w > 0 and h > 0:
        min_side = min(w, h) * eff_downsample
        if min_side < 24:
            eff_downsample = min(1.0, 24.0 / min(w, h))

    if start_seconds and start_seconds > 0:
        if fps_override and fps_override > 0:
            fps = float(fps_override)
        else:
            raw = cap.get(cv.CAP_PROP_FPS)
            fps = raw if (raw and raw > 0) else 30.0
        _seek_to_frame(cap, int(round(float(start_seconds) * fps)))

    emitted = 0
    try:
        while emitted < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None or frame.size == 0:
                break  # end of stream or unrecoverable read
            try:
                if 0 < eff_downsample < 1.0:
                    frame = cv.resize(frame, (0, 0), fx=eff_downsample, fy=eff_downsample,
                                      interpolation=cv.INTER_AREA)
                if frame.ndim == 3:
                    gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
                else:
                    gray = frame
                norm = cv.normalize(gray.astype("float64"), None, 0.0, 1.0, cv.NORM_MINMAX)
            except cv.error:
                # A single bad frame should not kill the whole reconstruction.
                continue
            emitted += 1
            yield norm
    finally:
        cap.release()


def effective_downsample(path: str | Path, downsample: float) -> float:
    """Return the down-sample factor that :func:`iter_gray_norm_frames` will
    actually use for this file (after the small-input safety relaxation).
    Handy for reporting in logs / the API response."""
    cap = cv.VideoCapture(str(Path(path)))
    try:
        w = cap.get(cv.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv.CAP_PROP_FRAME_HEIGHT)
    finally:
        cap.release()
    eff = float(downsample)
    if 0 < eff < 1.0 and w > 0 and h > 0 and min(w, h) * eff < 24:
        eff = min(1.0, 24.0 / min(w, h))
    return round(eff, 4)

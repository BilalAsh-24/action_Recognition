"""
Phase-based Visual Microphone core.

ATTRIBUTION
-----------
The algorithm implemented here is the "Visual Microphone" of

    A. Davis, M. Rubinstein, N. Wadhwa, G. J. Mysore, F. Durand, W. T. Freeman,
    "The Visual Microphone: Passive Recovery of Sound from Video",
    ACM Transactions on Graphics (SIGGRAPH) 33(4), 2014.

This file is an **adaptation** of the open-source Python re-implementation

    visual-mic-master  --  https://github.com/... (bundled as visual-mic-master.zip)
    visualmic/sound_from_video.py
    Copyright (c) 2020 Antonio Musolino and Davide Sforza -- MIT License

Reused (logic preserved, faithful to formulas (2)-(5) of the paper):
    * ``align_vectors``           -- cross-correlation alignment, paper eq. (4)
    * per-frame local phase / amplitude extraction via a complex steerable
      pyramid (pyrtools ``SteerablePyramidFreq``)
    * amplitude-weighted phase differencing, paper eq. (2)-(3)
    * per-band signal = amplitude-weighted mean of the weighted phase, eq. (3)
    * band alignment + summation, eq. (4)-(5)

Changed / fixed relative to the reference:
    * Output length is the number of frames **actually decoded**, never
      ``cv.CAP_PROP_FRAME_COUNT`` (see video_reader.py for the rationale).
    * Works on an iterator of pre-processed frames instead of driving the
      ``cv.VideoCapture`` itself -- decoding / down-sampling / graying /
      normalising now lives in ``video_reader.iter_gray_norm_frames`` and is
      individually fault-tolerant.
    * Guards against: zero frames, a degenerate first frame, ``NaN`` band
      values (silent regions -> divide-by-zero in the reference), and band
      signals of unequal length before summation.
    * The Butterworth high-pass is applied in ``signal_processing.py`` so the
      core returns the *raw* recovered motion signal; callers choose the
      filtering / scaling policy.
    * ``pyrtools`` import failure raises a typed, user-facing error instead of
      an ``ImportError`` traceback.
    * Optional ``progress_cb`` for UI status reporting.

Everything in ``signal_processing.py`` beyond this file is likewise adapted
from ``visualmic/sound_spectral_subtraction.py`` (same authors / licence).
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

try:  # pyrtools is pure-Python but still an optional heavy dependency.
    import pyrtools as pt

    _PYRTOOLS_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - only hit when dep is missing
    pt = None  # type: ignore[assignment]
    _PYRTOOLS_IMPORT_ERROR = str(exc)


class PyrtoolsUnavailableError(RuntimeError):
    """Raised when the complex steerable pyramid backend cannot be imported."""


class ReconstructionError(RuntimeError):
    """Raised when the recovered signal cannot be formed (user-facing message)."""


ProgressCb = Callable[[int, Optional[int]], None]


def pyrtools_available() -> bool:
    return pt is not None


def pyrtools_import_error() -> Optional[str]:
    return _PYRTOOLS_IMPORT_ERROR


# --------------------------------------------------------------------------- #
# Reused verbatim (logic) from visual-mic-master -- paper eq. (4)
# --------------------------------------------------------------------------- #
def align_vectors(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """Circularly shift ``v1`` so it best lines up with ``v2``.

    Adapted from ``visualmic/sound_from_video.py::align_vectors``
    (Musolino & Sforza, MIT).  Implements the alignment of paper eq. (4):
    the lag that maximises the cross-correlation is found via a convolution
    with the time-reversed reference, then applied with ``np.roll``.

    A ``NaN`` guard is the only addition.
    """
    v1 = np.nan_to_num(np.asarray(v1, dtype=np.float64))
    v2 = np.nan_to_num(np.asarray(v2, dtype=np.float64))
    if v1.size == 0 or v2.size == 0:
        return v1

    acorb = np.convolve(v1, np.flip(v2))
    maxind = int(np.argmax(acorb))
    shift = v2.size - maxind
    return np.roll(v1, shift)


# --------------------------------------------------------------------------- #
# Pyramid helpers
# --------------------------------------------------------------------------- #
def _build_pyramid(frame: np.ndarray, nscale: int, norientation: int) -> Dict[object, np.ndarray]:
    """Complex steerable pyramid coefficients for one normalised frame.

    Mirrors the reference call exactly::

        pt.pyramids.SteerablePyramidFreq(frame, nscale, norientation - 1,
                                         is_complex=True).pyr_coeffs
    """
    if pt is None:  # pragma: no cover
        raise PyrtoolsUnavailableError(
            "pyrtools is not installed, so complex steerable pyramids cannot be "
            "computed. Install it with `pip install pyrtools` and try again."
        )
    pyr = pt.pyramids.SteerablePyramidFreq(
        frame, height=nscale, order=norientation - 1, is_complex=True
    )
    return pyr.pyr_coeffs


def _reference_band(bands: Iterable[object]) -> object:
    """Pick the band used as the alignment reference (paper eq. (4)).

    The reference code always uses key ``(0, 0)``.  We keep that when present
    but fall back gracefully for unusual pyramid configurations.
    """
    band_list = list(bands)
    if (0, 0) in band_list:
        return (0, 0)
    for b in band_list:
        if isinstance(b, tuple):
            return b
    return band_list[0]


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def sound_from_frames(
    frames: Iterable[np.ndarray],
    *,
    nscale: int,
    norientation: int,
    expected_frames: Optional[int] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> np.ndarray:
    """Recover a raw motion / acoustic signal from an iterable of frames.

    Parameters
    ----------
    frames:
        Iterable of grayscale ``float`` images normalised to ``[0, 1]``
        (see :func:`video_reader.iter_gray_norm_frames`).  The **first** item
        is used as the phase reference, matching the reference implementation.
    nscale, norientation:
        Steerable-pyramid scales / orientations.
    expected_frames:
        Optional hint (real decoded count) used only for progress reporting.
    progress_cb:
        Called as ``progress_cb(frames_done, expected_frames)`` after each
        frame so the API can surface an indeterminate / fractional progress.

    Returns
    -------
    np.ndarray
        1-D ``float64`` signal, one sample per processed frame, **before**
        high-pass filtering and scaling.  Length == number of frames actually
        consumed from ``frames``.
    """
    if not pyrtools_available():
        raise PyrtoolsUnavailableError(
            "pyrtools is not available: "
            f"{_PYRTOOLS_IMPORT_ERROR or 'unknown import error'}"
        )

    frame_iter = iter(frames)
    try:
        first_frame = next(frame_iter)
    except StopIteration:
        raise ReconstructionError("No frames were available for processing.")

    if first_frame is None or np.asarray(first_frame).ndim != 2:
        raise ReconstructionError("The first video frame is unusable.")
    if not np.isfinite(first_frame).all():
        first_frame = np.nan_to_num(first_frame)

    first_coeffs = _build_pyramid(first_frame, nscale, norientation)
    band_keys: List[object] = list(first_coeffs.keys())
    if not band_keys:
        raise ReconstructionError(
            "The steerable pyramid produced no sub-bands. Try increasing "
            "'scales' or reducing the down-sample factor."
        )
    ref_band = _reference_band(band_keys)

    # One growing list of scalar values per band (paper eq. (3)).
    signals: Dict[object, List[float]] = {b: [] for b in band_keys}

    def _accumulate(coeffs: Dict[object, np.ndarray]) -> None:
        for band in band_keys:
            cur = coeffs[band]
            ref = first_coeffs[band]

            amp = np.abs(cur)                                   # amplitude, eq. (3)
            # amplitude-weighted phase difference vs. the first frame, eq. (2)
            dphase = (
                np.mod(math.pi + np.angle(cur) - np.angle(ref), 2 * math.pi)
                - math.pi
            )
            weighted = dphase * amp * amp                       # eq. (3) numerator
            total_amp = float(np.sum(amp))
            if total_amp <= 0.0 or not np.isfinite(total_amp):
                signals[band].append(0.0)                       # silent region guard
            else:
                signals[band].append(float(np.mean(weighted)) / total_amp)

    # Frame 0 (its phase difference against itself is ~0, exactly as in the
    # reference which also processes the first frame inside the loop).
    _accumulate(first_coeffs)
    n_done = 1
    if progress_cb:
        progress_cb(n_done, expected_frames)

    for frame in frame_iter:
        if frame is None:
            continue
        arr = np.asarray(frame)
        if arr.ndim != 2:
            continue
        if not np.isfinite(arr).all():
            arr = np.nan_to_num(arr)
        coeffs = _build_pyramid(arr, nscale, norientation)
        _accumulate(coeffs)
        n_done += 1
        if progress_cb:
            progress_cb(n_done, expected_frames)

    n_frames = len(signals[ref_band])
    if n_frames < 2:
        raise ReconstructionError(
            "Not enough frames were successfully processed to reconstruct a signal."
        )

    # Align every band to the reference band and sum -- paper eq. (4)-(5).
    reference_signal = np.asarray(signals[ref_band], dtype=np.float64)
    sound = np.zeros(n_frames, dtype=np.float64)
    for band, values in signals.items():
        sig = np.asarray(values, dtype=np.float64)
        if sig.size != n_frames:  # defensive: keep everything the same length
            sig = np.resize(sig, n_frames)
        aligned = align_vectors(sig, reference_signal)
        if aligned.size != n_frames:
            aligned = np.resize(aligned, n_frames)
        sound += aligned

    sound = np.nan_to_num(sound, nan=0.0, posinf=0.0, neginf=0.0)
    return sound

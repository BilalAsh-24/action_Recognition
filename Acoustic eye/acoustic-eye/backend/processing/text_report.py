"""
Turn the recovered audio into **text**.

Two independent things live here:

1. :func:`analyze_signal` -- a always-available, never-faked *textual description*
   of the reconstructed signal: duration, dominant frequency, loudness, where the
   energy bursts are, how energy splits across frequency bands, plus a plain
   English summary paragraph.  This is the honest "audio in words": at ordinary
   camera frame rates the recoverable band is only a few tens of Hz, so there is
   no intelligible speech to transcribe -- but the signal still *says* something,
   and this reports exactly what.

2. :func:`transcribe` -- optional speech-to-text via ``faster-whisper`` (offline,
   CPU).  Only useful when the source video frame rate is high enough to carry
   speech frequencies (thousands of fps); otherwise it honestly returns
   "no intelligible speech".  Disabled unless the package is installed *and*
   ``enable_transcription`` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy import signal as _sig

try:  # optional, heavy
    from faster_whisper import WhisperModel  # type: ignore

    _FASTER_WHISPER = True
    _FW_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - only when dep missing
    WhisperModel = None  # type: ignore
    _FASTER_WHISPER = False
    _FW_ERROR = str(exc)

_MODEL_CACHE: Dict[str, "WhisperModel"] = {}


def transcription_available() -> bool:
    return _FASTER_WHISPER


def transcription_import_error() -> Optional[str]:
    return _FW_ERROR


# --------------------------------------------------------------------------- #
# 1. Signal -> text description  (always available)
# --------------------------------------------------------------------------- #
def _envelope(sound: np.ndarray, sample_rate: int, win_s: float = 0.05) -> np.ndarray:
    """Short-time RMS envelope."""
    win = max(4, int(round(win_s * sample_rate)))
    if win >= sound.size:
        win = max(2, sound.size // 4)
    kernel = np.ones(win, dtype=np.float64) / win
    power = np.convolve(sound.astype(np.float64) ** 2, kernel, mode="same")
    return np.sqrt(np.maximum(power, 0.0))


def _find_bursts(sound: np.ndarray, sample_rate: int) -> List[Dict[str, float]]:
    """Detect contiguous stretches where the envelope is clearly above the floor."""
    env = _envelope(sound, sample_rate)
    if env.size == 0 or not np.any(env):
        return []
    norm = env / (env.max() + 1e-12)
    thr = max(0.25, float(np.median(norm) + 1.5 * np.std(norm)))
    active = norm > thr

    bursts: List[Dict[str, float]] = []
    i = 0
    n = active.size
    min_len = max(2, int(0.03 * sample_rate))
    gap = max(1, int(0.05 * sample_rate))
    while i < n:
        if not active[i]:
            i += 1
            continue
        j = i
        while j < n and (active[j] or (j + gap < n and np.any(active[j:j + gap]))):
            j += 1
        if j - i >= min_len:
            seg = norm[i:j]
            bursts.append(
                {
                    "start_s": round(i / sample_rate, 3),
                    "end_s": round(j / sample_rate, 3),
                    "duration_s": round((j - i) / sample_rate, 3),
                    "relative_level": round(float(seg.max()), 3),
                }
            )
        i = j + 1
    return bursts[:12]


def analyze_signal(sound: np.ndarray, sample_rate: int) -> Dict[str, object]:
    """Return a dict describing the reconstructed signal, plus a summary string."""
    sound = np.nan_to_num(np.asarray(sound, dtype=np.float64))
    n = sound.size
    sr = int(sample_rate) if sample_rate and sample_rate > 0 else 1
    nyquist = sr / 2.0
    duration = n / sr if sr else 0.0

    rms = float(np.sqrt(np.mean(sound ** 2))) if n else 0.0
    peak = float(np.max(np.abs(sound))) if n else 0.0
    crest_db = float(20.0 * np.log10(peak / rms)) if (rms > 1e-9 and peak > 0) else 0.0

    dominant_hz = 0.0
    centroid_hz = 0.0
    band_energy: Dict[str, float] = {}
    if n >= 8:
        nperseg = int(min(256, max(16, n)))
        freqs, psd = _sig.welch(sound, fs=sr, nperseg=nperseg)
        if freqs.size > 1:
            mag = np.asarray(psd, dtype=np.float64)
            ac = mag.copy()
            ac[0] = 0.0  # ignore DC
            if np.any(ac):
                dominant_hz = float(freqs[int(np.argmax(ac))])
                centroid_hz = float(np.sum(freqs * ac) / (np.sum(ac) + 1e-20))

            edges = [0.0, 2.0, 5.0, 10.0, 20.0, max(20.0, nyquist)]
            edges = sorted(set(e for e in edges if e <= nyquist + 1e-9)) or [0.0, nyquist]
            if edges[-1] < nyquist:
                edges.append(nyquist)
            total = float(np.sum(ac)) + 1e-20
            for lo, hi in zip(edges[:-1], edges[1:]):
                sel = (freqs >= lo) & (freqs < hi)
                pct = round(100.0 * float(np.sum(ac[sel])) / total, 1)
                band_energy[f"{lo:g}-{hi:g} Hz"] = pct

    bursts = _find_bursts(sound, sr)

    # ---- summary paragraph ------------------------------------------------ #
    parts: List[str] = []
    parts.append(
        f"The reconstructed signal is {duration:.2f} s long at a "
        f"{sr} Hz sample rate (equal to the video frame rate), so it can only "
        f"represent frequencies up to about {nyquist:.1f} Hz (Nyquist limit)."
    )
    if peak < 1e-4:
        parts.append("It is essentially silent — no usable vibration was recovered.")
    else:
        parts.append(
            f"Loudness: RMS {rms:.3f}, peak {peak:.3f} (crest factor "
            f"{crest_db:.1f} dB) on the normalised [-1, 1] scale."
        )
        if dominant_hz > 0:
            parts.append(
                f"Most of the energy sits around {dominant_hz:.2f} Hz "
                f"(spectral centroid {centroid_hz:.2f} Hz)."
            )
        if band_energy:
            top = max(band_energy.items(), key=lambda kv: kv[1])
            parts.append(f"The strongest frequency band is {top[0]} with {top[1]:.0f}% of the energy.")
        if bursts:
            times = ", ".join(f"{b['start_s']:.2f}-{b['end_s']:.2f}s" for b in bursts[:6])
            more = "" if len(bursts) <= 6 else f" (+{len(bursts) - 6} more)"
            parts.append(f"{len(bursts)} louder burst(s) were detected at: {times}{more}.")
        else:
            parts.append("No distinct louder bursts stand out above the background.")
    parts.append(
        "At this frame rate the result is a low-frequency vibration trace that "
        "correlates with the sound in the room, not intelligible speech or music."
    )
    summary = " ".join(parts)

    return {
        "duration_seconds": round(duration, 3),
        "sample_rate": sr,
        "nyquist_hz": round(nyquist, 3),
        "samples": n,
        "rms": round(rms, 5),
        "peak": round(peak, 5),
        "crest_factor_db": round(crest_db, 2),
        "dominant_frequency_hz": round(dominant_hz, 3),
        "spectral_centroid_hz": round(centroid_hz, 3),
        "band_energy_percent": band_energy,
        "bursts": bursts,
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# 2. Speech-to-text  (optional)
# --------------------------------------------------------------------------- #
def transcribe(
    wav_path: str | Path,
    *,
    model_size: str = "tiny",
    language: Optional[str] = None,
) -> Dict[str, object]:
    """Best-effort offline transcription of a WAV file.

    Never raises: returns ``available: False`` with a ``note`` explaining why
    when the feature is off or the run fails.
    """
    if not _FASTER_WHISPER:
        return {
            "available": False,
            "text": "",
            "segments": [],
            "note": (
                "Speech-to-text is not installed. Enable it with "
                "`pip install faster-whisper` and turn on 'enable_transcription', "
                "then restart the server. Note: at ordinary camera frame rates the "
                "recovered audio has no speech-band content to transcribe."
            ),
        }
    try:
        model = _MODEL_CACHE.get(model_size)
        if model is None:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _MODEL_CACHE[model_size] = model
        segments, info = model.transcribe(str(wav_path), language=language, vad_filter=True)
        segs = [
            {"start": round(float(s.start), 2), "end": round(float(s.end), 2),
             "text": s.text.strip()}
            for s in segments
        ]
        text = " ".join(s["text"] for s in segs).strip()
        return {
            "available": True,
            "text": text,
            "segments": segs,
            "language": getattr(info, "language", None),
            "language_probability": round(float(getattr(info, "language_probability", 0.0)), 3),
            "model_size": model_size,
            "note": "" if text
            else "No intelligible speech was detected in the recovered audio "
                 "(expected at normal frame rates).",
        }
    except Exception as exc:  # noqa: BLE001 - transcription is strictly best-effort
        return {
            "available": False,
            "text": "",
            "segments": [],
            "note": f"Transcription could not run: {type(exc).__name__}: {exc}",
        }

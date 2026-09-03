"""
WAV writing and visualisation rendering.

* WAV output uses :mod:`soundfile` (libsndfile) at 16-bit PCM.
* Waveform / spectrogram PNGs are rendered server-side with Matplotlib's
  non-interactive ``Agg`` backend so they work headless on Windows.

Every pixel of every visualisation is derived from the *actual* reconstructed
signal that gets written to the WAV -- there is no synthetic / placeholder art.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import matplotlib

matplotlib.use("Agg")  # must precede pyplot import; headless rendering
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy import signal as _sig  # noqa: E402

from .signal_processing import to_int16


def write_wav(path: str | Path, sound: np.ndarray, sample_rate: int) -> Path:
    """Write ``sound`` (float in [-1, 1]) as a 16-bit PCM WAV. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = to_int16(sound)
    if pcm.size == 0:
        raise ValueError("Refusing to write an empty WAV file.")
    sf.write(str(path), pcm, int(sample_rate), subtype="PCM_16")
    if not path.is_file() or path.stat().st_size == 0:
        raise IOError("WAV file was not created on disk.")
    return path


def wav_info(path: str | Path) -> dict:
    """Return basic properties of a WAV file (used by the API + tests)."""
    info = sf.info(str(path))
    return {
        "samplerate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration": round(info.duration, 4),
        "subtype": info.subtype,
        "format": info.format,
    }


def _safe_nfft(n: int) -> int:
    """Choose an FFT window that fits a short signal (power of two, <= n)."""
    if n <= 0:
        return 256
    nfft = 256
    while nfft * 2 <= n:
        nfft *= 2
    return max(32, min(nfft, 1024))


def render_waveform(path: str | Path, sound: np.ndarray, sample_rate: int) -> Path:
    """Render a time-domain waveform PNG of the reconstructed signal."""
    path = Path(path)
    sound = np.asarray(sound, dtype=np.float64)
    n = sound.size
    t = np.arange(n) / float(sample_rate) if sample_rate > 0 else np.arange(n)

    fig, ax = plt.subplots(figsize=(10, 3.2), dpi=110)
    ax.plot(t, sound, linewidth=0.7, color="#2f7ed8")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title("Reconstructed signal — waveform")
    ax.set_xlim(t[0] if n else 0, t[-1] if n else 1)
    ax.set_ylim(-1.05, 1.05)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, format="png")
    plt.close(fig)
    return path


def render_spectrogram(path: str | Path, sound: np.ndarray, sample_rate: int) -> Path:
    """Render a spectrogram PNG of the reconstructed signal.

    Mirrors the reference ``plot_specgram`` (``plt.specgram``, ``Fs=sr``,
    ``jet`` colormap) but with an FFT window sized safely for short signals.
    """
    path = Path(path)
    sound = np.asarray(sound, dtype=np.float64)
    nfft = _safe_nfft(sound.size)
    noverlap = nfft // 2

    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=110)
    if sound.size >= nfft and np.any(sound):
        spectrum, freqs, t_bins, im = ax.specgram(
            sound,
            NFFT=nfft,
            Fs=float(sample_rate) if sample_rate > 0 else 2.0,
            noverlap=noverlap,
            cmap=plt.get_cmap("magma"),
        )
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Power/Frequency (dB)")
    else:
        ax.text(0.5, 0.5, "Signal too short / silent for a spectrogram",
                ha="center", va="center", transform=ax.transAxes)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title("Reconstructed signal — spectrogram")
    fig.tight_layout()
    fig.savefig(path, format="png")
    plt.close(fig)
    return path


def render_all(
    out_dir: str | Path,
    stem: str,
    sound: np.ndarray,
    sample_rate: int,
) -> Tuple[Path, Path]:
    """Render both PNGs, returning ``(waveform_path, spectrogram_path)``."""
    out_dir = Path(out_dir)
    wf = render_waveform(out_dir / f"{stem}_waveform.png", sound, sample_rate)
    sp = render_spectrogram(out_dir / f"{stem}_spectrogram.png", sound, sample_rate)
    return wf, sp

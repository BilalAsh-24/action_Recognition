"""
Post-processing of the recovered motion signal.

Adapted from ``visual-mic-master/visualmic/sound_spectral_subtraction.py``
and the tail of ``sound_from_video.py``
(Copyright (c) 2020 Antonio Musolino and Davide Sforza, MIT License).

Reused:
    * ``get_scaled_sound``  -- centre + scale to [-1, 1]
    * the Butterworth high-pass (``scipy.signal.butter(..., output='sos')`` +
      ``sosfilt``) that the reference applies at the end of ``sound_from_video``
    * spectral-subtraction denoising (``get_soud_spec_sub``), itself adapted by
      the reference authors from Abe Davis' original MATLAB work.

Fixed:
    * ``get_scaled_sound`` divided by ``max - min`` with no guard -> a silent
      / constant signal produced ``inf``/``nan``.  Now returns zeros.
    * The reference spectral subtraction reconstructed the complex STFT as
      ``mags * (1j * angles)`` -- that is not a phasor and corrupts the phase.
      The correct reconstruction ``mags * exp(1j * angles)`` is used here.
    * ``istft`` output length is trimmed / padded back to the input length.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as _sig


def get_scaled_sound(sound: np.ndarray) -> np.ndarray:
    """Centre and scale ``sound`` into ``[-1, 1]``.

    Faithful to the reference ``get_scaled_sound`` but safe for degenerate
    input (all-equal samples -> returns zeros instead of ``nan``).
    """
    sound = np.asarray(sound, dtype=np.float64)
    if sound.size == 0:
        return sound
    sound = np.nan_to_num(sound, nan=0.0, posinf=0.0, neginf=0.0)

    maxv = float(np.max(sound))
    minv = float(np.min(sound))
    rangev = maxv - minv
    if rangev <= 1e-12:
        return np.zeros_like(sound)

    scaled = 2.0 * sound / rangev
    offset = float(np.max(scaled)) - 1.0
    return scaled - offset


def highpass_filter(
    sound: np.ndarray,
    *,
    cutoff_normalized: float,
    order: int = 3,
) -> np.ndarray:
    """Zero-out slow drift / DC with a Butterworth high-pass.

    ``cutoff_normalized`` is a fraction of the Nyquist frequency (0..1), matching
    the reference call ``signal.butter(3, 0.05, btype='highpass', output='sos')``.
    """
    sound = np.asarray(sound, dtype=np.float64)
    if sound.size < 12:  # too short to filter meaningfully
        return sound
    wn = float(np.clip(cutoff_normalized, 1e-4, 0.95))
    sos = _sig.butter(int(max(1, order)), wn, btype="highpass", output="sos")
    filtered = _sig.sosfilt(sos, sound)
    return np.nan_to_num(filtered, nan=0.0, posinf=0.0, neginf=0.0)


def notch_mains(
    sound: np.ndarray,
    sample_rate: float,
    base_hz: float = 60.0,
    quality: float = 35.0,
) -> np.ndarray:
    """Remove ``base_hz`` and every harmonic of it with narrow IIR notches.

    High-speed photography needs very bright continuous light, and mains-powered
    lamps pulse at twice the supply frequency.  That flicker is a genuine
    brightness oscillation, so the Visual Microphone recovers it faithfully --
    it lands in the output as an extremely strong 100/120 Hz tone plus
    harmonics that can sit 100s of times above the acoustic signal and mask it
    completely.  Notching the comb is what makes the recording audible.

    Uses zero-phase ``filtfilt`` so the notches introduce no group delay that
    would smear transients.  A no-op when ``base_hz`` is falsy.
    """
    sound = np.asarray(sound, dtype=np.float64)
    if not base_hz or base_hz <= 0 or sound.size < 32 or sample_rate <= 0:
        return sound

    nyq = sample_rate / 2.0
    out = sound
    n = 1
    while base_hz * n < nyq - (base_hz / 2.0):
        f0 = base_hz * n
        try:
            b, a = _sig.iirnotch(f0, Q=float(quality), fs=float(sample_rate))
            out = _sig.filtfilt(b, a, out)
        except ValueError:
            break
        n += 1
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def lowpass_filter(
    sound: np.ndarray, sample_rate: float, cutoff_hz: float, order: int = 4
) -> np.ndarray:
    """Zero-phase Butterworth low-pass, in Hz rather than normalised units.

    The per-frame phase estimate is noisy, and that noise is broadband: on a
    high-speed capture most of the output energy can sit above 2 kHz as hiss
    while the acoustic content is far lower.  A no-op when the cutoff is absent
    or already at/above Nyquist.
    """
    sound = np.asarray(sound, dtype=np.float64)
    nyq = sample_rate / 2.0
    if not cutoff_hz or cutoff_hz <= 0 or cutoff_hz >= nyq or sound.size < 32:
        return sound
    sos = _sig.butter(order, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    return np.nan_to_num(_sig.sosfiltfilt(sos, sound), nan=0.0, posinf=0.0, neginf=0.0)


def spectral_subtraction(sound: np.ndarray, quantile: float = 0.5) -> np.ndarray:
    """Reduce stationary background noise via spectral subtraction.

    Adapted from ``get_soud_spec_sub`` (Musolino & Sforza / Abe Davis).  The
    per-frequency noise floor is the ``quantile`` of the power spectrogram over
    time; it is subtracted from every frame, negatives clipped to zero, and the
    original phase re-applied with a correct complex exponential.
    """
    sound = np.asarray(sound, dtype=np.float64)
    n = sound.size
    if n < 64:
        return get_scaled_sound(sound)

    nperseg = int(min(256, max(16, n // 4)))
    freqs, times, zxx = _sig.stft(sound, nperseg=nperseg)
    mags = np.abs(zxx)
    angles = np.angle(zxx)

    power = mags ** 2
    noise_floor = np.quantile(power, float(np.clip(quantile, 0.05, 0.95)), axis=-1, keepdims=True)
    cleaned_power = np.maximum(power - noise_floor, 0.0)
    cleaned_mags = np.sqrt(cleaned_power)

    new_zxx = cleaned_mags * np.exp(1j * angles)
    _, rec = _sig.istft(new_zxx)

    rec = np.asarray(rec, dtype=np.float64)
    if rec.size >= n:
        rec = rec[:n]
    else:
        rec = np.pad(rec, (0, n - rec.size))
    return get_scaled_sound(rec)


def to_int16(sound: np.ndarray) -> np.ndarray:
    """Convert a ``[-1, 1]`` float signal to 16-bit PCM for broad browser
    playback compatibility (64-bit float WAV, as written by the reference via
    ``scipy.io.wavfile``, is not reliably playable in browsers)."""
    sound = np.asarray(sound, dtype=np.float64)
    sound = np.clip(np.nan_to_num(sound), -1.0, 1.0)
    return (sound * 32767.0).astype(np.int16)

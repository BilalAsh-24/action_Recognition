"""Tests for backend.processing.text_report (signal -> text description)."""

from __future__ import annotations

import numpy as np

from backend.processing.text_report import analyze_signal, transcribe


def _tone(freq: float, sr: int, seconds: float, noise: float = 0.0) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    x = np.sin(2 * np.pi * freq * t)
    if noise:
        x = x + noise * np.random.default_rng(0).standard_normal(x.size)
    return (x / np.max(np.abs(x))).astype(np.float64)


def test_analyze_reports_dominant_frequency():
    sr = 200
    x = _tone(12.0, sr, 3.0)
    a = analyze_signal(x, sr)
    assert a["sample_rate"] == sr
    assert a["nyquist_hz"] == sr / 2
    # welch resolution is coarse for short signals; just needs to be in the ballpark.
    assert 6.0 <= a["dominant_frequency_hz"] <= 20.0
    assert isinstance(a["summary"], str) and len(a["summary"]) > 40
    assert isinstance(a["band_energy_percent"], dict) and a["band_energy_percent"]


def test_analyze_silent_signal_is_safe():
    a = analyze_signal(np.zeros(300), 30)
    assert a["rms"] == 0.0 and a["peak"] == 0.0
    assert "silent" in a["summary"].lower()
    assert a["bursts"] == []


def test_analyze_detects_bursts():
    sr = 200
    x = np.zeros(sr * 3, dtype=np.float64)
    x[sr : sr + sr // 2] = _tone(15.0, sr, 0.5)          # burst 1
    x[2 * sr : 2 * sr + sr // 4] = _tone(15.0, sr, 0.25)  # burst 2
    a = analyze_signal(x, sr)
    assert len(a["bursts"]) >= 1
    for b in a["bursts"]:
        assert 0.0 <= b["start_s"] < b["end_s"] <= 3.01


def test_analyze_handles_tiny_input():
    a = analyze_signal(np.array([0.1, -0.2, 0.3, -0.1, 0.0]), 24)
    assert a["samples"] == 5
    assert np.isfinite(a["rms"]) and np.isfinite(a["peak"])
    assert isinstance(a["summary"], str)


def test_transcribe_is_graceful_without_dependency(tmp_path):
    # Whether or not faster-whisper is installed, this must not raise and must
    # return the documented shape.
    import soundfile as sf

    wav = tmp_path / "t.wav"
    sf.write(str(wav), (_tone(10.0, 48000, 0.5) * 20000).astype(np.int16), 48000)
    out = transcribe(wav)
    assert set(["available", "text", "segments", "note"]).issubset(out.keys())
    assert isinstance(out["available"], bool)

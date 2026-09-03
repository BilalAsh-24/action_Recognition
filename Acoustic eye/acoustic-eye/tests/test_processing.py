"""
Tests for the signal-processing helpers and the end-to-end pipeline.

The full pipeline test is marked ``slow`` and skipped automatically when
pyrtools is not installed, so ``pytest`` still passes on a partial install.
Run everything with:  ``pytest``  ;  skip the slow one with ``pytest -m "not slow"``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.config import ProcessingConfig
from backend.processing.audio_writer import render_all, wav_info, write_wav
from backend.processing.signal_processing import (
    get_scaled_sound,
    highpass_filter,
    spectral_subtraction,
    to_int16,
)


# --------------------------- signal_processing ---------------------------- #
def test_get_scaled_sound_range():
    x = np.linspace(-3.0, 7.0, 500)
    y = get_scaled_sound(x)
    assert pytest.approx(float(y.max()), abs=1e-6) == 1.0
    assert float(y.min()) >= -1.0 - 1e-6


def test_get_scaled_sound_constant_input_is_safe():
    y = get_scaled_sound(np.full(100, 0.42))
    assert np.all(y == 0.0)
    assert np.isfinite(y).all()


def test_highpass_removes_dc():
    n = 2000
    t = np.arange(n)
    sig = 5.0 + np.sin(2 * np.pi * t / 20.0)  # DC offset + oscillation
    out = highpass_filter(sig, cutoff_normalized=0.05, order=3)
    assert abs(float(np.mean(out))) < 0.5
    assert np.isfinite(out).all()


def test_spectral_subtraction_shape_and_finiteness():
    rng = np.random.default_rng(0)
    sig = np.sin(np.linspace(0, 60, 4096)) + 0.3 * rng.standard_normal(4096)
    out = spectral_subtraction(get_scaled_sound(sig), quantile=0.5)
    assert out.ndim == 1 and out.size == 4096
    assert np.isfinite(out).all()
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-6


def test_to_int16_clips():
    x = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    p = to_int16(x)
    assert p.dtype == np.int16
    assert p.min() >= -32767 and p.max() <= 32767


# ------------------------------ audio_writer ----------------------------- #
def test_write_wav_and_info(tmp_path: Path):
    sr = 30
    sound = 0.5 * np.sin(np.linspace(0, 40, 300))
    wav = write_wav(tmp_path / "out.wav", sound, sr)
    assert wav.is_file() and wav.stat().st_size > 44  # bigger than a bare header
    info = wav_info(wav)
    assert info["samplerate"] == sr
    assert info["channels"] == 1
    assert info["frames"] == 300
    assert "PCM_16" in info["subtype"]


def test_render_visualisations_exist(tmp_path: Path):
    sr = 30
    sound = 0.5 * np.sin(np.linspace(0, 80, 600))
    wf, sp = render_all(tmp_path, "job", sound, sr)
    for p in (wf, sp):
        assert p.is_file() and p.stat().st_size > 1000
        assert p.suffix == ".png"


def test_write_wav_empty_rejected(tmp_path: Path):
    with pytest.raises(Exception):
        write_wav(tmp_path / "empty.wav", np.array([]), 30)


# ------------------------------ full pipeline ---------------------------- #
@pytest.mark.slow
def test_pipeline_end_to_end(valid_video: Path, tmp_path: Path, pyrtools_required):
    from backend.processing.pipeline import run_pipeline

    result = run_pipeline(
        job_id="testjob123",
        video_path=valid_video,
        output_dir=tmp_path,
        config=ProcessingConfig(downsample=1.0, scales=1, orientations=2,
                                spectral_subtraction=True),
        min_frames=10,
        max_frames=200,
    )

    # One audio sample per processed frame; sample rate == fps.
    assert result.sample_rate == int(round(result.video["fps"]))
    assert result.frames_processed >= 40
    assert result.nyquist_hz == pytest.approx(result.sample_rate / 2.0)

    wav = tmp_path / result.wav_filename
    assert wav.is_file()
    info = wav_info(wav)
    assert info["samplerate"] == result.sample_rate
    assert info["frames"] == result.frames_processed
    assert (tmp_path / result.waveform_filename).is_file()
    assert (tmp_path / result.spectrogram_filename).is_file()
    if result.denoised_wav_filename:
        assert (tmp_path / result.denoised_wav_filename).is_file()

    # "Audio in text" outputs are always populated.
    assert isinstance(result.analysis, dict) and result.analysis
    assert isinstance(result.analysis_text, str) and len(result.analysis_text) > 40
    assert result.analysis["sample_rate"] == result.sample_rate
    assert isinstance(result.transcript, dict)  # empty unless enabled


@pytest.mark.slow
def test_pipeline_rejects_short_video(short_video: Path, tmp_path: Path, pyrtools_required):
    from backend.processing.pipeline import PipelineError, run_pipeline

    with pytest.raises(PipelineError):
        run_pipeline(
            job_id="shortjob",
            video_path=short_video,
            output_dir=tmp_path,
            config=ProcessingConfig(),
            min_frames=30,
            max_frames=200,
        )

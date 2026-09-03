"""
End-to-end Acoustic Eye pipeline.

    validated video file
          |
    iter_gray_norm_frames   (decode / downsample / gray / normalise, fault tolerant)
          |
    sound_from_frames       (complex steerable pyramid -> phase diff -> per-band
                             amplitude-weighted signal -> align -> sum)   [eq. 2-5]
          |
    highpass_filter         (Butterworth, drift / DC removal)
          |
    get_scaled_sound        (centre + scale to [-1, 1])
          |
    write_wav  +  render_waveform / render_spectrogram
          |
    (optional) spectral_subtraction -> second WAV + visualisations

The output sample rate is the video frame rate: the reference implementation
treats one pyramid measurement per frame as one audio sample, so the highest
representable frequency is fps / 2 (Nyquist).  We do not resample up and we do
not claim frequencies the temporal sampling cannot support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from ..config import ProcessingConfig
from . import audio_writer as aw
from .signal_processing import (
    get_scaled_sound,
    highpass_filter,
    lowpass_filter,
    notch_mains,
    spectral_subtraction,
)
from .text_report import analyze_signal, transcribe
from .video_reader import (
    VideoInfo,
    VideoValidationError,
    effective_downsample,
    iter_gray_norm_frames,
    probe_video,
)
from .visual_microphone import (
    PyrtoolsUnavailableError,
    ReconstructionError,
    pyrtools_available,
    pyrtools_import_error,
    sound_from_frames,
)

# Ordered pipeline stages surfaced to the UI.
STAGES: List[str] = [
    "validate",
    "read_frames",
    "extract_phase",
    "reconstruct",
    "filter",
    "generate_audio",
    "visualize",
    "analyze",
]

StageCb = Callable[[str, str, Optional[float]], None]
"""``stage_cb(stage_key, state, fraction)`` where state is
'running' | 'done' | 'error' and fraction is 0..1 or None (indeterminate)."""


@dataclass
class PipelineResult:
    job_id: str
    video: Dict[str, object]
    sample_rate: int
    nyquist_hz: float
    processing: Dict[str, object]
    frames_processed: int
    wav_filename: str
    waveform_filename: str
    spectrogram_filename: str
    denoised_wav_filename: Optional[str] = None
    denoised_waveform_filename: Optional[str] = None
    denoised_spectrogram_filename: Optional[str] = None
    wav_properties: Dict[str, object] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    #: Text description of the recovered signal (always present).
    analysis: Dict[str, object] = field(default_factory=dict)
    analysis_text: str = ""
    #: Optional speech-to-text result (see processing/text_report.py).
    transcript: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {k: v for k, v in self.__dict__.items()}


class PipelineError(RuntimeError):
    """User-facing pipeline failure."""


def _noop(stage: str, state: str, fraction: Optional[float]) -> None:  # pragma: no cover
    pass


def run_pipeline(
    *,
    job_id: str,
    video_path: str | Path,
    output_dir: str | Path,
    config: ProcessingConfig,
    min_frames: int,
    max_frames: int,
    start_seconds: float = 0.0,
    max_seconds: Optional[float] = None,
    stage_cb: Optional[StageCb] = None,
) -> PipelineResult:
    """Run the full reconstruction. Raises :class:`PipelineError` on failure.

    ``start_seconds`` / ``max_seconds`` restrict processing to a time window of
    the source video (used by the local-file endpoint for very large files).
    """
    cb: StageCb = stage_cb or _noop
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = config.validated()
    notes: List[str] = []
    start_seconds = max(0.0, float(start_seconds or 0.0))

    if not pyrtools_available():
        cb("extract_phase", "error", None)
        raise PipelineError(
            "The complex steerable pyramid backend (pyrtools) is not installed, "
            "so the Visual Microphone algorithm cannot run.\n\n"
            f"Details: {pyrtools_import_error()}\n"
            "Install it with:  pip install pyrtools"
        )

    # --- 1. validate ---------------------------------------------------- #
    cb("validate", "running", None)
    try:
        info: VideoInfo = probe_video(
            video_path,
            min_frames=min_frames,
            max_frames=max_frames,
            start_seconds=start_seconds,
            window_seconds=max_seconds,
            fps_override=cfg.capture_fps,
        )
    except VideoValidationError as exc:
        cb("validate", "error", None)
        raise PipelineError(str(exc)) from exc
    cb("validate", "done", 1.0)

    sample_rate = int(round(info.fps)) if info.fps and info.fps > 0 else 30
    nyquist = sample_rate / 2.0

    # Effective frame ceiling: the smaller of the global cap and the requested
    # time window.
    frame_cap = max_frames
    if max_seconds and max_seconds > 0 and sample_rate > 0:
        frame_cap = min(max_frames, int(round(max_seconds * sample_rate)) + 1)

    if info.fps_overridden:
        notes.append(
            f"Capture frame rate overridden to {info.fps:g} fps "
            f"(the file's own header claimed {info.container_fps:g} fps). "
            f"The output sample rate is {sample_rate} Hz, so frequencies up to "
            f"{nyquist:.0f} Hz can be represented."
        )

    eff_ds = effective_downsample(info.path, cfg.downsample)
    if abs(eff_ds - cfg.downsample) > 1e-6:
        notes.append(
            f"Down-sample factor relaxed from {cfg.downsample} to {eff_ds} "
            f"to keep the pyramid usable on this small frame size."
        )

    if start_seconds > 0:
        notes.append(
            f"Processed a {info.frames_read}-frame segment starting at "
            f"{start_seconds:.1f}s of a ~{info.source_duration_seconds:.0f}s source video."
        )
    if info.frames_read >= frame_cap:
        limit_reason = (
            "the requested segment length"
            if frame_cap < max_frames
            else "MAX_PROCESS_FRAMES"
        )
        notes.append(
            f"Only the first {frame_cap} frames were processed (limited by {limit_reason})."
        )

    # --- 2. read frames + 3. extract phase + 4. reconstruct ----------- #
    # These three are interleaved: sound_from_frames pulls frames lazily.
    cb("read_frames", "running", None)
    cb("extract_phase", "running", 0.0)

    expected = min(info.frames_read, frame_cap)
    frame_source = iter_gray_norm_frames(
        info.path,
        downsample=cfg.downsample,
        max_frames=frame_cap,
        start_seconds=start_seconds,
        fps_override=cfg.capture_fps,
    )

    read_marked_done = False

    def _progress(done: int, total: Optional[int]) -> None:
        nonlocal read_marked_done
        if not read_marked_done and done >= 1:
            cb("read_frames", "done", 1.0)
            read_marked_done = True
        frac = (done / total) if (total and total > 0) else None
        cb("extract_phase", "running", frac)

    try:
        raw_signal = sound_from_frames(
            frame_source,
            nscale=cfg.scales,
            norientation=cfg.orientations,
            expected_frames=expected,
            progress_cb=_progress,
        )
    except PyrtoolsUnavailableError as exc:  # pragma: no cover
        cb("extract_phase", "error", None)
        raise PipelineError(str(exc)) from exc
    except ReconstructionError as exc:
        cb("extract_phase", "error", None)
        raise PipelineError(str(exc)) from exc
    except MemoryError as exc:
        cb("extract_phase", "error", None)
        raise PipelineError(
            "The server ran out of memory while building steerable pyramids. "
            "Try a smaller down-sample factor, fewer scales/orientations, or a "
            "shorter / lower-resolution video."
        ) from exc

    if not read_marked_done:
        cb("read_frames", "done", 1.0)
    frames_processed = int(raw_signal.size)
    if frames_processed < min_frames:
        cb("extract_phase", "error", None)
        raise PipelineError(
            f"Only {frames_processed} frames could be processed successfully "
            f"(need at least {min_frames}). The video may be corrupt or too short."
        )
    cb("extract_phase", "done", 1.0)
    cb("reconstruct", "done", 1.0)  # alignment + sum happen inside sound_from_frames

    # --- 5. filter + normalise --------------------------------------- #
    cb("filter", "running", None)
    try:
        filtered = highpass_filter(
            raw_signal,
            cutoff_normalized=cfg.high_pass_frequency,
            order=cfg.high_pass_order,
        )
        if cfg.mains_notch_hz:
            filtered = notch_mains(filtered, sample_rate, cfg.mains_notch_hz)
            notes.append(
                f"Notched out {cfg.mains_notch_hz:g} Hz and its harmonics "
                f"(mains-powered lighting flicker)."
            )
        if cfg.low_pass_hz:
            filtered = lowpass_filter(filtered, sample_rate, cfg.low_pass_hz)
            notes.append(f"Low-passed at {cfg.low_pass_hz:g} Hz to remove broadband phase noise.")
        scaled = get_scaled_sound(filtered)
    except Exception as exc:  # noqa: BLE001 - convert to friendly message
        cb("filter", "error", None)
        raise PipelineError(f"Signal filtering failed: {exc}") from exc
    if not np.any(np.isfinite(scaled)) or scaled.size == 0:
        cb("filter", "error", None)
        raise PipelineError("The reconstructed signal was empty after filtering.")
    cb("filter", "done", 1.0)

    # --- 6. generate audio ----------------------------------------- #
    cb("generate_audio", "running", None)
    wav_path = output_dir / f"{job_id}.wav"
    try:
        aw.write_wav(wav_path, scaled, sample_rate)
        wav_props = aw.wav_info(wav_path)
    except Exception as exc:  # noqa: BLE001
        cb("generate_audio", "error", None)
        raise PipelineError(f"Could not write the output WAV file: {exc}") from exc

    denoised_wav_name = None
    denoised_wf_name = None
    denoised_sp_name = None
    denoised_scaled: Optional[np.ndarray] = None
    if cfg.spectral_subtraction:
        try:
            denoised_scaled = spectral_subtraction(scaled, cfg.spec_sub_quantile)
            d_path = output_dir / f"{job_id}_denoised.wav"
            aw.write_wav(d_path, denoised_scaled, sample_rate)
            denoised_wav_name = d_path.name
        except Exception as exc:  # noqa: BLE001 - denoising is best-effort
            notes.append(f"Spectral-subtraction denoising skipped: {exc}")
            denoised_scaled = None
    cb("generate_audio", "done", 1.0)

    # --- 7. visualise -------------------------------------------- #
    cb("visualize", "running", None)
    try:
        wf_path, sp_path = aw.render_all(output_dir, job_id, scaled, sample_rate)
        if denoised_scaled is not None:
            d_wf, d_sp = aw.render_all(output_dir, f"{job_id}_denoised", denoised_scaled, sample_rate)
            denoised_wf_name = d_wf.name
            denoised_sp_name = d_sp.name
    except Exception as exc:  # noqa: BLE001
        cb("visualize", "error", None)
        raise PipelineError(f"Could not render visualisations: {exc}") from exc
    cb("visualize", "done", 1.0)

    # --- 8. text: signal analysis (+ optional transcription) ---------- #
    cb("analyze", "running", None)
    analysis_source = denoised_scaled if denoised_scaled is not None else scaled
    try:
        analysis = analyze_signal(analysis_source, sample_rate)
        analysis_text = str(analysis.get("summary", ""))
    except Exception as exc:  # noqa: BLE001 - never fail the job over the text report
        analysis = {}
        analysis_text = ""
        notes.append(f"Signal analysis text could not be generated: {exc}")

    transcript: Dict[str, object] = {}
    if cfg.enable_transcription:
        stt_wav = (output_dir / denoised_wav_name) if denoised_wav_name else wav_path
        transcript = transcribe(stt_wav)
        if transcript.get("note"):
            notes.append(str(transcript["note"]))
    cb("analyze", "done", 1.0)

    return PipelineResult(
        job_id=job_id,
        video=info.as_dict(),
        sample_rate=sample_rate,
        nyquist_hz=round(nyquist, 3),
        processing={**cfg.as_dict(), "effective_downsample": eff_ds},
        frames_processed=frames_processed,
        wav_filename=wav_path.name,
        waveform_filename=wf_path.name,
        spectrogram_filename=sp_path.name,
        denoised_wav_filename=denoised_wav_name,
        denoised_waveform_filename=denoised_wf_name,
        denoised_spectrogram_filename=denoised_sp_name,
        wav_properties=wav_props,
        notes=notes,
        analysis=analysis,
        analysis_text=analysis_text,
        transcript=transcript,
    )

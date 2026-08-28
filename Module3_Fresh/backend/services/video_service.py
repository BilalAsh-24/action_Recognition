"""Video validation and probing. Never decodes or uses the source audio stream."""
from __future__ import annotations
import json, shutil, subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C


class VideoError(Exception):
    """User-facing validation failure."""


@dataclass
class VideoInfo:
    path: str
    duration_s: float
    width: int
    height: int
    fps: str
    frames: int
    codec: str
    has_audio: bool
    size_bytes: int

    def dict(self):
        return asdict(self)


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VideoError("FFmpeg is not installed or not on PATH. Install FFmpeg and retry.")


def probe(path: Path) -> VideoInfo:
    ensure_ffmpeg()
    if not Path(path).is_file():
        raise VideoError("The uploaded file could not be found on the server.")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                        "-of", "json", str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise VideoError("This file could not be read as a video. It may be corrupted "
                         "or in an unsupported format.")
    d = json.loads(r.stdout)
    vs = [s for s in d.get("streams", []) if s.get("codec_type") == "video"]
    aud = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    if not vs:
        raise VideoError("No video stream was found in this file.")
    v = vs[0]
    dur = float(d.get("format", {}).get("duration") or v.get("duration") or 0.0)
    try:
        frames = int(v.get("nb_frames") or 0)
    except (TypeError, ValueError):
        frames = 0
    return VideoInfo(path=str(path), duration_s=round(dur, 3),
                     width=int(v.get("width", 0)), height=int(v.get("height", 0)),
                     fps=v.get("r_frame_rate", "0/0"), frames=frames,
                     codec=v.get("codec_name", "?"), has_audio=bool(aud),
                     size_bytes=Path(path).stat().st_size)


def validate(info: VideoInfo, *, allow_audio: bool = True) -> list[str]:
    """Return non-fatal warnings; raise VideoError for fatal problems."""
    warnings: list[str] = []
    if info.duration_s <= 0.4:
        raise VideoError("This video is too short to analyse. Please upload a clip of at "
                         "least half a second.")
    if info.duration_s > C.MAX_VIDEO_SECONDS:
        raise VideoError(f"This video is {info.duration_s:.1f} s long. The current limit is "
                         f"{C.MAX_VIDEO_SECONDS} s, because action recognition cost grows "
                         f"with duration.")
    if info.size_bytes > C.MAX_UPLOAD_MB * 1024 * 1024:
        raise VideoError(f"This file is larger than the {C.MAX_UPLOAD_MB} MB limit.")
    if Path(info.path).suffix.lower() not in C.ALLOWED_SUFFIX:
        raise VideoError(f"Unsupported format '{Path(info.path).suffix}'. "
                         f"Supported: {', '.join(sorted(C.ALLOWED_SUFFIX))}.")
    if info.has_audio:
        if not allow_audio:
            raise VideoError("This video already contains an audio track. Please upload a "
                            "silent video.")
        warnings.append("This video already contains an audio track. It will be ignored — "
                        "the original audio is never decoded, and the output will contain "
                        "only generated Foley.")
    if info.width < 64 or info.height < 64:
        warnings.append("Very low resolution may reduce action-recognition accuracy.")
    return warnings

"""Final render: mux generated audio with the ORIGINAL video stream (copy, no re-encode)."""
from __future__ import annotations
import json, subprocess
from pathlib import Path


class RenderError(Exception):
    pass


def mux(video: Path, audio: Path, out_mp4: Path, sample_rate: int = 48000) -> dict:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-i", str(video), "-i", str(audio),
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy",                       # picture untouched
           "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
           "-movflags", "+faststart", "-shortest", str(out_mp4)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not out_mp4.is_file():
        raise RenderError(f"Final video rendering failed: {(p.stderr or '').strip()[:300]}")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(out_mp4)], capture_output=True, text=True)
    d = json.loads(probe.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next(s for s in d["streams"] if s["codec_type"] == "audio")
    return {"path": str(out_mp4), "duration_s": float(d["format"]["duration"]),
            "video_codec": v["codec_name"], "audio_codec": a["codec_name"],
            "video_duration_s": float(v.get("duration", 0)),
            "audio_duration_s": float(a.get("duration", 0)),
            "frames": int(v.get("nb_frames", 0)),
            "resolution": f"{v['width']}x{v['height']}",
            "audio_sample_rate": int(a["sample_rate"]),
            "audio_channels": int(a["channels"]),
            "video_stream_copied": True,
            "bytes": out_mp4.stat().st_size}

"""Mux the synchronised audio with the ORIGINAL silent video.

Video is stream-copied (-c:v copy): the original picture is bit-identical in the
output. Only an audio track is added.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C


def main() -> int:
    C.FINAL_MP4.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-i", str(C.SOURCE_VIDEO),          # original video (its AAC track is dropped)
           "-i", str(C.MIXED_WAV),             # our synchronised audio
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy",                     # picture untouched
           "-c:a", "aac", "-b:a", "192k", "-ar", str(C.SR),
           "-movflags", "+faststart",
           "-shortest", str(C.FINAL_MP4)]
    subprocess.run(cmd, check=True)
    print(f"wrote {C.FINAL_MP4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

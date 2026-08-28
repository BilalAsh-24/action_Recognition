"""Mux the POLISHED audio with the original silent video (new output, originals kept)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C
from polish_mix import MIXED_WAV_POLISHED, FINAL_MP4_POLISHED

FINAL_MP4_POLISHED.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error",
                "-i", str(C.SOURCE_VIDEO), "-i", str(MIXED_WAV_POLISHED),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(C.SR),
                "-movflags", "+faststart", "-shortest", str(FINAL_MP4_POLISHED)], check=True)
print(f"wrote {FINAL_MP4_POLISHED}")

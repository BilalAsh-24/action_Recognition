#!/usr/bin/env python
"""Derive the short cup-placement Foley asset from the approved 10 s MOSS source.

This is a trim, not a generation: one contact+resonance+settle cluster is cut out
with short fades. The 10 s source is left untouched.
"""
import sys
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C

def main():
    if C.ASSET_PLACEMENT.exists():
        print(f"exists, not regenerating: {C.ASSET_PLACEMENT.name}")
        return 0
    y, sr = sf.read(C.PLACEMENT_SOURCE)
    assert sr == C.SR and y.ndim == 1
    lo, hi = C.PLACEMENT_CROP
    seg = y[int(lo * sr):int(hi * sr)].astype(np.float64).copy()
    n = int(C.FADE_MS / 1000 * sr)
    seg[:n] *= np.linspace(0, 1, n); seg[-n:] *= np.linspace(1, 0, n)
    sf.write(C.ASSET_PLACEMENT, seg.astype(np.float32), sr, subtype="PCM_16")
    print(f"wrote {C.ASSET_PLACEMENT.name}  {len(seg)/sr:.3f}s  "
          f"peak {20*np.log10(np.abs(seg).max()):.1f} dBFS  from {lo}-{hi}s of "
          f"{C.PLACEMENT_SOURCE.name} (+{C.FADE_MS} ms fades)")
    return 0

if __name__ == "__main__":
    sys.exit(main())

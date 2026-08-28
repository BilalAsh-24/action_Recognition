"""Frame-level visual event localisation inside each Module 2 action interval.

Module 2 gives broad action spans. Placing Foley at the start of a span would be
wrong: the audible event happens at a specific instant inside it. This module
finds those instants from frame motion.

Frames are decoded with ffmpeg to a small greyscale raw stream — no extra Python
dependencies, and small enough to hold entirely in memory (240 x 90 x 160 bytes).

Region conventions (fractions of frame height):
    feet   0.55-1.00   lower body / floor contact
    head   0.00-0.50   head, hands, mug at face height
    table  0.40-0.85   table surface where the mug is set down
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

W, H = 320, 180


def load_frames(video: Path, fps: float = 24.0) -> np.ndarray:
    """Decode to (T, H, W) uint8 greyscale."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(video),
           "-vf", f"fps={fps},scale={W}:{H}", "-pix_fmt", "gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, H, W)


def motion(frames: np.ndarray, y0: float = 0.0, y1: float = 1.0) -> np.ndarray:
    """Per-frame mean |difference| within a horizontal band. Length T (first = 0)."""
    a, b = int(y0 * frames.shape[1]), int(y1 * frames.shape[1])
    band = frames[:, a:b, :].astype(np.float32)
    d = np.abs(np.diff(band, axis=0)).mean(axis=(1, 2))
    return np.concatenate([[0.0], d])


def _smooth(x: np.ndarray, k: int = 3) -> np.ndarray:
    if k <= 1:
        return x
    return np.convolve(x, np.ones(k) / k, mode="same")


def _local_maxima(x: np.ndarray, min_gap: int, thresh: float) -> list[int]:
    out = []
    for i in range(1, len(x) - 1):
        if x[i] >= x[i - 1] and x[i] > x[i + 1] and x[i] >= thresh:
            if not out or i - out[-1] >= min_gap:
                out.append(i)
            elif x[i] > x[out[-1]]:
                out[-1] = i
    return out


@dataclass
class VisualEvent:
    action: str
    kind: str                 # foot_contact | sip_hold | mug_table_contact | lift
    t_s: float
    confidence: str           # high | medium | low
    basis: str


def find_events(video: Path, actions: list[dict], fps: float = 24.0) -> tuple[list[VisualEvent], dict]:
    frames = load_frames(video, fps)
    T = len(frames)
    t = np.arange(T) / fps
    m_all = _smooth(motion(frames))
    m_feet = _smooth(motion(frames, 0.62, 1.00))   # tight on feet/floor; robust across prominence settings
    m_head = _smooth(motion(frames, 0.00, 0.50))
    m_table = _smooth(motion(frames, 0.40, 0.85))
    events: list[VisualEvent] = []

    def win(a, b):
        return (t >= a) & (t < b)

    for act in actions:
        name, a, b = act["action"], act["start"], act["end"]
        sel = win(a, b)
        idx = np.flatnonzero(sel)
        if len(idx) < 3:
            continue

        if name.startswith("walk"):
            # A step = a leg swing (prominent motion peak) resolving into a plant
            # (the following local minimum). The audible contact is the plant.
            # Prominence is essential: without it, low-amplitude ripples between
            # real steps are mistaken for steps.
            # Search a widened window so a swing peak sitting exactly on the
            # interval boundary is still detectable; keep only plants that fall
            # inside the Module 2 interval.
            MARGIN = 0.40
            import m3_config as _C
            wa, wb = getattr(_C, "WALK_SEARCH_SPAN", (a, b))
            widx = np.flatnonzero(win(min(a, wa) - MARGIN, max(b, wb) + MARGIN))
            seg = m_feet[widx]
            prom = max(0.15 * (seg.max() - seg.min()), 0.15 * seg.std())
            pk, _ = find_peaks(seg, prominence=prom, distance=max(1, int(0.25 * fps)))
            for p in pk:
                j = p
                while j + 1 < len(seg) and seg[j + 1] <= seg[j]:
                    j += 1
                tc = float(t[widx[j]])
                if wa <= tc < wb:
                    events.append(VisualEvent(name, "foot_contact", tc, "high",
                                              f"leg-swing peak (prominence>={prom:.3f}) resolved to the "
                                              f"following minimum = foot plant"))

        elif name.startswith("drink"):
            # A sip = mug held at the lips: a sustained LOW-motion hold in the head
            # region, bounded by the raise and lower movements.
            seg = m_head[idx]
            lowthr = np.percentile(seg, 40)
            holds, run = [], []
            for k, v in enumerate(seg):
                if v <= lowthr:
                    run.append(k)
                else:
                    if len(run) >= max(2, int(0.15 * fps)):
                        holds.append(run[len(run) // 2])
                    run = []
            if len(run) >= max(2, int(0.15 * fps)):
                holds.append(run[len(run) // 2])
            for hcenter in holds:
                events.append(VisualEvent(name, "sip_hold", float(t[idx[hcenter]]), "medium",
                                          "sustained low head-region motion = mug held at lips"))

        elif name.startswith("place"):
            # Contact = the last significant downward movement in the table region
            # before motion collapses to rest.
            seg = m_table[idx]
            thr = seg.mean() + 0.3 * seg.std()
            peaks = _local_maxima(seg, min_gap=max(1, int(0.12 * fps)), thresh=thr)
            if peaks:
                p = peaks[-1]
                j = p
                while j + 1 < len(seg) and seg[j + 1] <= seg[j]:
                    j += 1
                events.append(VisualEvent(name, "mug_table_contact", float(t[idx[j]]), "medium",
                                          "final table-region motion peak resolved to rest = mug meets table"))
            else:
                k = int(np.argmin(seg))
                events.append(VisualEvent(name, "mug_table_contact", float(t[idx[k]]), "low",
                                          "no clear peak; motion minimum used"))

        elif name.startswith("pick"):
            seg = m_table[idx]
            thr = seg.mean() + 0.3 * seg.std()
            peaks = _local_maxima(seg, min_gap=max(1, int(0.12 * fps)), thresh=thr)
            if peaks:
                events.append(VisualEvent(name, "lift", float(t[idx[peaks[0]]]), "medium",
                                          "first table-region motion peak = mug lifted (localised for metadata only)"))

    diag = {"frames": int(T), "fps": fps, "grid": [W, H],
            "motion_all_mean": float(m_all.mean()),
            "motion_by_action": {}}
    for act in actions:
        sel = win(act["start"], act["end"])
        diag["motion_by_action"][act["action"]] = {
            "all": round(float(m_all[sel].mean()), 4),
            "feet": round(float(m_feet[sel].mean()), 4),
            "head": round(float(m_head[sel].mean()), 4),
            "table": round(float(m_table[sel].mean()), 4)}
    return events, diag


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import m3_config as C
    acts = json.loads(C.MODULE2_JSON.read_text())["resolved_actions"]
    ev, diag = find_events(C.SOURCE_VIDEO, acts)
    out = {"diagnostics": diag, "events": [asdict(e) for e in ev]}
    C.EVENTS_JSON.write_text(json.dumps(out, indent=2))
    print(json.dumps(diag, indent=2))
    print("\n=== VISUAL EVENTS ===")
    for e in ev:
        print(f"  {e.t_s:>6.3f}s  {e.action:<20} {e.kind:<18} {e.confidence}")
    print(f"\nwrote {C.EVENTS_JSON}")

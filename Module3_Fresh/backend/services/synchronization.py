"""Visual event localisation and temporal alignment for arbitrary actions.

Generalises the validated Module 3 implementation. Frame primitives (decode, band
motion, smoothing) are imported from scripts/visual_events.py rather than rewritten;
the per-action detection and alignment logic is parameterised by the FoleySpec
strategy so new action types need no new code here.

Alignment principle (unchanged from the validated pipeline): a clip is positioned so
its TRUE ENVELOPE ATTACK coincides with the visual event. Onset-strength peaks are
not used as anchors — they lag or lead the real attack by tens to hundreds of ms.
Clips are shifted, never time-stretched.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import find_peaks, hilbert

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visual_events import load_frames, motion, _smooth          # validated primitives
from services.prompt_map import FoleySpec

BANDS = {"feet": (0.62, 1.00), "head": (0.00, 0.50),
         "table": (0.40, 0.85), "full": (0.00, 1.00)}


@dataclass
class VisualEvent:
    action: str
    kind: str
    t_s: float
    confidence: str
    basis: str
    def dict(self): return asdict(self)


# ------------------------------------------------------------------ audio utils
def envelope(y: np.ndarray, sr: int) -> np.ndarray:
    e = np.abs(hilbert(y))
    k = max(1, int(0.002 * sr))
    return np.convolve(e, np.ones(k) / k, mode="same")


def attack_times(y: np.ndarray, sr: int, min_gap_s=0.20, gate_db=-30.0) -> np.ndarray:
    """True transient attack times from the amplitude envelope."""
    env = envelope(y, sr)
    prom = max(0.08 * env.max(), 3.0 * np.percentile(env, 25))
    pk, _ = find_peaks(env, prominence=prom, distance=int(min_gap_s * sr))
    if not len(pk):
        return np.array([])
    pk = pk[env[pk] >= env[pk].max() * 10 ** (gate_db / 20)]
    out = []
    for i in pk:
        thr, j, lo = 0.20 * env[i], i, max(0, i - int(0.30 * sr))
        while j > lo and env[j] > thr:
            j -= 1
        out.append(j / sr)
    out = np.array(sorted(set(round(x, 4) for x in out)))
    if not len(out):
        return out
    ded = [out[0]]
    for x in out[1:]:
        if x - ded[-1] >= min_gap_s:
            ded.append(x)
    return np.array(ded)


def first_attack(y: np.ndarray, sr: int) -> float:
    env = envelope(y, sr)
    idx = np.flatnonzero(env >= 0.35 * env.max())
    return float(idx[0] / sr) if len(idx) else 0.0


def band_ratio(y, sr, lo, hi) -> float:
    import librosa
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=256))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    return float(np.sum(S[(f >= lo) & (f < hi)] ** 2) / (np.sum(S ** 2) + 1e-20))


# ------------------------------------------------------------- visual detection
def analyse_video(video: Path, fps: float = 24.0) -> dict:
    frames = load_frames(video, fps)
    return {"n": len(frames), "fps": fps,
            "t": np.arange(len(frames)) / fps,
            "bands": {k: _smooth(motion(frames, *v)) for k, v in BANDS.items()}}


def detect_events(mo: dict, action: str, spec: FoleySpec | None,
                  a: float, b: float, search: tuple[float, float] | None = None
                  ) -> list[VisualEvent]:
    """Locate audible instants for one action interval."""
    if spec is None or spec.strategy == "none":
        return []
    t, fps = mo["t"], mo["fps"]
    m = mo["bands"][spec.region]
    sa, sb = search if search else (a, b)
    MARGIN = 0.40
    widx = np.flatnonzero((t >= min(a, sa) - MARGIN) & (t < max(b, sb) + MARGIN))
    if len(widx) < 3:
        return []
    seg = m[widx]
    ev: list[VisualEvent] = []

    if spec.strategy == "footstep":
        prom = max(0.15 * (seg.max() - seg.min()), 0.15 * seg.std())
        pk, _ = find_peaks(seg, prominence=prom, distance=max(1, int(0.25 * fps)))
        for p in pk:
            j = p
            while j + 1 < len(seg) and seg[j + 1] <= seg[j]:
                j += 1
            tc = float(t[widx[j]])
            if sa <= tc < sb:
                ev.append(VisualEvent(action, "foot_contact", tc, "high",
                                      "motion peak resolved to following minimum (plant)"))

    elif spec.strategy == "hold":
        idx = np.flatnonzero((t >= a) & (t < b))
        s2 = m[idx]
        low = np.percentile(s2, 40)
        run, holds = [], []
        for k, v in enumerate(s2):
            if v <= low:
                run.append(k)
            else:
                if len(run) >= max(2, int(0.15 * fps)):
                    holds.append(run[len(run) // 2])
                run = []
        if len(run) >= max(2, int(0.15 * fps)):
            holds.append(run[len(run) // 2])
        for h in holds:
            ev.append(VisualEvent(action, "hold", float(t[idx[h]]), "medium",
                                  "sustained low motion = object held still"))

    elif spec.strategy == "contact":
        idx = np.flatnonzero((t >= a) & (t < b))
        s2 = m[idx]
        thr = s2.mean() + 0.3 * s2.std()
        pk, _ = find_peaks(s2, height=thr, distance=max(1, int(0.12 * fps)))
        if len(pk):
            p = pk[-1] if "place" in action or spec.key.endswith("placement") else pk[0]
            j = p
            while j + 1 < len(s2) and s2[j + 1] <= s2[j]:
                j += 1
            ev.append(VisualEvent(action, "contact", float(t[idx[j]]), "medium",
                                  "motion peak resolved to rest = contact"))
        else:
            k = int(np.argmin(s2))
            ev.append(VisualEvent(action, "contact", float(t[idx[k]]), "low",
                                  "no clear peak; motion minimum used"))

    elif spec.strategy == "continuous":
        # A continuous action still has a START. Placing audio at the label edge is
        # exactly the "trust the boundary" mistake this project avoids: the label is
        # a coarse span, the motion tells us when the activity actually begins.
        idx = np.flatnonzero((t >= a - 0.40) & (t < b))
        s2 = m[idx]
        thr = float(np.median(m) + 0.5 * m.std())
        rise = np.flatnonzero(s2 > thr)
        if len(rise):
            tc = float(t[idx[rise[0]]])
            ev.append(VisualEvent(action, "activity_start", tc, "medium",
                                  f"first frame whose motion exceeds {thr:.2f} "
                                  f"(median + 0.5 sd) = activity begins"))
        else:
            ev.append(VisualEvent(action, "activity_start", float(a), "low",
                                  "no clear motion rise; interval start used"))
    return ev


# ------------------------------------------------------------ segment selection
def select_event_clip(y, sr, half_lo=0.05, half_hi=0.35) -> tuple[float, float]:
    """Best single contact-plus-resonance window: highest peak, cleanest edges."""
    ats = attack_times(y, sr, min_gap_s=0.25, gate_db=-25.0)
    if not len(ats):
        return 0.0, min(0.4, len(y) / sr)
    env = envelope(y, sr)
    best, best_score = (0.0, 0.4), -1e9
    for t0 in ats:
        lo = max(0.0, t0 - half_lo); hi = min(len(y) / sr, t0 + half_hi)
        a, b = int(lo * sr), int(hi * sr)
        if b - a < int(0.08 * sr):
            continue
        seg = y[a:b]
        peak = float(np.abs(seg).max())
        n = max(1, int(0.005 * sr))
        edge = max(np.abs(seg[:n]).max(), np.abs(seg[-n:]).max())
        score = 20 * np.log10(max(peak, 1e-12)) - 20 * np.log10(max(edge / max(peak, 1e-12), 1e-6))
        if score > best_score:
            best, best_score = (lo, hi), score
    return best


def select_wet_segments(y, sr, n_want, half_s=0.35, min_wet=0.45) -> list[tuple[float, float]]:
    """Isolated segments dominated by 200 Hz-1 kHz energy (mouth/liquid content)."""
    cands = []
    for t0 in attack_times(y, sr, min_gap_s=0.25, gate_db=-22.0):
        a, b = int((t0 - half_s) * sr), int((t0 + half_s) * sr)
        if a < 0 or b > len(y):
            continue
        seg = y[a:b]
        wet = band_ratio(seg, sr, 200, 1000)
        if wet >= min_wet:
            cands.append((float(np.abs(seg).max()), wet, t0 - half_s, t0 + half_s))
    cands.sort(key=lambda c: -c[0])
    if not cands:                       # fall back to the loudest transients
        for t0 in attack_times(y, sr, min_gap_s=0.25, gate_db=-25.0):
            a, b = int((t0 - half_s) * sr), int((t0 + half_s) * sr)
            if a >= 0 and b <= len(y):
                cands.append((float(np.abs(y[a:b]).max()), 0.0, t0 - half_s, t0 + half_s))
        cands.sort(key=lambda c: -c[0])
    return [(c[2], c[3]) for c in cands[:max(1, n_want)]]


# --------------------------------------------------------------------- planning
def plan_action(spec: FoleySpec, asset: Path, events: list[VisualEvent],
                interval: tuple[float, float], video_end: float,
                search: tuple[float, float] | None = None) -> list[dict]:
    """Produce placement entries aligning asset audio to the detected events."""
    y, sr = sf.read(asset)
    y = y.astype(np.float64)
    a, b = interval
    # Audio may legitimately extend outside the Module 2 interval when a wider
    # search span was used (e.g. footsteps that begin before the labelled walk).
    # Clamp to the SEARCH span, not the label.
    lo_bound, hi_bound = (search if search else (a, b))
    lo_bound = max(0.0, min(lo_bound, a))
    hi_bound = min(video_end, max(hi_bound, b))
    out: list[dict] = []

    if spec.selection == "steps" and events:
        steps = attack_times(y, sr, min_gap_s=0.25, gate_db=-30.0)
        if not len(steps):
            return out
        contacts = sorted(e.t_s for e in events)
        n = len(contacts)
        if n >= 2 and len(steps) >= n:
            vis = np.diff(contacts)
            best, best_err = 0, None
            for k in range(len(steps) - n + 1):
                err = float(np.sum((np.diff(steps[k:k + n]) - vis) ** 2))
                if best_err is None or err < best_err:
                    best, best_err = k, err
            run = steps[best:best + n]
        else:
            run = steps[:1]
        anchor = float(run[0])
        offset = contacts[0] - anchor
        src_start = max(0.0, anchor - 0.30, lo_bound - offset)
        src_end = min(len(y) / sr, float(run[-1]) + 0.35, hi_bound - offset)
        if src_end - src_start < 0.05:
            return out
        out.append({"asset_start_s": round(src_start, 4), "asset_end_s": round(src_end, 4),
                    "video_start_s": round(src_start + offset, 4),
                    "aligned_to_s": round(contacts[0], 4), "alignment_kind": "foot_contact",
                    "visible_events_s": [round(c, 3) for c in contacts],
                    "per_event_error_ms": [round(1000 * (float(r) + offset - c), 1)
                                           for r, c in zip(run, contacts)],
                    "strategy": "continuous slice shifted so a natural step run lands on the "
                                "visible contacts; never time-stretched"})

    elif spec.selection == "wet_segment" and events:
        segs = select_wet_segments(y, sr, n_want=len(events))
        for i, (ev, (s0, s1)) in enumerate(zip(events, segs), 1):
            clip = y[int(s0 * sr):int(s1 * sr)]
            on = first_attack(clip, sr)
            out.append({"index": i, "asset_start_s": round(s0, 4), "asset_end_s": round(s1, 4),
                        "video_start_s": round(ev.t_s - on, 4),
                        "aligned_to_s": round(ev.t_s, 4), "alignment_kind": ev.kind,
                        "clip_onset_offset_s": round(on, 4),
                        "strategy": "isolated wet segment, attack aligned to the visible hold"})

    elif spec.selection == "event" and events:
        s0, s1 = select_event_clip(y, sr)
        clip = y[int(s0 * sr):int(s1 * sr)]
        on = first_attack(clip, sr)
        ev = events[0]
        out.append({"asset_start_s": round(s0, 4), "asset_end_s": round(s1, 4),
                    "video_start_s": round(ev.t_s - on, 4),
                    "aligned_to_s": round(ev.t_s, 4), "alignment_kind": ev.kind,
                    "clip_onset_offset_s": round(on, 4),
                    "strategy": "single contact event extracted from the generated asset, "
                                "attack aligned to the visible contact"})

    elif spec.selection == "slice":
        start = events[0].t_s if events else a
        # allow up to 0.40 s of lead-in before the label when motion says the
        # activity actually started earlier
        floor = max(0.0, min(lo_bound, a - 0.40))
        start = max(floor, min(start, b - 0.05))
        span = min(b - start, len(y) / sr)
        if span <= 0.05:
            return out
        # Begin the slice at the asset's own first transient so the clip does not
        # open mid-gesture, then align that transient to the visible activity start.
        ats = attack_times(y, sr, min_gap_s=0.15, gate_db=-30.0)
        src0 = float(ats[0]) if len(ats) and ats[0] < 0.5 else 0.0
        src1 = min(len(y) / sr, src0 + span)
        out.append({"asset_start_s": round(src0, 4), "asset_end_s": round(src1, 4),
                    "video_start_s": round(start, 4),
                    "aligned_to_s": round(start, 4), "alignment_kind": "activity_start",
                    "strategy": "continuous slice beginning at the asset's first transient, "
                                "aligned to the visible start of the activity"})
    return out

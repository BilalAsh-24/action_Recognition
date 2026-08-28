"""Build the synchronisation plan: Module 2 timeline + visual events -> Foley placements.

Core principle: a Foley clip is positioned so that its *audible onset* coincides with
the visual event, not so that its file start coincides with the action interval start.

Strategies per action:
  walking   - a continuous slice of the walking asset spanning the action interval,
              time-shifted so one of its natural footsteps lands on the detected
              foot-plant. Preserves MOSS's own 108 steps/min cadence.
  drinking  - one isolated sip/swallow segment per detected sip-hold, each aligned
              by its own onset.
  placement - the 400 ms contact asset, aligned by its attack.
  pickup    - no approved asset; recorded as unavailable, never fabricated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C


def envelope(y: np.ndarray, sr: int) -> np.ndarray:
    e = np.abs(hilbert(y))
    k = max(1, int(0.002 * sr))
    return np.convolve(e, np.ones(k) / k, mode="same")


def onsets(y: np.ndarray, sr: int, min_gap_s=0.20, gate_db=-30.0) -> np.ndarray:
    """True transient ATTACK times, gated relative to the loudest transient.

    Detected from the amplitude envelope, not from onset *strength*. Onset-strength
    peaks lag (or lead) the real attack by tens to hundreds of milliseconds, which
    is fatal when the value is used as a synchronisation anchor: aligning a
    strength peak to a visual event misplaces the audible transient by that lag.
    Here each envelope maximum is back-tracked to where the envelope last rose
    through 20 % of that maximum -- the perceived moment of contact.
    """
    from scipy.signal import find_peaks
    env = envelope(y, sr)
    prom = max(0.08 * env.max(), 3.0 * np.percentile(env, 25))
    pk, _ = find_peaks(env, prominence=prom, distance=int(min_gap_s * sr))
    if not len(pk):
        return np.array([])
    keep = env[pk] >= env[pk].max() * 10 ** (gate_db / 20)
    pk = pk[keep]
    out = []
    for i in pk:
        thr = 0.20 * env[i]
        j = i
        lo = max(0, i - int(0.30 * sr))
        while j > lo and env[j] > thr:
            j -= 1
        out.append(j / sr)
    out = np.array(sorted(set(round(x, 4) for x in out)))
    # drop attacks closer together than min_gap (same physical event)
    ded = [out[0]]
    for x in out[1:]:
        if x - ded[-1] >= min_gap_s:
            ded.append(x)
    return np.array(ded)


def first_onset(y: np.ndarray, sr: int) -> float:
    """Time of the primary attack inside a clip (for alignment)."""
    env = envelope(y, sr)
    peak = env.max()
    idx = np.flatnonzero(env >= 0.35 * peak)
    return float(idx[0] / sr) if len(idx) else 0.0


def band_ratio(y, sr, lo, hi):
    import librosa
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=256))
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    return float(np.sum(S[(f >= lo) & (f < hi)] ** 2) / (np.sum(S ** 2) + 1e-20))


def pick_wet_segments(y, sr, n_want, half_s=0.35):
    """Isolated, low-mid-dominant (sip/swallow) segments from the drinking asset."""
    cands = []
    for t in onsets(y, sr, min_gap_s=0.25, gate_db=-22.0):
        a, b = int((t - half_s) * sr), int((t + half_s) * sr)
        if a < 0 or b > len(y):
            continue
        seg = y[a:b]
        wet = band_ratio(seg, sr, 200, 1000)
        env = envelope(y, sr)
        pk = env[max(0, int((t - .02) * sr)):min(len(y), int((t + .3) * sr))].max()
        pre = env[max(0, int((t - .45) * sr)):max(0, int((t - .36) * sr))]
        iso = 20 * np.log10(max(pre.max(), 1e-12) / pk) if len(pre) else 0.0
        if wet >= 0.45:
            cands.append({"t": float(t), "wet": wet, "peak": float(pk), "iso_db": float(iso),
                          "start": (t - half_s), "end": (t + half_s)})
    cands.sort(key=lambda c: (-c["peak"], c["iso_db"]))
    return cands[:n_want]


def build_plan() -> dict:
    m2 = json.loads(C.MODULE2_JSON.read_text())
    actions = m2["resolved_actions"]
    vis = json.loads(C.EVENTS_JSON.read_text())
    events = vis["events"]
    by_action: dict[str, list[dict]] = {}
    for e in events:
        by_action.setdefault(e["action"], []).append(e)

    plan = {"placements": [], "unavailable": [], "assets": {}}

    # ---------------- walking -------------------------------------------------
    wy, sr = sf.read(C.ASSET_WALKING); wy = wy.astype(np.float64)
    steps = onsets(wy, sr, min_gap_s=0.25, gate_db=-30.0)
    plan["assets"]["walking"] = {"path": str(C.ASSET_WALKING.relative_to(C.ROOT)),
                                 "duration_s": round(len(wy) / sr, 4),
                                 "detected_steps": [round(float(x), 3) for x in steps]}
    wact = next(a for a in actions if a["action"].startswith("walk"))
    contacts = sorted(e["t_s"] for e in by_action.get(wact["action"], []))
    if contacts and len(steps):
        # Align the asset's own consecutive footsteps to the visible foot plants.
        # The clip is only SHIFTED: we search every consecutive run of len(contacts)
        # asset steps and keep the run whose internal spacing best matches the visible
        # gait, then translate it so its first step lands on the first visible plant.
        n = len(contacts)
        vis_gaps = np.diff(contacts)
        best, best_err = None, None
        if n == 1 or len(steps) < n:
            best, best_err = 0, 0.0
        else:
            for k in range(len(steps) - n + 1):
                err = float(np.sum((np.diff(steps[k:k + n]) - vis_gaps) ** 2))
                if best_err is None or err < best_err:
                    best, best_err = k, err
        run = steps[best:best + n] if len(steps) >= best + n else steps[best:]
        anchor = float(run[0])
        offset = contacts[0] - anchor                      # video_t = source_t + offset
        lead_in, tail = 0.30, 0.35
        src_start = max(0.0, anchor - lead_in)
        # clamp the decay tail so it never bleeds into the next (silent) action
        src_end = min(len(wy) / sr, float(run[-1]) + tail, wact["end"] - offset)
        landed = [round(float(x + offset), 3) for x in steps if src_start <= x <= src_end]
        errs = [round(1000 * (float(r) + offset - c), 1) for r, c in zip(run, contacts)]
        plan["placements"].append({
            "action": wact["action"], "asset": "walking",
            "video_start_s": round(src_start + offset, 4),
            "source_start_s": round(src_start, 4), "source_end_s": round(src_end, 4),
            "duration_s": round(src_end - src_start, 4),
            "aligned_to_visual_event_s": round(contacts[0], 4),
            "alignment_kind": "foot_contact",
            "aligned_source_onset_s": round(anchor, 4),
            "shift_offset_s": round(offset, 4),
            "visible_contacts_s": [round(c, 3) for c in contacts],
            "asset_step_run_s": [round(float(x), 3) for x in run],
            "steps_inside_window": landed,
            "per_contact_error_ms": errs,
            "strategy": "continuous slice SHIFTED (never stretched); the consecutive asset step-run "
                        "whose spacing best matches the visible gait is translated onto the visible "
                        "foot plants. Spans the whole walking sequence, including the part Module 2 "
                        "labelled 'stand' (flagged suspect; footage shows walking)."})

    # ---------------- drinking ------------------------------------------------
    dy, _ = sf.read(C.ASSET_DRINKING); dy = dy.astype(np.float64)
    dact = next(a for a in actions if a["action"].startswith("drink"))
    sips = [e["t_s"] for e in by_action.get(dact["action"], [])]
    segs = pick_wet_segments(dy, sr, n_want=len(sips))
    plan["assets"]["drinking"] = {"path": str(C.ASSET_DRINKING.relative_to(C.ROOT)),
                                  "duration_s": round(len(dy) / sr, 4),
                                  "selected_sip_segments": [{"src_s": round(s["start"], 3),
                                                             "end_s": round(s["end"], 3),
                                                             "wet_200_1k": round(s["wet"], 3)} for s in segs]}
    for k, (tv, seg) in enumerate(zip(sips, segs)):
        clip = dy[int(seg["start"] * sr):int(seg["end"] * sr)]
        on = first_onset(clip, sr)
        plan["placements"].append({
            "action": dact["action"], "asset": "drinking", "index": k + 1,
            "video_start_s": round(tv - on, 4),
            "source_start_s": round(seg["start"], 4), "source_end_s": round(seg["end"], 4),
            "duration_s": round(seg["end"] - seg["start"], 4),
            "aligned_to_visual_event_s": round(tv, 4),
            "alignment_kind": "sip_hold",
            "clip_onset_offset_s": round(on, 4),
            "strategy": "isolated sip/swallow segment, onset aligned to the visible sip hold"})

    # ---------------- placement ----------------------------------------------
    py, _ = sf.read(C.ASSET_PLACEMENT); py = py.astype(np.float64)
    pact = next(a for a in actions if a["action"].startswith("place"))
    pcs = [e["t_s"] for e in by_action.get(pact["action"], [])]
    plan["assets"]["placement"] = {"path": str(C.ASSET_PLACEMENT.relative_to(C.ROOT)),
                                   "duration_s": round(len(py) / sr, 4),
                                   "derived_from": str(C.PLACEMENT_SOURCE.name),
                                   "source_crop_s": list(C.PLACEMENT_CROP)}
    if pcs:
        on = first_onset(py, sr)
        plan["placements"].append({
            "action": pact["action"], "asset": "placement",
            "video_start_s": round(pcs[0] - on, 4),
            "source_start_s": 0.0, "source_end_s": round(len(py) / sr, 4),
            "duration_s": round(len(py) / sr, 4),
            "aligned_to_visual_event_s": round(pcs[0], 4),
            "alignment_kind": "mug_table_contact",
            "clip_onset_offset_s": round(on, 4),
            "strategy": "400 ms contact asset, attack aligned to the visible mug-table contact"})

    # ---------------- unavailable --------------------------------------------
    for a in actions:
        if a["action"] in C.UNAVAILABLE_FOLEY:
            ev = by_action.get(a["action"], [])
            plan["unavailable"].append({
                "action": a["action"], "interval_s": [a["start"], a["end"]],
                "visual_event_s": round(ev[0]["t_s"], 4) if ev else None,
                "reason": C.UNAVAILABLE_FOLEY[a["action"]], "audio_written": False})
    return plan


if __name__ == "__main__":
    p = build_plan()
    out = C.ROOT / "results" / "sync_plan.json"
    out.write_text(json.dumps(p, indent=2))
    print("=== PLACEMENTS ===")
    for x in p["placements"]:
        print(f"  {x['action']:<20} {x['asset']:<10} video {x['video_start_s']:>6.3f}s "
              f"+{x['duration_s']:.3f}s  <- src {x['source_start_s']:.3f}-{x['source_end_s']:.3f}s"
              f"  aligned@{x['aligned_to_visual_event_s']:.3f}s ({x['alignment_kind']})")
    print("\n=== UNAVAILABLE ===")
    for x in p["unavailable"]:
        print(f"  {x['action']:<20} {x['interval_s']}  -> silent")
    print(f"\nwrote {out}")

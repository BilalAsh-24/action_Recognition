"""Mixing and polish. Same chain as the validated Module 3 implementation.

Per clip : DC removal -> zero-crossing-safe trim -> raised-cosine fades ->
           active-RMS level -> per-clip peak cap
Bus      : sum -> linear normalisation -> safety limiter (protection only)

No compression is applied unless the limiter actually engages, and the gain
reduction is always reported.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C
from services.foley_validation import MAX_AUTO_GAIN_DB


def snap_zero(y: np.ndarray, i: int, search: int) -> int:
    lo, hi = max(1, i - search), min(len(y) - 1, i + search)
    best, bestd = i, search + 1
    for j in range(lo, hi):
        if y[j - 1] == 0.0 or (y[j - 1] < 0) != (y[j] < 0):
            if abs(j - i) < bestd:
                best, bestd = j, abs(j - i)
    return best


def rcos_fade(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    n = min(int(ms / 1000 * sr), len(x) // 2)
    if n < 2:
        return x
    w = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    x = x.copy(); x[:n] *= w; x[-n:] *= w[::-1]
    return x


def active_rms(x: np.ndarray) -> float:
    f = 1024
    fr = np.array([np.sqrt(np.mean(x[i:i + f] ** 2))
                   for i in range(0, max(1, len(x) - f), f // 2)])
    if not len(fr):
        return float(np.sqrt(np.mean(x ** 2)))
    # Gate on the 60th percentile OR 40 dB below the loudest frame, whichever is
    # higher. The percentile alone degenerates to 0 when a clip is mostly digital
    # silence, which would make this identical to a whole-file RMS.
    thr = max(float(np.percentile(fr, 60)), float(fr.max()) * 10 ** (-40 / 20))
    sel = fr[fr >= thr]
    return float(np.sqrt(np.mean(sel ** 2))) if len(sel) else float(fr.max())


def soft_limit(x: np.ndarray, thresh_db: float, ceiling_db: float) -> tuple[np.ndarray, float]:
    t, c = 10 ** (thresh_db / 20), 10 ** (ceiling_db / 20)
    a = np.abs(x); over = a > t
    if not over.any():
        return x, 0.0
    y = x.copy(); room = c - t
    y[over] = np.sign(x[over]) * (t + room * np.tanh((a[over] - t) / max(room, 1e-9)))
    gr = 20 * np.log10(np.max(a[over]) / max(np.max(np.abs(y[over])), 1e-12))
    return y, float(gr)


def mix(placements: list[dict], duration_s: float, out_wav: Path,
        sample_rate: int = 48000) -> dict:
    """placements: [{asset, asset_start_s, asset_end_s, video_start_s, target_rms_dbfs, ...}]"""
    n = int(round(duration_s * sample_rate))
    bus = np.zeros(n, dtype=np.float64)
    log = {"sample_rate": sample_rate, "duration_s": round(duration_s, 6),
           "tracks": [], "truncations": [], "rejected": [],
           "max_auto_gain_db": MAX_AUTO_GAIN_DB}

    for p in placements:
        y, sr = sf.read(p["asset"])
        y = y.astype(np.float64)
        if sr != sample_rate:
            raise ValueError(f"asset sample-rate {sr} != {sample_rate}")
        srch = int(0.003 * sr)
        a0 = snap_zero(y, int(p["asset_start_s"] * sr), srch)
        a1 = snap_zero(y, int(p["asset_end_s"] * sr), srch)
        if a1 <= a0:
            continue
        clip = y[a0:a1].copy()
        snap_ms = round((a0 - int(p["asset_start_s"] * sr)) / sr * 1000, 3)
        dc = float(clip.mean()); clip -= dc
        clip = rcos_fade(clip, sr, C.FADE_MS)

        raw_peak, raw_arms = float(np.abs(clip).max()), active_rms(clip)
        g = 10 ** (p["target_rms_dbfs"] / 20) / max(raw_arms, 1e-12)

        # Hard safety limit. A clip needing more than MAX_AUTO_GAIN_DB has too little
        # signal to level; applying the gain would amplify quantisation noise into
        # audible hiss. Refuse it rather than clamping — clamping still admits noise.
        need_db = 20 * np.log10(max(g, 1e-12))
        if need_db > MAX_AUTO_GAIN_DB:
            log["rejected"].append({
                "action": p.get("action"), "asset": Path(p["asset"]).name,
                "stage": "mixer_gain_limit",
                "required_gain_db": round(float(need_db), 2),
                "limit_db": MAX_AUTO_GAIN_DB,
                "reason": (f"selected segment would need {need_db:+.1f} dB of make-up gain, "
                           f"above the {MAX_AUTO_GAIN_DB} dB safety limit"),
                "user_reason": "generated audio failed quality validation"})
            continue

        cap = 10 ** (C.CLIP_PEAK_CEILING_DBFS / 20) / max(raw_peak, 1e-12)
        capped = g > cap
        g = min(g, cap); clip *= g

        start = int(round((p["video_start_s"] + snap_ms / 1000) * sr))
        trunc = 0
        if start < 0:
            clip = clip[-start:]; start = 0
        if start + len(clip) > n:
            trunc = start + len(clip) - n
            kept = max(0, n - start)
            # A sliver of a contact sound reads as a click rather than as the event.
            # Below MIN_KEPT_FRACTION it is better to omit it than to emit a fragment.
            MIN_KEPT_FRACTION = 0.45
            if kept < MIN_KEPT_FRACTION * len(clip):
                log["rejected"].append({
                    "action": p.get("action"), "asset": Path(p["asset"]).name,
                    "stage": "end_of_video_truncation",
                    "kept_ms": round(kept / sr * 1000, 1),
                    "clip_ms": round(len(clip) / sr * 1000, 1),
                    "reason": (f"only {kept/sr*1000:.0f} ms of a {len(clip)/sr*1000:.0f} ms "
                               f"sound fits before the video ends; a fragment that short "
                               f"reads as a click, so it was omitted"),
                    "user_reason": "the event occurs too close to the end of the video"})
                continue
            clip = rcos_fade(clip[:kept], sr, C.FADE_MS)
            log["truncations"].append({"action": p.get("action"),
                                       "truncated_ms": round(trunc / sr * 1000, 1),
                                       "reason": "clip crosses end of video; tail faded"})
        if len(clip) == 0:
            continue
        bus[start:start + len(clip)] += clip
        log["tracks"].append({
            "action": p.get("action"), "asset": Path(p["asset"]).name, "index": p.get("index"),
            "video_start_s": round(start / sr, 6),
            "video_end_s": round((start + len(clip)) / sr, 6),
            "asset_start_s": round(a0 / sr, 6), "asset_end_s": round(a1 / sr, 6),
            "aligned_to_s": p.get("aligned_to_s"), "alignment_kind": p.get("alignment_kind"),
            "zero_cross_snap_ms": snap_ms, "dc_removed": round(dc, 8),
            "raw_peak_dbfs": round(20 * np.log10(max(raw_peak, 1e-12)), 2),
            "raw_active_rms_dbfs": round(20 * np.log10(max(raw_arms, 1e-12)), 2),
            "target_active_rms_dbfs": p["target_rms_dbfs"],
            "gain_db": round(20 * np.log10(g), 2), "peak_ceiling_engaged": bool(capped),
            "out_peak_dbfs": round(20 * np.log10(max(np.abs(clip).max(), 1e-12)), 2),
            "fade_in_ms": C.FADE_MS, "fade_out_ms": C.FADE_MS,
            "truncated_ms": round(trunc / sr * 1000, 1)})

    pre = float(np.abs(bus).max())
    if pre > 1e-9:
        norm = 10 ** (C.BUS_TARGET_DBFS / 20) / pre
        bus *= norm
    else:
        norm = 1.0
    bus, gr = soft_limit(bus, C.LIMIT_THRESH_DBFS, C.BUS_CEILING_DBFS)
    log["bus"] = {"peak_before_dbfs": round(20 * np.log10(max(pre, 1e-12)), 2),
                  "normalisation_db": round(20 * np.log10(max(norm, 1e-12)), 2),
                  "normalisation_target_dbfs": C.BUS_TARGET_DBFS,
                  "limiter_threshold_dbfs": C.LIMIT_THRESH_DBFS,
                  "max_gain_reduction_db": round(gr, 2), "limiter_engaged": bool(gr > 0.01),
                  "peak_after_dbfs": round(20 * np.log10(max(np.abs(bus).max(), 1e-12)), 2)}

    log["silent"] = bool(pre <= 1e-9)
    if not np.isfinite(bus).all():
        raise ValueError("mix contains NaN or Inf")
    if np.abs(bus).max() >= 1.0:
        raise ValueError("mix clips")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav, bus.astype(np.float32), sample_rate, subtype="PCM_16")
    log["output"] = {"path": str(out_wav), "channels": 1, "subtype": "PCM_16",
                     "peak_dbfs": round(20 * np.log10(max(np.abs(bus).max(), 1e-12)), 2),
                     "rms_dbfs": round(20 * np.log10(max(np.sqrt(np.mean(bus ** 2)), 1e-12)), 2),
                     "crest_db": round(20 * np.log10(max(np.abs(bus).max(), 1e-12) /
                                       max(np.sqrt(np.mean(bus ** 2)), 1e-12)), 2),
                     "clipped_samples": int(np.sum(np.abs(bus) >= 1.0)),
                     "duration_s": round(len(bus) / sample_rate, 6)}
    return log

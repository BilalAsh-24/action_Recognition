"""Conservative post-production pass over the synchronisation plan.

Nothing is regenerated and no approved WAV is altered on disk. Per clip:
  * DC offset removed
  * cut points snapped to the nearest zero crossing (kills edit clicks at source)
  * short raised-cosine fades (gentler than linear, no discontinuity in slope)
  * level set by ACTIVE RMS with a per-clip peak ceiling, so balance is
    perceptual rather than peak-matched
Bus:
  * summed, then a soft-knee limiter that only engages on transient peaks
  * final peak trim to a stated ceiling — no loudness maximising, no compression
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C

ASSET_PATH = {"walking": C.ASSET_WALKING, "drinking": C.ASSET_DRINKING,
              "placement": C.ASSET_PLACEMENT}

# Perceptual balance by ACTIVE RMS (rms of frames above the clip's own noise floor).
TARGET_ACTIVE_RMS_DBFS = {"walk around table": -34.0,
                          "drink from cup": -38.0,
                          "place cup on table": -32.0}
CLIP_PEAK_CEILING_DBFS = -12.0     # per clip, before the bus
BUS_TARGET_DBFS = -6.0             # final peak after transparent normalisation
BUS_CEILING_DBFS = -3.0            # absolute ceiling the limiter must not exceed
LIMIT_THRESH_DBFS = -6.0           # soft limiter knee (safety net only)
FADE_MS = 12.0

MIXED_WAV_POLISHED = C.ROOT / "audio" / "mixed" / "final_synchronized_audio_polished.wav"
FINAL_MP4_POLISHED = C.ROOT / "output" / "final_silent_to_audio_polished.mp4"


def video_duration(p: Path) -> float:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(o.stdout.strip())


def snap_zero(y: np.ndarray, i: int, search: int) -> int:
    """Nearest zero crossing to sample i, within +/- search samples."""
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
    w = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))     # raised cosine
    x = x.copy(); x[:n] *= w; x[-n:] *= w[::-1]
    return x


def active_rms(x: np.ndarray) -> float:
    """RMS over frames above the clip's own 25th-percentile floor — ignores silence."""
    f = 1024
    fr = np.array([np.sqrt(np.mean(x[i:i + f] ** 2)) for i in range(0, max(1, len(x) - f), f // 2)])
    if not len(fr):
        return float(np.sqrt(np.mean(x ** 2)))
    thr = np.percentile(fr, 60)
    sel = fr[fr >= thr]
    return float(np.sqrt(np.mean(sel ** 2))) if len(sel) else float(fr.mean())


def soft_limit(x: np.ndarray, thresh_db: float, ceiling_db: float) -> tuple[np.ndarray, float]:
    """Smooth tanh knee above `thresh`; returns (audio, max gain reduction dB)."""
    t = 10 ** (thresh_db / 20); c = 10 ** (ceiling_db / 20)
    a = np.abs(x); over = a > t
    if not over.any():
        return x, 0.0
    y = x.copy()
    room = c - t
    y[over] = np.sign(x[over]) * (t + room * np.tanh((a[over] - t) / max(room, 1e-9)))
    gr = 20 * np.log10(np.max(a[over]) / np.max(np.abs(y[over])))
    return y, float(gr)


def main() -> int:
    plan = json.loads((C.ROOT / "results" / "sync_plan.json").read_text())
    dur = video_duration(C.SOURCE_VIDEO)
    n = int(round(dur * C.SR))
    mix = np.zeros(n, dtype=np.float64)
    log = {"timeline_duration_s": round(dur, 6), "sample_rate": C.SR, "samples": n,
           "policy": {"level_mode": "active-RMS balance with per-clip peak ceiling",
                      "target_active_rms_dbfs": TARGET_ACTIVE_RMS_DBFS,
                      "clip_peak_ceiling_dbfs": CLIP_PEAK_CEILING_DBFS,
                      "bus_ceiling_dbfs": BUS_CEILING_DBFS,
                      "limiter_threshold_dbfs": LIMIT_THRESH_DBFS,
                      "fade_ms": FADE_MS, "fade_shape": "raised cosine",
                      "zero_crossing_snap": True, "dc_removed": True},
           "tracks": [], "truncations": []}

    for p in plan["placements"]:
        y, sr = sf.read(ASSET_PATH[p["asset"]]); y = y.astype(np.float64)
        assert sr == C.SR
        srch = int(0.003 * sr)                       # +/-3 ms zero-crossing search
        a0 = snap_zero(y, int(p["source_start_s"] * sr), srch)
        a1 = snap_zero(y, int(p["source_end_s"] * sr), srch)
        clip = y[a0:a1].copy()
        snap_shift_ms = round((a0 - int(p["source_start_s"] * sr)) / sr * 1000, 3)

        dc = float(clip.mean()); clip -= dc            # DC removal
        clip = rcos_fade(clip, sr, FADE_MS)

        raw_peak = float(np.abs(clip).max()); raw_arms = active_rms(clip)
        g = 10 ** (TARGET_ACTIVE_RMS_DBFS[p["action"]] / 20) / max(raw_arms, 1e-12)
        cap = 10 ** (CLIP_PEAK_CEILING_DBFS / 20) / max(raw_peak, 1e-12)
        capped = g > cap
        g = min(g, cap)
        clip *= g

        start = int(round((p["video_start_s"] + snap_shift_ms / 1000) * sr))
        trunc = 0
        if start < 0:
            clip = clip[-start:]; start = 0
        if start + len(clip) > n:
            trunc = start + len(clip) - n
            clip = rcos_fade(clip[:n - start], sr, FADE_MS)
            log["truncations"].append({"action": p["action"], "truncated_ms": round(trunc / sr * 1000, 1),
                                       "reason": "clip crosses end of video; tail faded, timeline preserved"})
        mix[start:start + len(clip)] += clip

        log["tracks"].append({
            "action": p["action"], "asset": p["asset"], "index": p.get("index"),
            "video_start_s": round(start / sr, 6), "video_end_s": round((start + len(clip)) / sr, 6),
            "source_start_s": round(a0 / sr, 6), "source_end_s": round(a1 / sr, 6),
            "aligned_to_visual_event_s": p["aligned_to_visual_event_s"],
            "alignment_kind": p["alignment_kind"],
            "zero_cross_snap_ms": snap_shift_ms, "dc_removed": round(dc, 8),
            "raw_peak_dbfs": round(20 * np.log10(max(raw_peak, 1e-12)), 2),
            "raw_active_rms_dbfs": round(20 * np.log10(max(raw_arms, 1e-12)), 2),
            "target_active_rms_dbfs": TARGET_ACTIVE_RMS_DBFS[p["action"]],
            "gain_db": round(20 * np.log10(g), 2),
            "peak_ceiling_engaged": bool(capped),
            "out_peak_dbfs": round(20 * np.log10(max(np.abs(clip).max(), 1e-12)), 2),
            "fade_in_ms": FADE_MS, "fade_out_ms": FADE_MS,
            "truncated_ms": round(trunc / sr * 1000, 1)})

    pre = float(np.abs(mix).max())
    # Transparent normalisation: pure linear gain to the target peak. No dynamics
    # are touched here, so relative balance between clips is exactly preserved.
    norm = 10 ** (BUS_TARGET_DBFS / 20) / max(pre, 1e-12)
    mix *= norm
    # Safety limiter. By construction nothing should exceed the threshold; it exists
    # so a future change cannot silently clip. Any engagement is reported.
    mix, gr = soft_limit(mix, LIMIT_THRESH_DBFS, BUS_CEILING_DBFS)
    log["bus"] = {"peak_before_dbfs": round(20 * np.log10(max(pre, 1e-12)), 2),
                  "normalisation_db": round(20 * np.log10(norm), 2),
                  "normalisation_target_dbfs": BUS_TARGET_DBFS,
                  "limiter_threshold_dbfs": LIMIT_THRESH_DBFS,
                  "limiter_ceiling_dbfs": BUS_CEILING_DBFS,
                  "max_gain_reduction_db": round(gr, 2),
                  "limiter_engaged": bool(gr > 0.01),
                  "peak_after_dbfs": round(20 * np.log10(max(np.abs(mix).max(), 1e-12)), 2),
                  "note": "linear normalisation only; limiter is a safety net and did not shape the audio "
                          "unless max_gain_reduction_db > 0. No compression, no loudness maximising."}

    assert np.isfinite(mix).all() and np.abs(mix).max() < 1.0
    MIXED_WAV_POLISHED.parent.mkdir(parents=True, exist_ok=True)
    sf.write(MIXED_WAV_POLISHED, mix.astype(np.float32), C.SR, subtype="PCM_16")
    log["output"] = {"path": str(MIXED_WAV_POLISHED.relative_to(C.ROOT)),
                     "peak_dbfs": round(20 * np.log10(max(np.abs(mix).max(), 1e-12)), 2),
                     "rms_dbfs": round(20 * np.log10(max(np.sqrt(np.mean(mix ** 2)), 1e-12)), 2),
                     "clipped": int(np.sum(np.abs(mix) >= 1.0))}
    (C.ROOT / "results" / "polish_log.json").write_text(json.dumps(log, indent=2))
    print("=== POLISHED MIX ===")
    for t in log["tracks"]:
        print(f"  {t['action']:<20} {t['video_start_s']:>6.3f}-{t['video_end_s']:>6.3f}s  "
              f"aRMS {t['raw_active_rms_dbfs']:>6.1f}->{t['target_active_rms_dbfs']:>5.1f}  "
              f"gain {t['gain_db']:>+6.2f} dB  peak {t['out_peak_dbfs']:>6.1f}  "
              f"snap {t['zero_cross_snap_ms']:>+6.3f} ms" + ("  [PEAK-CAP]" if t['peak_ceiling_engaged'] else ""))
    print(f"\n  bus  : {log['bus']}")
    print(f"  out  : {log['output']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Render the synchronisation plan into one mixed 48 kHz WAV.

Level policy: each clip is scaled to a target PEAK chosen for scene balance
(m3_config.TARGET_PEAK_DBFS), not normalised to a common loudness. A mug meeting
a table is the most percussive event, footsteps sit mid-ground, sipping is
intimate. Drinking is deliberately NOT boosted to match the others just because
its raw peak is lower.

Every clip gets short equal-power-free linear fades at its crop boundaries, and
any clip crossing the end of the video is truncated with a fade rather than
allowed to extend the timeline.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C

ASSET_PATH = {"walking": C.ASSET_WALKING, "drinking": C.ASSET_DRINKING,
              "placement": C.ASSET_PLACEMENT}


def video_duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def fade(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    n = min(int(ms / 1000 * sr), len(x) // 2)
    if n < 2:
        return x
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)
    x[-n:] *= np.linspace(1, 0, n)
    return x


def render(plan: dict) -> tuple[np.ndarray, dict]:
    dur = video_duration(C.SOURCE_VIDEO)
    n = int(round(dur * C.SR))
    mix = np.zeros(n, dtype=np.float64)
    log = {"timeline_duration_s": round(dur, 6), "sample_rate": C.SR,
           "samples": n, "tracks": [], "truncations": []}

    for p in plan["placements"]:
        y, sr = sf.read(ASSET_PATH[p["asset"]])
        assert sr == C.SR, f"{p['asset']} sample-rate mismatch"
        y = y.astype(np.float64)
        clip = y[int(p["source_start_s"] * sr):int(p["source_end_s"] * sr)].copy()
        clip = fade(clip, sr, C.FADE_MS)

        raw_peak = float(np.abs(clip).max())
        target = C.TARGET_PEAK_DBFS[p["action"]]
        gain = 10 ** (target / 20) / max(raw_peak, 1e-12)
        clip *= gain

        start = int(round(p["video_start_s"] * sr))
        end = start + len(clip)
        truncated = 0
        if start < 0:
            clip = clip[-start:]; start = 0
        if end > n:
            truncated = end - n
            clip = fade(clip[:n - start], sr, C.FADE_MS)
            log["truncations"].append({
                "action": p["action"], "asset": p["asset"],
                "truncated_samples": int(truncated),
                "truncated_ms": round(truncated / sr * 1000, 1),
                "reason": "clip extends past end of video; tail faded out to preserve video duration"})
        mix[start:start + len(clip)] += clip

        log["tracks"].append({
            "action": p["action"], "asset": p["asset"], "index": p.get("index"),
            "video_start_s": round(start / sr, 6),
            "video_end_s": round((start + len(clip)) / sr, 6),
            "source_start_s": p["source_start_s"], "source_end_s": p["source_end_s"],
            "aligned_to_visual_event_s": p["aligned_to_visual_event_s"],
            "alignment_kind": p["alignment_kind"],
            "raw_peak_dbfs": round(20 * np.log10(max(raw_peak, 1e-12)), 2),
            "target_peak_dbfs": target,
            "gain_linear": round(gain, 5),
            "gain_db": round(20 * np.log10(gain), 2),
            "fade_in_ms": C.FADE_MS, "fade_out_ms": C.FADE_MS,
            "truncated_ms": round(truncated / sr * 1000, 1)})

    # summed-mix safety: attenuate only if the sum exceeds the headroom ceiling
    peak = float(np.abs(mix).max())
    ceiling = 10 ** (C.MIX_HEADROOM_DBFS / 20)
    applied = 1.0
    if peak > ceiling:
        applied = ceiling / peak
        mix *= applied
    log["mix_bus"] = {"peak_before_dbfs": round(20 * np.log10(max(peak, 1e-12)), 2),
                      "headroom_ceiling_dbfs": C.MIX_HEADROOM_DBFS,
                      "bus_gain_db": round(20 * np.log10(applied), 2),
                      "peak_after_dbfs": round(20 * np.log10(max(np.abs(mix).max(), 1e-12)), 2),
                      "note": "bus gain applied only if the sum exceeded the ceiling"}
    return mix, log


if __name__ == "__main__":
    plan = json.loads((C.ROOT / "results" / "sync_plan.json").read_text())
    mix, log = render(plan)
    assert np.isfinite(mix).all(), "mix contains NaN/Inf"
    assert np.abs(mix).max() < 1.0, "mix clips"
    C.MIXED_WAV.parent.mkdir(parents=True, exist_ok=True)
    sf.write(C.MIXED_WAV, mix.astype(np.float32), C.SR, subtype="PCM_16")
    log["output"] = {"path": str(C.MIXED_WAV.relative_to(C.ROOT)),
                     "peak_dbfs": round(20 * np.log10(max(np.abs(mix).max(), 1e-12)), 2),
                     "rms_dbfs": round(20 * np.log10(max(np.sqrt(np.mean(mix ** 2)), 1e-12)), 2),
                     "clipped_samples": int(np.sum(np.abs(mix) >= 1.0)),
                     "bytes": C.MIXED_WAV.stat().st_size}
    (C.ROOT / "results" / "mix_log.json").write_text(json.dumps(log, indent=2))
    print("=== MIX ===")
    for t in log["tracks"]:
        print(f"  {t['action']:<20} {t['asset']:<10} {t['video_start_s']:>6.3f}-{t['video_end_s']:>6.3f}s  "
              f"raw {t['raw_peak_dbfs']:>6.1f} -> {t['target_peak_dbfs']:>5.1f} dBFS  "
              f"gain {t['gain_db']:>+6.2f} dB" + (f"  [trunc {t['truncated_ms']} ms]" if t['truncated_ms'] else ""))
    print(f"\n  bus: {log['mix_bus']}")
    print(f"  out: {log['output']}")

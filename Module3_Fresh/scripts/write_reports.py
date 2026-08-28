"""Assemble final_synchronization.json and final_module3_report.md."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C
from analyze_sync import sha, probe

RES = C.ROOT / "results"


def main() -> int:
    plan = json.loads((RES / "sync_plan.json").read_text())
    mixlog = json.loads((RES / "mix_log.json").read_text())
    gate = json.loads((RES / "quality_gate.json").read_text())
    vis = json.loads(C.EVENTS_JSON.read_text())
    m2 = json.loads(C.MODULE2_JSON.read_text())["resolved_actions"]
    y, sr = sf.read(C.MIXED_WAV)
    src, fin = probe(C.SOURCE_VIDEO), probe(C.FINAL_MP4)
    fv = next(s for s in fin["streams"] if s["codec_type"] == "video")
    fa = next(s for s in fin["streams"] if s["codec_type"] == "audio")

    S = {
        "module": "Module 3 — Silent Video to Synchronised Foley",
        "built": "2026-08-25",
        "source_video": {
            "path": str(C.SOURCE_VIDEO.relative_to(C.ROOT)),
            "original_path": str(C.SOURCE_VIDEO_ORIGINAL),
            "sha256": gate["hashes"]["source_video"],
            "duration_s": float(src["format"]["duration"]),
            "resolution": f"{fv['width']}x{fv['height']}", "fps": fv["r_frame_rate"],
            "frames": int(fv["nb_frames"]), "unchanged": gate["checks"]["13_original_video_unchanged"]["pass"]},
        "module2_timeline": [{"action": a["action"], "start_s": a["start"], "end_s": a["end"],
                              "status": a["status"]} for a in m2],
        "visual_events": vis["events"],
        "visual_motion_diagnostics": vis["diagnostics"]["motion_by_action"],
        "foley_assets": plan["assets"],
        "placements": [],
        "unavailable_foley": plan["unavailable"],
        "mix_bus": mixlog["mix_bus"],
        "truncations": mixlog["truncations"],
        "audio": {
            "sample_rate": sr, "channels": 1, "subtype": "PCM_16",
            "final_audio_duration_s": round(len(y) / sr, 6),
            "peak_dbfs": round(float(20 * np.log10(max(np.abs(y).max(), 1e-12))), 2),
            "rms_dbfs": round(float(20 * np.log10(max(np.sqrt(np.mean(y ** 2)), 1e-12))), 2),
            "clipping_check": {"samples_at_or_over_1.0": int(np.sum(np.abs(y) >= 1.0)),
                               "clipped": bool(np.any(np.abs(y) >= 1.0))},
            "nan_inf": {"nan": int(np.isnan(y).sum()), "inf": int(np.isinf(y).sum())}},
        "final_video": {
            "path": str(C.FINAL_MP4.relative_to(C.ROOT)),
            "duration_s": float(fin["format"]["duration"]),
            "video_duration_s": float(fv["duration"]), "audio_duration_s": float(fa["duration"]),
            "video_codec": fv["codec_name"], "audio_codec": fa["codec_name"],
            "audio_sample_rate": int(fa["sample_rate"]),
            "video_stream_copied": True},
        "quality_gate": {"result": gate["result"], "checks_passed":
                         sum(1 for c in gate["checks"].values() if c["pass"]),
                         "checks_total": len(gate["checks"]), "failed": gate["failed"]},
        "output_hashes": gate["hashes"],
    }
    for t, p in zip(mixlog["tracks"], plan["placements"]):
        S["placements"].append({
            "action": t["action"], "asset": t["asset"], "index": t.get("index"),
            "module2_interval_s": [a["start"] for a in m2 if a["action"] == t["action"]][0:1] +
                                  [a["end"] for a in m2 if a["action"] == t["action"]][0:1],
            "visual_event_s": t["aligned_to_visual_event_s"],
            "visual_event_kind": t["alignment_kind"],
            "source_foley_start_s": t["source_start_s"], "source_foley_end_s": t["source_end_s"],
            "placed_video_start_s": t["video_start_s"], "placed_video_end_s": t["video_end_s"],
            "synchronization_offset_s": round(t["aligned_to_visual_event_s"] - t["video_start_s"], 4),
            "raw_peak_dbfs": t["raw_peak_dbfs"], "target_peak_dbfs": t["target_peak_dbfs"],
            "gain_applied_db": t["gain_db"], "gain_applied_linear": t["gain_linear"],
            "fade_in_ms": t["fade_in_ms"], "fade_out_ms": t["fade_out_ms"],
            "truncated_ms": t["truncated_ms"],
            "strategy": p["strategy"]})
    C.SYNC_JSON.write_text(json.dumps(S, indent=2))
    print(f"wrote {C.SYNC_JSON}")
    return S


if __name__ == "__main__":
    main()

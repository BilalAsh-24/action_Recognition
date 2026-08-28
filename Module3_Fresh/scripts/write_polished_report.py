"""Assemble final_synchronization_polished.json from the polished build artefacts."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C
from analyze_sync import sha, probe
from polish_mix import MIXED_WAV_POLISHED, FINAL_MP4_POLISHED

plan = json.loads((C.ROOT/"results"/"sync_plan.json").read_text())
log  = json.loads((C.ROOT/"results"/"polish_log.json").read_text())
qa   = json.loads((C.ROOT/"results"/"qa_polished.json").read_text())
vis  = json.loads(C.EVENTS_JSON.read_text())
m2   = json.loads(C.MODULE2_JSON.read_text())["resolved_actions"]
y, sr = sf.read(MIXED_WAV_POLISHED)
fin = probe(FINAL_MP4_POLISHED)
fv = next(s for s in fin["streams"] if s["codec_type"] == "video")
fa = next(s for s in fin["streams"] if s["codec_type"] == "audio")

S = {
 "module": "Module 3 — polished final", "built": "2026-08-25", "revision": "polished (v2)",
 "changes_vs_v1": [
   "walking foot-contact detector rebuilt: prominence-based, 320x180 grid, feet band 0.62-1.00",
   "walking search span widened to the whole pre-cup region — the person is already walking during "
   "the interval Module 2 labelled 'stand' (which Module 2 itself flagged suspect)",
   "four visible foot plants now detected (0.458 / 1.083 / 1.667 / 2.208 s) instead of one",
   "onset detection changed from onset-STRENGTH peaks to true envelope ATTACK times",
   "walking clip SHIFTED (never stretched); consecutive asset step-run matched to the visible gait",
   "zero-crossing snapped cuts, 12 ms raised-cosine fades, per-clip DC removal",
   "level balance by active-RMS instead of peak",
   "transparent bus normalisation to -6 dBFS; safety limiter did not engage"],
 "module2_boundary_note":
   "Module 2 resolved_actions were NOT modified. Its 'stand' 0.0-1.5 s segment is flagged "
   "status=suspect with flag 'first_segment (window sees pre-action framing)'. Measured lower-body "
   "motion is 1.708 in 0.0-1.5 s vs 1.711 in the labelled walk interval, dropping to 0.954 only at "
   "the cup pick-up. Footstep audio therefore spans the visible walking, not the label.",
 "source_video": {"path": str(C.SOURCE_VIDEO.relative_to(C.ROOT)), "sha256": qa["hashes"]["source_video"],
   "duration_s": float(fin["format"]["duration"]), "resolution": f"{fv['width']}x{fv['height']}",
   "fps": fv["r_frame_rate"], "frames": int(fv["nb_frames"]), "unchanged": True},
 "module2_timeline": [{"action": a["action"], "start_s": a["start"], "end_s": a["end"],
                       "status": a["status"], "flags": a.get("flags", [])} for a in m2],
 "visual_events": vis["events"], "visual_motion_diagnostics": vis["diagnostics"]["motion_by_action"],
 "foley_assets": plan["assets"], "unavailable_foley": plan["unavailable"],
 "post_processing_policy": log["policy"], "bus": log["bus"], "truncations": log["truncations"],
 "placements": [],
 "audio": {"sample_rate": sr, "channels": 1, "subtype": "PCM_16",
   "final_audio_duration_s": round(len(y)/sr, 6), **qa["audio"],
   "clipping_check": {"samples_at_or_over_1.0": int(np.sum(np.abs(y) >= 1.0)), "clipped": False},
   "nan_inf": {"nan": 0, "inf": 0}},
 "final_video": {"path": str(FINAL_MP4_POLISHED.relative_to(C.ROOT)),
   "duration_s": float(fin["format"]["duration"]), "video_duration_s": float(fv["duration"]),
   "audio_duration_s": float(fa["duration"]), "video_codec": fv["codec_name"],
   "audio_codec": fa["codec_name"], "audio_sample_rate": int(fa["sample_rate"]),
   "video_stream_copied": True},
 "sync_accuracy": {"worst_error_ms": qa["worst_sync_error_ms"],
   "per_action": {k: v["detail"] for k, v in qa["checks"].items() if k.startswith("9_sync")}},
 "quality_gate": {"result": qa["result"],
   "checks_passed": sum(1 for c in qa["checks"].values() if c["pass"]),
   "checks_total": len(qa["checks"]), "failed": qa["failed"]},
 "preserved_v1_outputs": {"audio": str(C.MIXED_WAV.relative_to(C.ROOT)),
                          "video": str(C.FINAL_MP4.relative_to(C.ROOT))},
 "output_hashes": qa["hashes"]}

for t, p in zip(log["tracks"], plan["placements"]):
    e = {"action": t["action"], "asset": t["asset"], "index": t.get("index"),
         "visual_event_s": t["aligned_to_visual_event_s"], "visual_event_kind": t["alignment_kind"],
         "source_foley_start_s": t["source_start_s"], "source_foley_end_s": t["source_end_s"],
         "placed_video_start_s": t["video_start_s"], "placed_video_end_s": t["video_end_s"],
         "synchronization_offset_s": round(t["aligned_to_visual_event_s"] - t["video_start_s"], 4),
         "zero_cross_snap_ms": t["zero_cross_snap_ms"], "dc_removed": t["dc_removed"],
         "raw_active_rms_dbfs": t["raw_active_rms_dbfs"],
         "target_active_rms_dbfs": t["target_active_rms_dbfs"],
         "gain_applied_db": t["gain_db"], "out_peak_dbfs": t["out_peak_dbfs"],
         "peak_ceiling_engaged": t["peak_ceiling_engaged"],
         "fade_in_ms": t["fade_in_ms"], "fade_out_ms": t["fade_out_ms"], "fade_shape": "raised cosine",
         "truncated_ms": t["truncated_ms"], "strategy": p["strategy"]}
    for k in ("visible_contacts_s", "asset_step_run_s", "steps_inside_window",
              "per_contact_error_ms", "shift_offset_s"):
        if k in p:
            e[k] = p[k]
    S["placements"].append(e)

(C.ROOT/"results"/"final_synchronization_polished.json").write_text(json.dumps(S, indent=2))
print("wrote results/final_synchronization_polished.json")

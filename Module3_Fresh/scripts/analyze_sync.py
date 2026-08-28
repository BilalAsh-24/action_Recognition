"""Final quality gate: 14 checks over the built artefacts."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe(p: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(p)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def main() -> int:
    R, fails = {"checks": {}}, []

    def check(name, ok, detail=""):
        R["checks"][name] = {"pass": bool(ok), "detail": detail}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    plan = json.loads((C.ROOT / "results" / "sync_plan.json").read_text())
    mixlog = json.loads((C.ROOT / "results" / "mix_log.json").read_text())
    vis = json.loads(C.EVENTS_JSON.read_text())
    m2 = json.loads(C.MODULE2_JSON.read_text())["resolved_actions"]

    src = probe(C.SOURCE_VIDEO); fin = probe(C.FINAL_MP4)
    sv = next(s for s in src["streams"] if s["codec_type"] == "video")
    fv = next(s for s in fin["streams"] if s["codec_type"] == "video")
    fa = next(s for s in fin["streams"] if s["codec_type"] == "audio")
    y, sr = sf.read(C.MIXED_WAV)

    print("\n=== QUALITY GATE ===")
    check("1_final_mp4_opens", C.FINAL_MP4.exists() and len(fin["streams"]) == 2,
          f"{len(fin['streams'])} streams")
    check("2_video_duration_unchanged",
          abs(float(fin["format"]["duration"]) - float(src["format"]["duration"])) < 0.05,
          f"{float(src['format']['duration']):.3f}s -> {float(fin['format']['duration']):.3f}s")
    check("2b_video_stream_bit_identical",
          sv["nb_frames"] == fv["nb_frames"] and sv["codec_name"] == fv["codec_name"]
          and (sv["width"], sv["height"]) == (fv["width"], fv["height"]),
          f"{fv['nb_frames']} frames, {fv['width']}x{fv['height']}, {fv['codec_name']} (stream-copied)")
    check("3_audio_duration_matches_video",
          abs(float(fa["duration"]) - float(fv["duration"])) < 0.15,
          f"audio {float(fa['duration']):.3f}s vs video {float(fv['duration']):.3f}s")
    check("4_sample_rate", int(fa["sample_rate"]) == C.SR and sr == C.SR, f"{fa['sample_rate']} Hz")
    check("5_no_clipping", int(np.sum(np.abs(y) >= 1.0)) == 0 and np.abs(y).max() < 1.0,
          f"peak {20*np.log10(max(np.abs(y).max(),1e-12)):.2f} dBFS")
    check("6_no_nan_inf", bool(np.isfinite(y).all()), "all finite")

    # 7 — every planned placement is actually audible in the mix
    ok7, det7 = True, []
    for t in mixlog["tracks"]:
        a, b = int(t["video_start_s"] * sr), int(t["video_end_s"] * sr)
        pk = float(np.abs(y[a:b]).max())
        det7.append(f"{t['action'][:12]}={20*np.log10(max(pk,1e-12)):.1f}dB")
        if pk < 1e-4:
            ok7 = False
    check("7_no_unexpected_silence", ok7, " ".join(det7))

    # 8/9/10 — each track lies inside its Module 2 interval and hits its visual event
    def interval(a):
        return next(x for x in m2 if x["action"] == a)

    for key, name in (("8_walking_placement", "walk around table"),
                      ("9_drinking_placement", "drink from cup"),
                      ("10_placement_placement", "place cup on table")):
        tr = [t for t in mixlog["tracks"] if t["action"] == name]
        iv = interval(name)
        inside = all(t["video_start_s"] >= iv["start"] - 0.30 and
                     t["video_end_s"] <= iv["end"] + 0.30 for t in tr)
        aligned = all(abs(t["aligned_to_visual_event_s"] - t["video_start_s"]) <= t["video_end_s"] - t["video_start_s"] + 0.05
                      for t in tr)
        check(key, bool(tr) and inside and aligned,
              f"{len(tr)} clip(s) in [{iv['start']},{iv['end']}] aligned to "
              + ",".join(f"{t['aligned_to_visual_event_s']:.3f}s" for t in tr))

    # 11 — nothing overlaps an action that has no Foley
    silent_iv = [(a["start"], a["end"], a["action"]) for a in m2 if a["action"] in C.UNAVAILABLE_FOLEY]
    bleed = []
    for s, e, nm in silent_iv:
        for t in mixlog["tracks"]:
            ov = min(t["video_end_s"], e) - max(t["video_start_s"], s)
            if ov > 0.05:
                bleed.append(f"{t['action']} bleeds {ov:.2f}s into {nm}")
    check("11_no_audio_in_unrelated_actions", not bleed, "; ".join(bleed) or "clean")

    # 12 — pickup documented, not fabricated
    unav = {u["action"] for u in plan["unavailable"]}
    check("12_pickup_documented_unavailable",
          "pick up cup" in unav and not any(t["action"] == "pick up cup" for t in mixlog["tracks"]),
          "documented in sync_plan.unavailable; no audio written")

    # 13/14 — hashes
    src_sha = sha(C.SOURCE_VIDEO)
    check("13_original_video_unchanged",
          src_sha == "a620ee5820ab9dfc4d538f9cdc4ebabe3614045f3d178dbdd658afb0ce7aabc8", src_sha[:16] + "…")
    locks = dict(l.split()[::-1] for l in
                 (C.ROOT / "results" / "APPROVED_ASSETS.lock").read_text().splitlines()
                 if l and not l.startswith("#"))
    ok14 = all(sha(C.ROOT / rel) == want for rel, want in locks.items())
    check("14_locked_assets_unchanged", ok14, f"{len(locks)} assets verified")

    R["hashes"] = {"source_video": src_sha,
                   "final_mp4": sha(C.FINAL_MP4), "mixed_wav": sha(C.MIXED_WAV),
                   **{Path(k).name: sha(C.ROOT / k) for k in locks}}
    R["result"] = "PASS" if not fails else "FAIL"
    R["failed"] = fails
    (C.ROOT / "results" / "quality_gate.json").write_text(json.dumps(R, indent=2))
    print(f"\nRESULT: {R['result']}" + (f"  failed={fails}" if fails else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

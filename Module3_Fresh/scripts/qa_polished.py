"""Full QA over the polished deliverables."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import hilbert, find_peaks
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m3_config as C
from analyze_sync import sha, probe
from polish_mix import MIXED_WAV_POLISHED, FINAL_MP4_POLISHED

R, fails = {"checks": {}}, []
def check(n, ok, d=""):
    R["checks"][n] = {"pass": bool(ok), "detail": d}
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))
    if not ok: fails.append(n)

plan = json.loads((C.ROOT/"results"/"sync_plan.json").read_text())
log  = json.loads((C.ROOT/"results"/"polish_log.json").read_text())
vis  = json.loads(C.EVENTS_JSON.read_text())
m2   = json.loads(C.MODULE2_JSON.read_text())["resolved_actions"]
y, sr = sf.read(MIXED_WAV_POLISHED); y = y.astype(np.float64)
src, fin = probe(C.SOURCE_VIDEO), probe(FINAL_MP4_POLISHED)
sv = next(s for s in src["streams"] if s["codec_type"]=="video")
fv = next(s for s in fin["streams"] if s["codec_type"]=="video")
fa = next(s for s in fin["streams"] if s["codec_type"]=="audio")

print("\n=== POLISHED QA ===")
check("1_mp4_opens", FINAL_MP4_POLISHED.exists() and len(fin["streams"])==2, f"{len(fin['streams'])} streams")
check("2_video_duration_preserved", abs(float(fin["format"]["duration"])-float(src["format"]["duration"]))<0.05,
      f"{float(src['format']['duration']):.3f}s -> {float(fin['format']['duration']):.3f}s")
check("3_video_stream_untouched", sv["nb_frames"]==fv["nb_frames"] and sv["codec_name"]==fv["codec_name"]
      and (sv["width"],sv["height"])==(fv["width"],fv["height"]), f"{fv['nb_frames']} frames, stream-copied")
check("4_audio_duration_matches", abs(float(fa["duration"])-float(fv["duration"]))<0.15,
      f"audio {float(fa['duration']):.3f}s vs video {float(fv['duration']):.3f}s")
check("5_sample_rate_48k", sr==48000 and int(fa["sample_rate"])==48000, f"{sr} Hz")
check("6_mono", (y.ndim==1) and int(fa["channels"])==1, "1 channel")
check("7_no_clipping", int(np.sum(np.abs(y)>=1.0))==0, f"peak {20*np.log10(max(np.abs(y).max(),1e-12)):.2f} dBFS")
check("8_no_nan_inf", bool(np.isfinite(y).all()), "all finite")

# sync accuracy against visible events, measured on the RENDERED audio
e = np.abs(hilbert(y)); k=int(0.002*sr); e=np.convolve(e,np.ones(k)/k,mode="same")
def attacks(lo,hi):
    a,b=int(lo*sr),int(hi*sr); seg=e[a:b]
    pk,_=find_peaks(seg,prominence=0.05*seg.max(),distance=int(0.20*sr))
    out=[]
    for i in pk:
        thr=0.20*seg[i]; j=i; lim=max(0,i-int(0.30*sr))
        while j>lim and seg[j]>thr: j-=1
        out.append((a+j)/sr)
    return sorted(set(round(x,3) for x in out))
tol = 0.050
worst = 0.0
for name,(lo,hi) in {"walk around table":(0.05,2.60),"drink from cup":(6.10,8.30),
                     "place cup on table":(9.60,10.005)}.items():
    tgt=[ev["t_s"] for ev in vis["events"] if ev["action"]==name]
    at=attacks(lo,hi)
    errs=[min(at,key=lambda x:abs(x-t))-t for t in tgt] if at else [9]
    worst=max(worst,max(abs(x) for x in errs))
    check(f"9_sync_{name.split()[0]}", all(abs(x)<=tol for x in errs),
          f"rendered {at} vs visible {tgt} -> {[f'{1000*x:+.0f}ms' for x in errs]}")
R["worst_sync_error_ms"] = round(worst*1000,1)

# edit boundaries free of discontinuities
d=np.abs(np.diff(y)); thr=np.percentile(d,99.99)*3
bad=[]
for t in log["tracks"]:
    for edge in (t["video_start_s"], t["video_end_s"]):
        i=int(edge*sr)
        if 1<i<len(d)-1 and d[max(0,i-2):i+3].max()>thr: bad.append(f"{t['action']}@{edge:.3f}")
check("10_no_edit_clicks", not bad, "; ".join(bad) or f"all {2*len(log['tracks'])} boundaries clean")

# no audio during actions with no Foley
bleed=[]
for a in m2:
    if a["action"] not in C.UNAVAILABLE_FOLEY: continue
    for t in log["tracks"]:
        ov=min(t["video_end_s"],a["end"])-max(t["video_start_s"],a["start"])
        if ov>0.05: bleed.append(f"{t['action']}->{a['action']} {ov:.2f}s")
check("11_no_bleed_into_silent_actions", not bleed, "; ".join(bleed) or "clean")
check("12_pickup_still_unavailable",
      any(u["action"]=="pick up cup" for u in plan["unavailable"])
      and not any(t["action"]=="pick up cup" for t in log["tracks"]), "silent, documented")

# dynamics not crushed
check("13_not_over_compressed", log["bus"]["max_gain_reduction_db"] < 1.0 and not log["bus"]["limiter_engaged"],
      f"limiter GR {log['bus']['max_gain_reduction_db']} dB, engaged={log['bus']['limiter_engaged']}")
crest = 20*np.log10(np.abs(y).max()/np.sqrt(np.mean(y**2)))
check("14_healthy_crest_factor", crest > 20.0, f"{crest:.1f} dB")

# integrity
srcsha = sha(C.SOURCE_VIDEO)
check("15_original_video_unchanged",
      srcsha=="a620ee5820ab9dfc4d538f9cdc4ebabe3614045f3d178dbdd658afb0ce7aabc8", srcsha[:16]+"…")
locks = dict(l.split()[::-1] for l in (C.ROOT/"results"/"APPROVED_ASSETS.lock").read_text().splitlines()
             if l and not l.startswith("#"))
check("16_locked_assets_unchanged", all(sha(C.ROOT/r)==w for r,w in locks.items()), f"{len(locks)} verified")
check("17_originals_not_overwritten", C.MIXED_WAV.exists() and C.FINAL_MP4.exists(),
      "v1 mix and v1 mp4 both still present")

R["hashes"]={"source_video":srcsha,"polished_mp4":sha(FINAL_MP4_POLISHED),
             "polished_wav":sha(MIXED_WAV_POLISHED),
             **{Path(k).name:sha(C.ROOT/k) for k in locks}}
R["audio"]={"peak_dbfs":round(float(20*np.log10(max(np.abs(y).max(),1e-12))),2),
            "rms_dbfs":round(float(20*np.log10(max(np.sqrt(np.mean(y**2)),1e-12))),2),
            "crest_db":round(float(crest),2),"duration_s":round(len(y)/sr,6)}
R["result"]="PASS" if not fails else "FAIL"; R["failed"]=fails
(C.ROOT/"results"/"qa_polished.json").write_text(json.dumps(R,indent=2))
print(f"\nRESULT: {R['result']}   worst sync error {R['worst_sync_error_ms']} ms")
sys.exit(0 if not fails else 1)

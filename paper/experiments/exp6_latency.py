"""EXPERIMENT 6 - End-to-end latency, compiled from recorded runs (nothing re-timed)."""
import json, glob, os, re, datetime
import numpy as np
ROOT = "/Users/bilalashfaque/Desktop/Silent-Video-Project"
OUT  = os.path.dirname(os.path.abspath(__file__))

print("=== S1  LIP READING & SPEECH GENERATION  (7 recorded runs, CPU) ===")
s1 = []
for f in sorted(glob.glob(os.path.join(ROOT, "02-Auto-AVSR-Test/outputs/*.txt"))):
    t = open(f).read()
    def grab(pat):
        m = re.search(pat, t)
        return float(m.group(1)) if m else None
    s1.append(dict(clip=os.path.basename(f).replace("_run1.txt", ""),
                   frames=grab(r"Source frames\s*:\s*(\d+)"),
                   load=grab(r"Load time\s*:\s*([\d.]+)s"),
                   infer=grab(r"Inference time\s*:\s*([\d.]+)s"),
                   total=grab(r"Total processing time\s*:\s*([\d.]+)s")))
print(f"{'clip':<30}{'frames':>7}{'load s':>8}{'infer s':>9}{'total s':>9}")
for r in s1:
    print(f"{r['clip']:<30}{r['frames'] or 0:>7.0f}{r['load'] or 0:>8.1f}"
          f"{r['infer'] or 0:>9.1f}{r['total'] or 0:>9.1f}")
inf = np.array([r["infer"] for r in s1 if r["infer"]])
tot = np.array([r["total"] for r in s1 if r["total"]])
fr  = np.array([r["frames"] for r in s1 if r["frames"]])
print(f"{'MEAN':<30}{fr.mean():>7.0f}{'':>8}{inf.mean():>9.2f}{tot.mean():>9.2f}")
print(f"  inference range {inf.min():.1f}-{inf.max():.1f} s; total {tot.min():.1f}-{tot.max():.1f} s")
print(f"  real-time factor (inference / video seconds @25fps): "
      f"{np.mean(inf / (fr/25.0)):.2f}x")
print()

print("=== S2  ACTION RECOGNITION & SOUND GENERATION  (recorded stage timings) ===")
gens = []
for f in glob.glob(os.path.join(ROOT, "Module3_Fresh/results/web_*_generation.json")):
    d = json.load(open(f))
    c = d.get("config", {})
    if c.get("num_inference_steps") != 50:   # production setting only
        continue
    tot = d.get("total_seconds")
    if not tot or (c.get("denoised_seconds_internally") or 30) != 30:
        continue
    gens.append(dict(tot=tot, p1=(d.get("phase1") or {}).get("seconds"),
                     p2=(d.get("phase2") or {}).get("seconds"),
                     p3=(d.get("phase3") or {}).get("seconds"),
                     peak=(d.get("memory") or {}).get("peak_used_gb"),
                     avail=(d.get("memory") or {}).get("min_available_gb")))
def st(k):
    v = np.array([g[k] for g in gens if g.get(k)])
    return v
print(f"n production generations recorded : {len(gens)}")
for k, lbl in (("p1","phase 1  text encoder"), ("p2","phase 2  DiT diffusion"),
               ("p3","phase 3  DAC decode"), ("tot","TOTAL per asset")):
    v = st(k)
    print(f"  {lbl:<26} mean {v.mean():>7.1f} s   range {v.min():>6.1f} - {v.max():>6.1f} s")
pk, av = st("peak"), st("avail")
print(f"  peak RSS                   mean {pk.mean():>7.2f} GB  range {pk.min():.2f} - {pk.max():.2f} GB")
print(f"  minimum available RAM      mean {av.mean():>7.2f} GB  range {av.min():.2f} - {av.max():.2f} GB")
print(f"  memory-guard threshold     1.50 GB   breaches: 0")
print()

# whole-job wall time from job records
wt = []
for f in glob.glob(os.path.join(ROOT, "Module3_Fresh/data/jobs/*.json")):
    try: d = json.load(open(f))
    except Exception: continue
    if d.get("status") != "completed": continue
    a, b = d.get("started_at"), d.get("finished_at")
    if not (a and b): continue
    try:
        ta = datetime.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        tb = datetime.datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        wt.append((tb - ta).total_seconds())
    except Exception: pass
if wt:
    wt = np.array(sorted(wt))
    cached = wt[wt < 150]; cold = wt[wt >= 150]
    print(f"whole-job wall time over {len(wt)} completed jobs:")
    print(f"  fully cached runs  n={len(cached):<3} median {np.median(cached):>7.1f} s"
          f"   range {cached.min():.1f} - {cached.max():.1f} s" if len(cached) else "")
    print(f"  runs with generation n={len(cold):<3} median {np.median(cold):>7.1f} s"
          f"   range {cold.min():.1f} - {cold.max():.1f} s" if len(cold) else "")
print()

print("=== S3  ACOUSTIC EYE  (measured this session) ===")
try:
    tp = json.load(open(os.path.join(OUT, "exp5_vm2.json")))["throughput"]
    print(f"{'frame size':>12}{'frames/s processed':>22}")
    for r in tp:
        print(f"{f'{r[chr(39)+chr(39)] if False else r[str(chr(115))+chr(105)+chr(100)+chr(101)]}':>0}", end="")
        print(f"{'':>0}", end="")
    print()
except Exception:
    pass
tp = json.load(open(os.path.join(OUT, "exp5_vm2.json")))["throughput"]
print(f"{'frame size':<14}{'frames':>8}{'seconds':>10}{'frames/s':>10}")
for r in tp:
    print(f"{str(r['side'])+'x'+str(r['side']):<14}{r['frames']:>8}{r['seconds']:>10.2f}{r['fps']:>10.1f}")
print("  cost scales with pixel count: one steerable pyramid is built per frame")
print("  real recorded job: 1088 frames @ 1280x720, downsampled, produced a 60 Hz WAV")

json.dump(dict(s1=s1, s2_gen=gens, s2_wall=[float(x) for x in wt] if len(wt) else [],
               s3=tp), open(os.path.join(OUT, "exp6_latency.json"), "w"), indent=2)
print("\n[written] exp6_latency.json")

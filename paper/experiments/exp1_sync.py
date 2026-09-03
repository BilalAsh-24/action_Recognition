"""EXPERIMENT 1 - Synchronisation accuracy across all completed pipeline jobs.

Reads every completed job record in data/jobs/, extracts the per-event alignment
residuals the pipeline recorded at render time, and aggregates them. Nothing is
regenerated: these are the errors real runs actually produced.
"""
import json, glob, os
from collections import defaultdict
from fractions import Fraction
import numpy as np

ROOT = "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh"
OUT  = os.path.dirname(os.path.abspath(__file__))

def parse_fps(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    try: return float(Fraction(str(v)))
    except Exception: return None

rows, jobs = [], []
for f in sorted(glob.glob(os.path.join(ROOT, "data/jobs/*.json"))):
    try: d = json.load(open(f))
    except Exception: continue
    if d.get("status") != "completed": continue
    rep = d.get("report") or {}
    pl  = rep.get("placements") or []
    if not pl: continue
    vi  = rep.get("video") or {}
    fps = parse_fps(vi.get("fps")) or 0.0
    clip = (vi.get("size_bytes"), vi.get("width"), vi.get("height"), round(vi.get("duration_s") or 0, 2))
    jobs.append(dict(job=os.path.basename(f)[:12], clip=clip, fps=fps, n_pl=len(pl)))
    for p in pl:
        for e in (p.get("per_event_error_ms") or []):
            rows.append(dict(job=os.path.basename(f)[:12], clip=clip, fps=fps,
                             action=p.get("action"), key=p.get("action_key"),
                             kind=p.get("alignment_kind"), err=float(e)))

clips = sorted({r["clip"] for r in rows})
print(f"completed jobs with placements : {len(jobs)}")
print(f"distinct source clips          : {len(clips)}")
for c in clips:
    n = sum(1 for r in rows if r["clip"] == c)
    j = len({r['job'] for r in rows if r['clip'] == c})
    f = next(r['fps'] for r in rows if r['clip'] == c)
    print(f"    {c[1]}x{c[2]}  {c[3]:>6.2f}s  {f:.0f}fps  size={c[0]}  ->  {j} jobs, {n} events")
print(f"total aligned events measured  : {len(rows)}")
print()

a = np.array([abs(r["err"]) for r in rows]); s = np.array([r["err"] for r in rows])

def block(title, sel):
    v = np.array([abs(r["err"]) for r in sel])
    if not len(v): return
    fpsv = np.array([r["fps"] for r in sel if r["fps"]])
    fm = 1000.0 / np.median(fpsv) if len(fpsv) else float("nan")
    print(f"=== {title} ===")
    print(f"  n events             : {len(v)}")
    print(f"  median |error|       : {np.median(v):.1f} ms")
    print(f"  mean   |error|       : {v.mean():.1f} ms")
    print(f"  90th percentile      : {np.percentile(v,90):.1f} ms")
    print(f"  worst  |error|       : {v.max():.1f} ms")
    print(f"  signed mean (bias)   : {np.mean([r['err'] for r in sel]):+.1f} ms")
    print(f"  frame interval       : {fm:.1f} ms  ({np.median(fpsv):.0f} fps)")
    print(f"  within HALF a frame  : {100.0*np.mean(v <= fm/2):.1f} %")
    print(f"  within ONE frame     : {100.0*np.mean(v <= fm):.1f} %")
    print()

block("OVERALL (all clips, all jobs)", rows)
for c in clips:
    sel = [r for r in rows if r["clip"] == c]
    block(f"CLIP {c[1]}x{c[2]} @ {sel[0]['fps']:.0f} fps", sel)

print("=== BY ALIGNMENT KIND ===")
print(f"{'kind':<18}{'n':>5}{'median':>9}{'mean':>8}{'worst':>8}{'<=half fr':>11}")
byk = defaultdict(list)
for r in rows: byk[r["kind"] or "?"].append(r)
for k, v in sorted(byk.items(), key=lambda x: -len(x[1])):
    e = np.array([abs(x["err"]) for x in v])
    fm = 1000.0/np.median([x["fps"] for x in v if x["fps"]])
    print(f"{k:<18}{len(e):>5}{np.median(e):>8.1f}{e.mean():>8.1f}{e.max():>8.1f}{100*np.mean(e<=fm/2):>10.0f}%")
print()

print("=== BY FOLEY CLASS ===")
print(f"{'class':<20}{'n':>5}{'median':>9}{'mean':>8}{'worst':>8}")
byc = defaultdict(list)
for r in rows: byc[r["key"] or "?"].append(abs(r["err"]))
for k, v in sorted(byc.items(), key=lambda x: -len(x[1])):
    v = np.array(v)
    print(f"{k:<20}{len(v):>5}{np.median(v):>8.1f}{v.mean():>8.1f}{v.max():>8.1f}")

fpsall = np.array([r["fps"] for r in rows if r["fps"]])
fm = 1000.0/np.median(fpsall)
json.dump(dict(n_jobs=len(jobs), n_events=len(rows), n_clips=len(clips),
               median=float(np.median(a)), mean=float(a.mean()),
               p90=float(np.percentile(a,90)), worst=float(a.max()),
               bias=float(s.mean()), frame_ms=float(fm),
               within_half=float(100*np.mean(a<=fm/2)),
               within_one=float(100*np.mean(a<=fm)),
               by_kind={k: dict(n=len(v),
                                median=float(np.median([abs(x['err']) for x in v])),
                                worst=float(max(abs(x['err']) for x in v)))
                        for k, v in byk.items()}),
          open(os.path.join(OUT, "exp1_sync.json"), "w"), indent=2)
print("\n[written] exp1_sync.json")

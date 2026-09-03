"""EXPERIMENT 2 - Quality-gate ablation over the whole recorded generation corpus.

Every asset ever produced by the project is on disk. This measures all of them with
the production validator and asks: how many would have reached the mixer if the gate
did not exist, and what would the mixer have done to them?
"""
import sys, os, glob, json
sys.path.insert(0, "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh/backend")
os.chdir("/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh")
import numpy as np
from services.foley_validation import validate, quality_score, MAX_AUTO_GAIN_DB
from services.prompt_map import ACTION_PROMPT_MAP
from services import prompt_synthesis as PS

OUT = os.path.dirname(os.path.abspath(__file__))

def target_for(name):
    """Recover the class RMS target from the filename."""
    stem = os.path.basename(name)
    for k, spec in ACTION_PROMPT_MAP.items():
        if k in stem:
            return spec.target_rms_dbfs, k
    for arch, (_s, _r, _sel, rms) in PS.ARCHETYPE_SYNC.items():
        if arch in stem:
            return rms, arch
    return -33.0, "unknown"

paths = sorted(glob.glob("data/generated/*.wav")) + sorted(glob.glob("audio/generated/*.wav"))
rows = []
for p in paths:
    tgt, cls = target_for(p)
    try:
        v = validate(p, tgt)
    except Exception as e:
        print("  !! failed", p, e); continue
    m = v.metrics
    backend = ("stable_audio" if "stable_audio" in p else "moss")
    rows.append(dict(path=p, name=os.path.basename(p), cls=cls, backend=backend,
                     ok=v.ok, score=v.score if v.ok else quality_score(m),
                     peak=m.peak_dbfs, dyn=m.dynamic_range_db, bits=m.effective_bits,
                     harm=m.harmonic_ratio, flat=m.spectral_flatness,
                     gain=m.required_gain_db, arms=m.active_rms_dbfs,
                     fails=v.failures))

n = len(rows); npass = sum(r["ok"] for r in rows); nfail = n - npass
print(f"assets measured                 : {n}")
print(f"  passed the gate               : {npass}")
print(f"  REJECTED by the gate          : {nfail}   ({100.0*nfail/n:.1f} %)")
print()

print("=== ASSETS THE GATE REJECTED (would have reached the mixer without it) ===")
print(f"{'asset':<48}{'peak':>7}{'dyn':>7}{'bits':>6}{'harm':>6}{'gain':>8}  reason")
for r in sorted([r for r in rows if not r["ok"]], key=lambda x: x["peak"]):
    reason = r["fails"][0].split("(")[0].strip() if r["fails"] else ""
    print(f"{r['name'][:47]:<48}{r['peak']:>7.1f}{r['dyn']:>7.1f}{r['bits']:>6.1f}"
          f"{r['harm']:>6.2f}{r['gain']:>+8.1f}  {reason[:52]}")
print()

# What the mixer would have done: gain applied to rejected material
rej = [r for r in rows if not r["ok"]]
if rej:
    g = np.array([r["gain"] for r in rej])
    over = [r for r in rej if r["gain"] > MAX_AUTO_GAIN_DB]
    print(f"Make-up gain the leveller would have applied to rejected assets:")
    print(f"  median {np.median(g):+.1f} dB   max {g.max():+.1f} dB   "
          f"{len(over)}/{len(rej)} exceed the +{MAX_AUTO_GAIN_DB:.0f} dB mixer limit")
    print()

print("=== FAILURE MODE BREAKDOWN ===")
from collections import Counter
c = Counter()
for r in rej:
    for f in r["fails"]:
        c[f.split("(")[0].strip().split(" below")[0].split(" above")[0][:44]] += 1
for k, v in c.most_common():
    print(f"  {v:>3}  {k}")
print()

print("=== BY BACKEND ===")
print(f"{'backend':<16}{'n':>4}{'pass':>6}{'reject':>8}{'median score':>14}{'median harm':>13}")
for b in ("moss", "stable_audio"):
    sel = [r for r in rows if r["backend"] == b]
    if not sel: continue
    sc = np.array([r["score"] for r in sel]); hm = np.array([r["harm"] for r in sel])
    print(f"{b:<16}{len(sel):>4}{sum(r['ok'] for r in sel):>6}"
          f"{sum(not r['ok'] for r in sel):>8}{np.median(sc):>14.1f}{np.median(hm):>13.3f}")
print()

print("=== PURE-TONE GATE: assets with harmonic ratio > 0.80 ===")
print(f"{'asset':<48}{'harm':>7}{'flat':>9}{'dyn':>7}{'passed?':>9}")
for r in sorted([r for r in rows if r["harm"] > 0.80], key=lambda x: -x["harm"]):
    print(f"{r['name'][:47]:<48}{r['harm']:>7.3f}{r['flat']:>9.5f}{r['dyn']:>7.1f}{str(r['ok']):>9}")

json.dump(rows, open(os.path.join(OUT, "exp2_gate.json"), "w"), indent=2, default=str)
print("\n[written] exp2_gate.json")

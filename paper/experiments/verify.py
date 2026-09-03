"""Cross-check every numeric claim in the paper against the recorded experiment data."""
import json, os, re
EXP = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
TEX = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/main.tex"
tex = open(TEX).read()

gate = json.load(open(f"{EXP}/exp2_gate.json"))
abl  = json.load(open(f"{EXP}/exp3_ablation.json"))
vm   = json.load(open(f"{EXP}/exp4_vm.json"))
vm2  = json.load(open(f"{EXP}/exp5_vm2.json"))
lat  = json.load(open(f"{EXP}/exp6_latency.json"))
import numpy as np

checks = []
def chk(label, claimed, actual, tol=0.06, unit=""):
    if actual is None:
        checks.append((label, claimed, "n/a", "SKIP")); return
    ok = abs(claimed - actual) <= max(tol, abs(actual) * tol)
    checks.append((label, f"{claimed}{unit}", f"{actual:.4g}{unit}", "OK" if ok else "MISMATCH"))

def present(label, s):
    checks.append((label, s, "in text", "OK" if s in tex else "MISSING"))

# ---- gate corpus
n = len(gate); rej = [r for r in gate if not r["ok"]]
chk("assets measured", 54, n, 0)
chk("assets rejected", 16, len(rej), 0)
chk("rejection rate %", 29.6, 100*len(rej)/n, .1)
g = np.array([r["gain"] for r in rej])
chk("rejected over +25 dB", 11, int((g > 25).sum()), 0)
chk("median required gain", 29.1, float(np.median(g)), .15)
chk("max required gain", 42.1, float(g.max()), .15)
moss = [r for r in gate if r["backend"]=="moss"]; sa = [r for r in gate if r["backend"]=="stable_audio"]
chk("MOSS assets", 46, len(moss), 0); chk("MOSS rejected", 12, sum(not r["ok"] for r in moss), 0)
chk("SA assets", 8, len(sa), 0);      chk("SA rejected", 4, sum(not r["ok"] for r in sa), 0)
chk("MOSS median score", 54.5, float(np.median([r["score"] for r in moss])), .2)
chk("SA median score", 53.2, float(np.median([r["score"] for r in sa])), .2)
chk("MOSS median harmonic", 0.040, float(np.median([r["harm"] for r in moss])), .005)
chk("SA median harmonic", 0.898, float(np.median([r["harm"] for r in sa])), .005)
chk("harmonic ratio factor", 22, float(np.median([r["harm"] for r in sa])/np.median([r["harm"] for r in moss])), 1.0)
chk("assets harm > 0.80", 10, sum(1 for r in gate if r["harm"]>0.80), 0)

# ---- ablation
A = {r["label"]: r for r in abl["steps"]}; B = {r["label"]: r for r in abl["latent"]}
chk("50-step score", 86.9, A["50 steps (production)"]["score"], .1)
chk("35-step score", 86.3, A["35 steps"]["score"], .1)
chk("25-step score", 86.4, A["25 steps"]["score"], .1)
chk("50-step dyn", 32.6, A["50 steps (production)"]["dyn"], .1)
chk("25-step dyn", 29.1, A["25 steps"]["dyn"], .1)
chk("steps attacks equal", 7, A["50 steps (production)"]["attacks"], 0)
chk("30s latent score", 97.1, B["30 s latent (production)"]["score"], .1)
chk("10s latent score", 86.0, B["10 s latent"]["score"], .1)
chk("30s latent dyn", 43.7, B["30 s latent (production)"]["dyn"], .1)
chk("10s latent dyn", 61.1, B["10 s latent"]["dyn"], .1)
chk("30s latent bits", 14.9, B["30 s latent (production)"]["bits"], .1)
chk("10s latent bits", 16.0, B["10 s latent"]["bits"], .1)
chk("30s attacks", 16, B["30 s latent (production)"]["attacks"], 0)
chk("10s attacks", 8, B["10 s latent"]["attacks"], 0)
chk("30s gap sd", 0.042, B["30 s latent (production)"]["gap_sd"], .002)
chk("10s gap sd", 0.244, B["10 s latent"]["gap_sd"], .002)
chk("irregularity factor", 5.8, B["10 s latent"]["gap_sd"]/B["30 s latent (production)"]["gap_sd"], .15)
chk("latent speedup x", 2.8, B["30 s latent (production)"]["gen_s"]/B["10 s latent"]["gen_s"], .1)
chk("cup pickup 30s pass", 1, abl["cup30"], 0)
chk("cup pickup 10s pass", 0, abl["cup10"], 0)

# ---- visual microphone
b = {r["true"]: r for r in vm["B"]}
chk("70 Hz aliases to", 50, b[70]["dom"], .5)
chk("100 Hz aliases to", 20, b[100]["dom"], .5)
chk("55 Hz recovered", 55, b[55]["dom"], .5)
fl = {r["amp"]: r for r in vm2["floor"]}
chk("floor 0.020 share %", 48.2, fl[0.02]["share"], .3)
checks.append(("0.015 px not detected", "fails", str(fl[0.015]["detected"]), "OK" if not fl[0.015]["detected"] else "MISMATCH"))
tp = {r["side"]: r for r in vm2["throughput"]}
chk("throughput 64", 1284, tp[64]["fps"], 30); chk("throughput 128", 441, tp[128]["fps"], 12)
chk("throughput 256", 103, tp[256]["fps"], 5)

# ---- latency
s1 = lat["s1"]
chk("S1 mean inference", 1.57, float(np.mean([r["infer"] for r in s1])), .02)
chk("S1 mean total", 3.73, float(np.mean([r["total"] for r in s1])), .02)
chk("S1 mean frames", 87, float(np.mean([r["frames"] for r in s1])), 1)
chk("S1 runs", 7, len(s1), 0)
gen = lat["s2_gen"]
chk("S2 production gens", 31, len(gen), 0)
chk("S2 phase1", 4.7, float(np.mean([g["p1"] for g in gen])), .1)
chk("S2 phase2", 264.4, float(np.mean([g["p2"] for g in gen])), 1.0)
chk("S2 phase3", 8.6, float(np.mean([g["p3"] for g in gen])), .2)
chk("S2 total", 280.9, float(np.mean([g["tot"] for g in gen])), 1.0)
chk("S2 peak GB", 12.11, float(np.mean([g["peak"] for g in gen])), .05)
chk("S2 min avail mean", 2.35, float(np.mean([g["avail"] for g in gen])), .05)
chk("S2 min avail worst", 1.58, float(min(g["avail"] for g in gen)), .02)
chk("diffusion share %", 94, 100*np.mean([g["p2"] for g in gen])/np.mean([g["tot"] for g in gen]), 1)
w = np.array(lat["s2_wall"]); cached = w[w<150]; cold = w[w>=150]
chk("cached median s", 39.5, float(np.median(cached)), 1)
chk("generation median s", 556.9, float(np.median(cold)), 2)

# ---- cadence arithmetic
chk("MOSS pct slower", 9.9, 100*(0.641-0.583)/0.583, .3)
chk("SA pct faster", 30.2, 100*(0.583-0.407)/0.583, .3)
chk("SA 3-step deficit", 0.528, 3*(0.583-0.407), .01)

w_ok = sum(1 for c in checks if c[3]=="OK")
print(f"{'claim':<28}{'paper':>14}{'measured':>14}   status")
print("-"*72)
for lab, cl, ac, st in checks:
    flag = "" if st=="OK" else "   <<<<<<"
    print(f"{lab:<28}{str(cl):>14}{str(ac):>14}   {st}{flag}")
print("-"*72)
print(f"{w_ok}/{len(checks)} checks OK")
bad = [c for c in checks if c[3] not in ("OK",)]
if bad:
    print("\nNEEDS ATTENTION:")
    for c in bad: print("  ", c)

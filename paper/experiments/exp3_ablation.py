"""EXPERIMENT 3 - Generation-settings ablation: does the quality gate see what the ear hears?

Two speed-ups were tried and reverted after listening: fewer denoising steps, and a
shorter denoised latent. This measures the SAME assets the listening judgement was made
on, using the production metrics, plus a structural measure the gate does not compute
(transient count and rhythmic regularity).
"""
import sys, os, json
sys.path.insert(0, "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh/backend")
os.chdir("/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh")
import numpy as np, soundfile as sf
from services.foley_validation import validate, quality_score
from services.synchronization import attack_times
OUT = os.path.dirname(os.path.abspath(__file__))

def structure(p):
    y, sr = sf.read(p)
    if y.ndim > 1: y = y[:, 0]
    t = attack_times(np.asarray(y, float), sr)
    g = np.diff(t) if len(t) > 1 else np.array([])
    return len(t), (g.mean() if len(g) else float("nan")), (g.std() if len(g) else float("nan"))

def row(label, path, tgt, gen_s):
    v = validate(path, tgt); m = v.metrics
    n, mg, sg = structure(path)
    return dict(label=label, gen_s=gen_s, ok=v.ok,
                score=v.score if v.ok else quality_score(m),
                peak=m.peak_dbfs, dyn=m.dynamic_range_db, bits=m.effective_bits,
                harm=m.harmonic_ratio, gain=m.required_gain_db,
                attacks=n, gap=mg, gap_sd=sg)

print("=== A. DENOISING STEPS ABLATION  (impact_football, seed 42, 30 s latent) ===")
A = [row("50 steps (production)", "data/generated/moss_impact_football_21203cf0ab36bec6.wav", -31.0, 265.9),
     row("35 steps",              "data/generated/moss_impact_football_8c5adaeb0d9a10f4.wav", -31.0, 200.4),
     row("25 steps",              "data/generated/moss_impact_football_48956018c5fcf516.wav", -31.0, 128.6)]
hdr = f"{'setting':<24}{'gen s':>7}{'score':>7}{'dyn':>7}{'bits':>6}{'harm':>7}{'peak':>7}{'attacks':>8}"
print(hdr); print("-"*len(hdr))
for r in A:
    print(f"{r['label']:<24}{r['gen_s']:>7.0f}{r['score']:>7.1f}{r['dyn']:>7.1f}{r['bits']:>6.1f}"
          f"{r['harm']:>7.2f}{r['peak']:>7.1f}{r['attacks']:>8}")

print()
print("=== B. DENOISED-LATENT ABLATION  (walking, seed 42, 50 steps) ===")
B = [row("30 s latent (production)", "data/generated/moss_walking_da7ee566fba6f8b4.wav", -34.0, 242.3),
     row("10 s latent",              "data/generated/moss_walking_2c64bdaf6bee5607.wav", -34.0, 88.0)]
hdr2 = f"{'setting':<26}{'gen s':>7}{'score':>7}{'dyn':>7}{'bits':>6}{'harm':>7}{'attacks':>9}{'gap s':>8}{'gap sd':>8}"
print(hdr2); print("-"*len(hdr2))
for r in B:
    print(f"{r['label']:<26}{r['gen_s']:>7.0f}{r['score']:>7.1f}{r['dyn']:>7.1f}{r['bits']:>6.1f}"
          f"{r['harm']:>7.2f}{r['attacks']:>9}{r['gap']:>8.3f}{r['gap_sd']:>8.3f}")
print("   filmed gait for reference:                                          "
      "        4    0.583   0.034")

print()
print("=== C. LATENT ABLATION ACROSS THE 3-SEED CUP-PICKUP LADDER ===")
print("   (cup pickup is the hardest class; multi-candidate exists because of it)")
C30 = [("seed 42", "data/generated/moss_cup_pickup_8b53bff2a694fe9c.wav"),
       ("seed 43", "data/generated/moss_cup_pickup_e9d0a0ff5d6e9381.wav"),
       ("seed 44", "data/generated/moss_cup_pickup_d291458b03e5e609.wav")]
C10 = [("seed 42", "data/generated/moss_cup_pickup_b7164e7de83b6421.wav"),
       ("seed 43", "data/generated/moss_cup_pickup_3ecfc07d3e09d2f9.wav"),
       ("seed 44", "data/generated/moss_cup_pickup_61ea935e9014cd16.wav")]
hdr3 = f"{'latent':<12}{'seed':<9}{'gate':>7}{'score':>7}{'dyn':>7}{'bits':>6}{'peak':>7}{'gain':>8}"
print(hdr3); print("-"*len(hdr3))
res = {}
for tag, lst in (("30 s", C30), ("10 s", C10)):
    passes = 0
    for sd, p in lst:
        r = row(sd, p, -33.0, 0)
        passes += r["ok"]
        print(f"{tag:<12}{sd:<9}{('PASS' if r['ok'] else 'FAIL'):>7}{r['score']:>7.1f}"
              f"{r['dyn']:>7.1f}{r['bits']:>6.1f}{r['peak']:>7.1f}{r['gain']:>+8.1f}")
    res[tag] = passes
    print(f"{'':<12}{'-> candidates passing:':<9} {passes}/3")
print()
print(f"SUMMARY: with the 30 s latent {res['30 s']}/3 candidates were usable; "
      f"with the 10 s latent {res['10 s']}/3 were usable.")

json.dump(dict(steps=A, latent=B, cup30=res.get("30 s"), cup10=res.get("10 s")),
          open(os.path.join(OUT, "exp3_ablation.json"), "w"), indent=2, default=str)
print("[written] exp3_ablation.json")

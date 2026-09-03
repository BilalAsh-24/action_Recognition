"""Figures 2-4: quality gate, ablation structure, alignment cadence. All from real data."""
import sys, os, json, glob
sys.path.insert(0, "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh/backend")
os.chdir("/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh")
import numpy as np, soundfile as sf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from services.synchronization import attack_times, envelope

FIG = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/figs"
EXP = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True,
                     "grid.alpha": .3, "grid.linewidth": .4, "axes.linewidth": .6,
                     "xtick.major.width": .6, "ytick.major.width": .6, "legend.frameon": False})

# ---------------------------------------------------------------- Fig 2: quality gate
rows = json.load(open(os.path.join(EXP, "exp2_gate.json")))
fig, ax = plt.subplots(figsize=(3.4, 2.5))
for backend, mark, lab in (("moss", "o", "MOSS-SoundEffect"), ("stable_audio", "s", "Stable Audio Open")):
    sel = [r for r in rows if r["backend"] == backend]
    okx  = [r["dyn"] for r in sel if r["ok"]];  oky  = [r["harm"] for r in sel if r["ok"]]
    bax  = [r["dyn"] for r in sel if not r["ok"]]; bay = [r["harm"] for r in sel if not r["ok"]]
    ax.scatter(okx, oky, marker=mark, s=22, facecolors="none",
               edgecolors=("#1f4e79" if backend=="moss" else "#a33"), linewidths=.9,
               label=f"{lab} — passed")
    ax.scatter(bax, bay, marker=mark, s=22,
               color=("#1f4e79" if backend=="moss" else "#a33"), alpha=.85,
               label=f"{lab} — rejected")
ax.axvline(6.0, color="k", ls="--", lw=.7)
ax.axhline(0.90, color="k", ls=":", lw=.7)
ax.text(6.4, 1.03, "dynamic-range gate", fontsize=6, rotation=0)
ax.text(46, 0.92, "pure-tone gate", fontsize=6, ha="right")
ax.set_xlabel("Dynamic range (dB)"); ax.set_ylabel("Harmonic ratio")
ax.set_xlim(-2, 68); ax.set_ylim(-0.05, 1.12)
ax.legend(fontsize=5.6, loc="upper right", ncol=1, handletextpad=.3, labelspacing=.25)
fig.tight_layout(pad=.3)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_gate.{e}", dpi=300)
print("fig_gate written")

# ------------------------------------------------- Fig 3: latent ablation, walking asset
pairs = [("30 s denoised latent (production)", "data/generated/moss_walking_da7ee566fba6f8b4.wav"),
         ("10 s denoised latent (ablation)",   "data/generated/moss_walking_2c64bdaf6bee5607.wav")]
fig, axs = plt.subplots(2, 1, figsize=(3.4, 2.6), sharex=True)
for ax, (lab, p) in zip(axs, pairs):
    y, sr = sf.read(p)
    if y.ndim > 1: y = y[:, 0]
    y = np.asarray(y, float)
    t = np.arange(len(y)) / sr
    env = envelope(y, sr)
    at = attack_times(y, sr)
    ax.plot(t, env / (env.max() + 1e-12), lw=.5, color="#333")
    for a in at:
        ax.axvline(a, color="#c33", lw=.6, alpha=.85)
    g = np.diff(at)
    ax.set_ylabel("envelope", fontsize=7)
    ax.set_title(f"{lab} — {len(at)} attacks, gap sd {g.std():.3f} s" if len(g) else lab,
                 fontsize=7, pad=2)
    ax.set_ylim(0, 1.05)
axs[-1].set_xlabel("Time within generated asset (s)")
axs[-1].set_xlim(0, 10)
fig.tight_layout(pad=.3)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_latent.{e}", dpi=300)
print("fig_latent written")

# ------------------------------------------------------- Fig 4: cadence vs filmed gait
assets = {"MOSS (production)": "data/generated/moss_walking_da7ee566fba6f8b4.wav",
          "MOSS (10 s latent)": "data/generated/moss_walking_2c64bdaf6bee5607.wav",
          "Stable Audio Open": "data/generated/stable_audio_walking_1beada76b97253c5.wav"}
filmed = np.diff([0.458, 1.083, 1.667, 2.208])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.9, 2.2))
labs, means, sds = [], [], []
for lab, p in assets.items():
    y, sr = sf.read(p)
    if y.ndim > 1: y = y[:, 0]
    at = attack_times(np.asarray(y, float), sr); g = np.diff(at)
    labs.append(lab); means.append(g.mean()); sds.append(g.std())
labs.append("Filmed gait\n(measured)"); means.append(filmed.mean()); sds.append(filmed.std())
cols = ["#1f4e79", "#7aa6c2", "#a33", "#2b2b2b"]
a1.bar(range(len(labs)), means, yerr=sds, capsize=3, color=cols, width=.6,
       error_kw=dict(lw=.8, capthick=.8))
a1.set_xticks(range(len(labs))); a1.set_xticklabels(labs, fontsize=6)
a1.set_ylabel("Mean inter-step interval (s)")
a1.axhline(filmed.mean(), color="k", ls="--", lw=.7)
a1.set_title("Generated cadence vs filmed gait", fontsize=7.5)

res = {"MOSS (production)": [0.0, -67.6, -4.7, 1.0],
       "Stable Audio Open": [0.0, -150.6, -322.0, -462.4]}
for (lab, r), c in zip(res.items(), ["#1f4e79", "#a33"]):
    a2.plot(range(1, len(r) + 1), r, "o-", ms=4, lw=1, color=c, label=lab)
a2.axhspan(-20.8, 20.8, color="#999", alpha=.22, lw=0)
a2.text(1.05, 26, "± half a frame (24 fps)", fontsize=6, color="#444")
a2.set_xticks([1, 2, 3, 4]); a2.set_xlabel("Foot plant index")
a2.set_ylabel("Alignment residual (ms)")
a2.legend(fontsize=6.5, loc="lower left")
a2.set_title("Residual accumulates with cadence mismatch", fontsize=7.5)
fig.tight_layout(pad=.4)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_cadence.{e}", dpi=300)
print("fig_cadence written")

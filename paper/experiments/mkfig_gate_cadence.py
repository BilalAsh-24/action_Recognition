"""Figures 2 and 4, corrected layout."""
import sys, os, json
sys.path.insert(0, "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh/backend")
os.chdir("/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh")
import numpy as np, soundfile as sf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from services.synchronization import attack_times

FIG = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/figs"
EXP = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True,
                     "grid.alpha": .3, "grid.linewidth": .4, "axes.linewidth": .6,
                     "xtick.major.width": .6, "ytick.major.width": .6, "legend.frameon": False})
BLUE, RED = "#1f4e79", "#a33"

# ------------------------------------------------------------- Fig 2: quality gate
rows = json.load(open(os.path.join(EXP, "exp2_gate.json")))
fig, ax = plt.subplots(figsize=(3.4, 2.9))
for backend, mark, col in (("moss", "o", BLUE), ("stable_audio", "s", RED)):
    sel = [r for r in rows if r["backend"] == backend]
    ax.scatter([r["dyn"] for r in sel if r["ok"]], [r["harm"] for r in sel if r["ok"]],
               marker=mark, s=24, facecolors="none", edgecolors=col, linewidths=1.0)
    ax.scatter([r["dyn"] for r in sel if not r["ok"]], [r["harm"] for r in sel if not r["ok"]],
               marker=mark, s=24, color=col, alpha=.9)
ax.axvline(6.0, color="k", ls="--", lw=.7)
ax.axhline(0.90, color="k", ls=":", lw=.7)
ax.annotate("dynamic-range gate\n(reject $<$ 6 dB)", xy=(6, .40), xytext=(13, .40),
            fontsize=6, va="center",
            arrowprops=dict(arrowstyle="->", lw=.5, color="#444"))
ax.annotate("pure-tone gate", xy=(40, .90), xytext=(40, .74), fontsize=6, ha="center",
            arrowprops=dict(arrowstyle="->", lw=.5, color="#444"))
ax.set_xlabel("Dynamic range (dB)"); ax.set_ylabel("Harmonic ratio")
ax.set_xlim(-3, 68); ax.set_ylim(-0.06, 1.10)
handles = [Line2D([], [], marker="o", ls="", mfc="none", mec=BLUE, mew=1.0, ms=5, label="MOSS — passed"),
           Line2D([], [], marker="o", ls="", color=BLUE, ms=5, label="MOSS — rejected"),
           Line2D([], [], marker="s", ls="", mfc="none", mec=RED, mew=1.0, ms=5, label="Stable Audio — passed"),
           Line2D([], [], marker="s", ls="", color=RED, ms=5, label="Stable Audio — rejected")]
ax.legend(handles=handles, fontsize=6, loc="upper center", bbox_to_anchor=(.5, -.22),
          ncol=2, handletextpad=.3, columnspacing=1.0, labelspacing=.3)
fig.tight_layout(pad=.3)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_gate.{e}", dpi=300, bbox_inches="tight")
print("fig_gate rewritten")

# --------------------------------------------------- Fig 4: cadence + residual growth
assets = [("MOSS\n(production)", "data/generated/moss_walking_da7ee566fba6f8b4.wav", BLUE),
          ("MOSS\n(10 s latent)", "data/generated/moss_walking_2c64bdaf6bee5607.wav", "#7aa6c2"),
          ("Stable Audio\nOpen", "data/generated/stable_audio_walking_1beada76b97253c5.wav", RED)]
filmed = np.diff([0.458, 1.083, 1.667, 2.208])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.3))
labs, means, sds, cols = [], [], [], []
for lab, p, c in assets:
    y, sr = sf.read(p)
    if y.ndim > 1: y = y[:, 0]
    g = np.diff(attack_times(np.asarray(y, float), sr))
    labs.append(lab); means.append(g.mean()); sds.append(g.std()); cols.append(c)
labs.append("Filmed gait\n(measured)"); means.append(filmed.mean()); sds.append(filmed.std()); cols.append("#2b2b2b")
a1.bar(range(len(labs)), means, yerr=sds, capsize=3, color=cols, width=.62,
       error_kw=dict(lw=.8, capthick=.8))
a1.set_xticks(range(len(labs))); a1.set_xticklabels(labs, fontsize=6.2)
a1.set_ylabel("Mean inter-step interval (s)")
a1.axhline(filmed.mean(), color="k", ls="--", lw=.7, zorder=0)
a1.set_ylim(0, 1.02)
a1.set_title("(a)  Generated cadence vs filmed gait", fontsize=7.5)

res = {"MOSS (production)": ([0.0, -67.6, -4.7, 1.0], BLUE),
       "Stable Audio Open": ([0.0, -150.6, -322.0, -462.4], RED)}
for lab, (r, c) in res.items():
    a2.plot(range(1, len(r) + 1), r, "o-", ms=4, lw=1.1, color=c, label=lab)
a2.axhspan(-20.8, 20.8, color="#888", alpha=.20, lw=0)
a2.text(4.0, 34, "$\\pm$ half a frame (24 fps)", fontsize=6, color="#444", ha="right")
a2.set_xticks([1, 2, 3, 4]); a2.set_xlabel("Foot plant index")
a2.set_ylabel("Alignment residual (ms)")
a2.set_ylim(-500, 90)
a2.legend(fontsize=6.5, loc="lower left")
a2.set_title("(b)  Residual accumulates with cadence mismatch", fontsize=7.5)
fig.tight_layout(pad=.4)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_cadence.{e}", dpi=300, bbox_inches="tight")
print("fig_cadence rewritten")

"""Figure 5: Visual Microphone Nyquist behaviour and detection floor."""
import json, os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
FIG = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/figs"
EXP = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True,
                     "grid.alpha": .3, "grid.linewidth": .4, "axes.linewidth": .6,
                     "legend.frameon": False})
BLUE, RED = "#1f4e79", "#a33"
B = json.load(open(f"{EXP}/exp4_vm.json"))["B"]
F = json.load(open(f"{EXP}/exp5_vm2.json"))["floor"]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.4))

# ---- (a) Nyquist folding at 120 fps
tr = np.array([r["true"] for r in B]); dm = np.array([r["dom"] for r in B])
below = tr < 60
a1.plot([0, 120], [0, 120], ls=":", lw=.8, color="#888", label="ideal (recovered = true)")
xs = np.linspace(0, 120, 400)
a1.plot(xs, np.abs(((xs + 60) % 120) - 60), ls="--", lw=.8, color=RED,
        label="predicted alias (fold about Nyquist)")
a1.scatter(tr[below], dm[below], s=30, color=BLUE, zorder=5, label="measured, $f <$ Nyquist")
a1.scatter(tr[~below], dm[~below], s=30, color=RED, marker="s", zorder=5,
           label="measured, $f >$ Nyquist")
a1.axvline(60, color="k", lw=.7)
a1.text(62.5, 8, "Nyquist\n60 Hz", fontsize=6, va="bottom")
a1.set_xlabel("True vibration frequency (Hz)")
a1.set_ylabel("Recovered dominant frequency (Hz)")
a1.set_xlim(0, 110); a1.set_ylim(0, 115)
a1.legend(fontsize=5.8, loc="upper left", borderaxespad=.4)
a1.set_title("(a)  Recovery and aliasing at 120 fps", fontsize=7.5)

# ---- (b) detection floor
amp = np.array([r["amp"] for r in F]); sh = np.array([r["share"] for r in F])
det = np.array([r["detected"] for r in F])
a2.semilogx(amp[det], sh[det], "o", ms=5, color=BLUE, label="10 Hz recovered")
a2.semilogx(amp[~det], sh[~det], "x", ms=6, color=RED, mew=1.4, label="not recovered")
a2.semilogx(amp, sh, lw=.7, color="#888", zorder=0)
a2.axvspan(0.015, 0.020, color="#ddd", alpha=.7, lw=0)
a2.text(0.0173, 33, "detection\nfloor", fontsize=6, ha="center", va="center")
a2.set_xlabel("Sub-pixel displacement amplitude (px)")
a2.set_ylabel("Energy at true frequency (%)")
a2.set_ylim(-4, 78)
a2.legend(fontsize=6.5, loc="upper left")
a2.set_title("(b)  Sensitivity at 240 fps", fontsize=7.5)

fig.tight_layout(pad=.4)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_vm.{e}", dpi=300, bbox_inches="tight")
print("fig_vm written")

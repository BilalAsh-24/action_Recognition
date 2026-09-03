"""Figure 6 corrected: interval labels along the top, legend below the axes."""
import sys, os, json
sys.path.insert(0, "/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh/backend")
os.chdir("/Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh")
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from services.synchronization import analyse_video
FIG = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/figs"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True,
                     "grid.alpha": .3, "grid.linewidth": .4, "axes.linewidth": .6,
                     "legend.frameon": False})
mo = analyse_video("input/test_video.mp4", 24.0)
t = mo["t"]
fig, ax = plt.subplots(figsize=(7.0, 2.6))
ax.plot(t, mo["bands"]["feet"],  "-",  color="#1f4e79", lw=1.2, label="feet band (0.62–1.00 h)")
ax.plot(t, mo["bands"]["head"],  "-",  color="#a33",    lw=.9,  label="head band (0.00–0.50 h)")
ax.plot(t, mo["bands"]["table"], "--", color="#2e7d32", lw=.9,  label="table band (0.40–0.85 h)")

segs = [(0.0,1.5,"stand"), (1.5,2.5,"walk"), (2.5,5.5,"pick up cup"),
        (5.5,8.5,"drink"), (8.5,10.0,"place cup")]
TOP = 3.55
for i,(a,b,lab) in enumerate(segs):
    if i % 2 == 0: ax.axvspan(a, b, color="#000", alpha=.035, lw=0)
    ax.axvline(a, color="#bbb", lw=.5)
    ax.text((a+b)/2, TOP*.955, lab, fontsize=6, ha="center", va="top", color="#444")
ax.text(0.06, TOP*.86, "Module 2 intervals", fontsize=5.6, color="#777", style="italic")

for p in [0.458,1.083,1.667,2.208]:
    ax.plot([p],[np.interp(p,t,mo["bands"]["feet"])],  "v", color="#1f4e79", ms=6, zorder=6)
for h in [6.625,7.792]:
    ax.plot([h],[np.interp(h,t,mo["bands"]["head"])],  "o", color="#a33",    ms=5, zorder=6)
for c_ in [9.833]:
    ax.plot([c_],[np.interp(c_,t,mo["bands"]["table"])],"s", color="#2e7d32", ms=5, zorder=6)
ax.plot([],[], "v", color="#1f4e79", ms=6, ls="", label="foot plant")
ax.plot([],[], "o", color="#a33",    ms=5, ls="", label="sip hold")
ax.plot([],[], "s", color="#2e7d32", ms=5, ls="", label="cup contact")

ax.set_xlabel("Time (s)"); ax.set_ylabel("Mean abs. inter-frame difference")
ax.set_xlim(0,10.02); ax.set_ylim(0, TOP)
ax.legend(fontsize=6.2, loc="upper center", bbox_to_anchor=(.5,-.20), ncol=6,
          columnspacing=1.1, handletextpad=.4)
fig.tight_layout(pad=.35)
for e in ("pdf","png"): fig.savefig(f"{FIG}/fig_motion.{e}", dpi=300, bbox_inches="tight")
print("fig_motion rewritten")

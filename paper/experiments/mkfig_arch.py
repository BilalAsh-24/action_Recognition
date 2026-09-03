"""Figure 1: system architecture - three silent-video-to-audio paths."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
FIG = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/figs"
plt.rcParams.update({"font.size": 7, "font.family": "serif"})

BLUE, GREEN, RED, GREY = "#1f4e79", "#2e7d32", "#a33", "#555"
fig, ax = plt.subplots(figsize=(7.1, 3.05))
ax.set_xlim(0, 100); ax.set_ylim(0, 41); ax.axis("off")

def box(x, y, w, h, text, ec, fc="white", fs=6.4, lw=.9, style="round,pad=0.02"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, ec=ec, fc=fc, lw=lw, zorder=3))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs, zorder=4, linespacing=1.25)

def arrow(x1, y1, x2, y2, c=GREY, lw=.85, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, color=c,
                                 lw=lw, mutation_scale=8, zorder=2,
                                 shrinkA=0, shrinkB=0))

# input / output rails
box(1.5, 17.5, 11, 8, "Silent\nvideo", "#000", "#f0f0f0", fs=7.2, lw=1.1)
box(87.5, 17.5, 11, 8, "Video with\ngenerated\naudio", "#000", "#f0f0f0", fs=7.2, lw=1.1)

lanes = [
  (33.0, BLUE,  "S1  Lip reading and speech generation",
   [("MediaPipe landmarks\n+ 96$\\times$96\nmouth ROI", 13.0),
    ("Auto-AVSR Conformer\n/ Transformer\n(visual only)", 14.5),
    ("CTC forced\nalignment\n$\\to$ word onsets", 12.0),
    ("Kokoro TTS\n+ phrase\nplacement", 11.0)]),
  (20.0, GREEN, "S2  Action recognition and Foley generation",
   [("Qwen2.5-VL-3B\n2 s windows,\n1 s stride", 12.5),
    ("Foley prompt\nresolution\n(16 curated + open)", 14.0),
    ("MOSS-SoundEffect\nDiT + flow matching\n48 kHz", 14.0),
    ("Quality gate\n$\\to$ visual events\n$\\to$ alignment", 13.5)]),
  (7.0,  RED,   "S3  Acoustic Eye (visual microphone)",
   [("Complex steerable\npyramid per frame", 15.0),
    ("Local phase\ndifference vs\nreference frame", 13.5),
    ("Amplitude-weighted\nband signals,\naligned and summed", 15.5),
    ("High-pass +\nWAV at\n$f_s =$ fps", 10.0)]),
]

for y, col, title, blocks in lanes:
    ax.text(14.5, y + 8.9, title, fontsize=7.0, color=col, style="italic")
    x = 14.5
    arrow(12.5, 21.5, x, y + 4.0, c=col)
    for i, (txt, w) in enumerate(blocks):
        box(x, y, w, 8, txt, col, fs=5.9)
        if i < len(blocks) - 1:
            arrow(x + w, y + 4, x + w + 2.0, y + 4, c=col)
        x += w + 2.0
    arrow(x - 2.0, y + 4.0, 87.5, 21.5, c=col)

fig.tight_layout(pad=.2)
for e in ("pdf", "png"): fig.savefig(f"{FIG}/fig_arch.{e}", dpi=300, bbox_inches="tight")
print("fig_arch written")

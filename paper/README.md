# Research paper

IEEE-format manuscript covering the whole project: lip reading and speech
generation (S1), action recognition and Foley generation (S2), and Acoustic Eye
(S3).

```
paper/
├── Reconstructing_Audio_from_Silent_Video.pdf   12-page two-column PDF
├── main.tex          IEEEtran conference-class source (submission format)
├── paper_print.html  two-column print layout the PDF was rendered from
├── paper_web.html    single-column reading version
├── figs/             six figures, PDF for LaTeX + PNG for the HTML versions
├── experiments/      the analysis and figure scripts
└── README.md         this file
```

## About the PDF

`Reconstructing_Audio_from_Silent_Video.pdf` is 12 pages, US Letter, two-column,
10 pt Times — visually an IEEE paper. It was produced by rendering
`paper_print.html` with headless Chrome, **not** by compiling `main.tex`, because
this machine has no LaTeX installed.

That distinction matters if you are submitting to an actual IEEE venue: the PDF
is an IEEE-*style* layout built with CSS multi-column, not genuine `IEEEtran`
output. It is fine for a supervisor, a report submission, or review. For a real
IEEE conference or journal submission, compile `main.tex` instead — the
formatting will then be exactly to spec.

Regenerating the PDF after editing `paper_print.html`:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --user-data-dir="$(mktemp -d)" \
  --no-pdf-header-footer --virtual-time-budget=25000 \
  --print-to-pdf="Reconstructing_Audio_from_Silent_Video.pdf" \
  "file://$PWD/paper_print.html"
```

Chrome does not always exit on its own; the PDF is written before it hangs, so
kill it after ~40 s if needed.

## Building from LaTeX

`main.tex` has not been compiled — there is no TeX toolchain here. It is written
against the standard `IEEEtran` class and uses only `cite`, `amsmath`,
`amssymb`, `graphicx`, `booktabs`, `url`, `hyperref` and `textcomp` — all present
in a default TeX Live install.

**Overleaf** (no local install): create a project, upload `main.tex` and the
`figs/` folder, set the compiler to pdfLaTeX. It compiles in one pass — the
bibliography is an inline `thebibliography`, so no BibTeX run is needed.

**Locally**, with MacTeX or TeX Live installed:

```bash
cd paper && pdflatex main.tex && pdflatex main.tex
```

Run it twice so cross-references resolve.

## Before submitting

Three things need filling in:

- **Affiliation.** The author block in `main.tex` has `[Department]`,
  `[Institution]` and `[City, Country]` placeholders.
- **Target venue.** The paper is formatted for an IEEE conference. A journal
  target needs `\documentclass[journal]{IEEEtran}` and a longer format.
- **Supervisor / co-authors**, if they should appear.

## Figures

Every figure is generated from the project's own recorded data, not drawn by
hand. Regenerating them requires the scripts used to produce them, which read
from `Module3_Fresh/results/`, `Module3_Fresh/data/jobs/` and
`Module3_Fresh/data/generated/`.

| Figure | Content | Source data |
|---|---|---|
| `fig_arch` | three-path system architecture | schematic |
| `fig_motion` | region-band motion + detected visual events | `input/test_video.mp4`, recomputed |
| `fig_cadence` | generated cadence vs filmed gait; residual growth | generated assets + job records |
| `fig_gate` | all 54 assets in the harmonic/dynamic-range plane | `data/generated/`, `audio/generated/` |
| `fig_latent` | envelope + attacks, 30 s vs 10 s latent | two walking assets |
| `fig_vm` | Nyquist folding and sub-pixel detection floor | synthetic stimuli, run for the paper |

## Claims and evidence

Everything numeric in the paper traces to recorded project data. The sources are:

- **Job records** — 32 completed pipeline runs in `Module3_Fresh/data/jobs/`,
  carrying per-event alignment residuals written at render time.
- **Generation records** — 38 runs in `Module3_Fresh/results/web_*_generation.json`,
  31 of them at production settings, with per-phase timing and memory.
- **Asset corpus** — all 54 WAV files, re-measured with the production validator
  in `backend/services/foley_validation.py`.
- **Test suites** — `test_suite.py` (42) and `test_foley_validation.py` (22),
  both run and passing; plus `e2e_gate.py`.
- **S1 runs** — the seven transcripts in `02-Auto-AVSR-Test/outputs/`.

62 numeric claims were checked programmatically against these sources; all
matched. The 23 references were each verified against a primary source (IEEE
Xplore, CVF, NeurIPS/ICLR proceedings, ACM DL, ISCA Archive, arXiv) — none are
fabricated.

## Things the paper deliberately does not claim

Stated as limitations in Section IX rather than smoothed over:

- No word error rate for S1 — ground-truth transcripts were not retained.
- Listening judgements come from a single assessor.
- S3 is characterised on synthetic stimuli only; no real sound has been
  recovered from real footage.
- The 20 ms synchronisation figure is seven events on one clip, measured on the
  build tuned against it.
- No benchmark comparison against Diff-Foley, MMAudio or FoleyCrafter.

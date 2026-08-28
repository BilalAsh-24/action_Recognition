# MMAudio small_44k — Drinking Foley, Generation v1

**Date:** 2026-08-25
**Output:** `Module3_Fresh/mmaudio/results/drinking_mmaudio_v1.wav`
**Generations run:** exactly 1 — no regeneration, no parameter sweep, no prompt change.

---

# QUALITY VERDICT: ❌ FAIL

**Not recognisable as drinking — because there is essentially no audio during the drinking window.**

The generated clip covers source time 2.0–10.0 s. The drinking action occupies source 5.5–8.5 s,
which is clip time 3.50–6.50 s. In that window:

| Measurement | Value |
|---|---|
| Events detected | **0** |
| Active frames | **0.00 %** |
| RMS | 0.001394 |
| Peak | 0.00797 (−42 dBFS) |

Meanwhile **100 % of the generated activity** (4 of 5 events, all the energy) sits in clip
0.02–2.03 s — which is **source 2.02–4.03 s**, i.e. the end of *"walk around table"* and the start
of *"pick up cup"*.

**The model generated sound for the wrong action.** It responded to the cup pickup and produced
near-silence for the sip. Whatever the audible events sound like, there is nothing in the drinking
window to recognise, so this cannot pass.

---

## What the run actually did

| | |
|---|---|
| Model | MMAudio `small_44k`, 44.1 kHz |
| Device | Apple MPS (M4, 17.18 GB) |
| Precision | bf16 CLIP + Synchformer · **fp32** diffusion · **fp32** VAE + BigVGAN · no fp16 |
| Seed / steps / CFG | 42 / 25 (euler) / 4.5 — upstream defaults |
| Video context | source 2.00–10.00 s, video stream only (no audio stream present) |
| Actual duration | 7.9644 s (frame budget truncated the requested 8.00 s) |
| Sequence lengths | latent 343 · clip 63 · sync 184 |
| Wall time | **70 s total** (phase 1 47 s, phase 2 8.8 s, phase 3 14.3 s) |

Phase separation worked exactly as designed — the three phases ran as isolated subprocesses and
never held CLIP, the diffusion net, and the vocoder co-resident:

| Phase | Resident | Params |
|---|---|---|
| 1 — CLIP + Synchformer (bf16) | VAE/vocoder proven `None` | 1109.16 M |
| 2 — diffusion net (fp32) | FeaturesUtils proven 0 params | 157.41 M |
| 3 — VAE decoder + BigVGAN (fp32) | CLIP/Synchformer proven `None` | 298.49 M |

## Memory

| | Value |
|---|---|
| Baseline used / available / swap | 8.37 / 6.38 / 0.70 GB |
| **Peak used** | **10.25 GB** |
| **Min available** | **2.32 GB** (guard was 1.5 GB — never approached) |
| Peak swap | 1.19 GB |
| **Swap growth** | **+0.49 GB** |
| Breach / killed | none / no |

**My earlier evaluation was wrong about this, and materially so.** I predicted a ~7.9 GB CLIP
construction transient and insisted on a ≤5 GB host baseline. The real Phase 1 peak was **+1.9 GB
over baseline** — `open_clip` does not hold the checkpoint and the model doubly resident the way I
assumed. The ≤5 GB precondition was unnecessary, and the run had ~4× more headroom than I projected.

For contrast, this is now the best-behaved run in the project: **+0.49 GB swap growth**, against
MMAudio's earlier all-resident attempt (+3.8 GB, killed) and FoleyCrafter's two runs (+6.04 and
+10.08 GB, one aborted).

---

## Objective analysis (all 15 requested checks)

| # | Check | Result |
|---|---|---|
| 1 | Duration | 7.9644 s |
| 2 | Sample rate | 44,100 Hz |
| 3 | Channels | 1 (mono) |
| 4 | RMS | 0.004255 |
| 5 | Peak | 0.15027 (−16.46 dBFS) |
| 6 | Clipping | **none** — 0 samples ≥ 1.0, 0 above 0.99 |
| 7 | NaN / Inf | **none** — all finite |
| 8 | Acoustic onset | 0.0203 s |
| 9 | Acoustic offset | 7.9209 s |
| 10 | Distinct events | **5** |
| 11 | Event durations | 0.496 / 0.087 / 0.160 / 0.453 / 0.046 s (mean 0.248) |
| 12 | Event spacing | 0.421 / 0.218 / 0.177 / **5.846** s |
| 13 | Spectral | centroid 4497 Hz · rolloff95 15.3 kHz · flatness **0.027** · bands: 36.8 % <200 Hz, 41.6 % 200 Hz–1 kHz, 16.1 % 1–4 kHz, 4.0 % 4–8 kHz, 1.5 % 8–16 kHz |
| 14 | Silence | 82.6 % of frames below −20 dB · 86.5 % below acoustic threshold · 0.73 % true digital silence |
| 15 | Activity through action window | **0 events, 0 % active, RMS 0.0014** |

Crest factor 30.96 dB. Dynamic range (p95−p5) 18.7 dB.

### Event map

| # | Start | End | Dur | Peak | In drink window? |
|---|---|---|---|---|---|
| 1 | 0.020 | 0.517 | 0.496 s | 0.056 | no |
| 2 | 0.938 | 1.025 | 0.087 s | 0.025 | no |
| 3 | 1.242 | 1.402 | 0.160 s | 0.050 | no |
| 4 | 1.579 | 2.032 | 0.453 s | **0.150** | no |
| 5 | 7.877 | 7.924 | 0.046 s | 0.014 | no |

Per-second RMS: `0.0064, 0.0094, 0.0020, 0.0014, 0.0013, 0.0014, 0.0014, 0.0018`
— energy collapses after second 2 and never returns.

### Envelope

```
   0dB   |                                  #   #                                          |
  -6dB   |       ##                 #      ###  ##                                         |
 -12dB   | #########         ##     ##   ###### ###                                       #|
 -18dB   |##############  ##########################     #            ##          #      ##|
 -24dB   |######################################################## # ######################|
         |^         ^         ^         ^         ^         ^         ^         ^          |
          0s        1s        2s        3s        4s        5s        6s        7s
         |                              ==============================                     |  <- DRINK window
```

---

## What this is *not*

Some genuine positives worth recording, because they distinguish this from the earlier failures:

- **It is not hiss or a noise bed.** Spectral flatness 0.027 (white noise ≈ 1.0), 86.5 % of frames
  below the acoustic threshold. Compare FoleyCrafter's run 2: flatness 0.126 with **zero** frames
  below −20 dB. This output is sparse and structured, not a continuous texture.
- **It is not clicks or pops.** Event durations of 0.496 s, 0.453 s, and 0.160 s are sustained
  gestures, not transients. Only event 5 (0.046 s) is click-length.
- **It is not electronic.** Energy is 78 % below 1 kHz with a smooth rolloff — physical-sounding,
  consistent with cup/hand/surface contact.
- **It is technically clean.** No clipping, no NaN/Inf, correct 44.1 kHz mono, correct duration.

So the *material* looks like plausible physical Foley. It is simply **placed on the wrong action**.

---

## Why this likely happened

Offered as hypotheses, not conclusions — I have not tested any of them, and doing so would require
more generations than you authorised.

1. **The prompt was truncated to 42 % of its length.** CLIP's text encoder has a hard 77-token
   context. Your prompt is **189 BPE tokens**, so **112 tokens were discarded** — everything from
   *"lips. Include natural ceramic cup handling…"* onward. Critically, that includes the sentence
   *"The drinking action should continue throughout the relevant visible drinking sequence, with
   multiple clearly recognizable sip and swallow events rather than isolated clicks"* — the exact
   instruction targeting the failure that occurred — **and all 15 negative clauses**, which never
   reached the model at all.

2. **The 8 s context contains four actions, and the model picked the wrong one.** Source 2.0–10.0 s
   spans *walk* → *pick up cup* → *drink* → *place cup*. Synchformer keys on visual motion energy;
   the cup lift is a large, fast gesture, whereas drinking is a person holding a mug near their face
   with little movement. The model appears to have locked onto the most salient motion and treated
   the low-motion drinking pose as a non-event.

3. **`small_44k` is the smallest variant** (157 M parameters). `large_44k_v2` is ~6× larger and is
   upstream's recommended model. It is not currently downloaded.

4. **Negative conditioning was empty.** `negative_text=""` (upstream `demo.py` default). Your
   negations were inside the positive prompt, where they were both truncated away and — had they
   survived — would have been conditioning *toward* those tokens rather than away from them.

---

## Files written

| Path | Contents |
|---|---|
| `mmaudio/results/drinking_mmaudio_v1.wav` | the single generated audio, 7.96 s, 44.1 kHz mono PCM_16 |
| `mmaudio/results/drinking_mmaudio_v1_generation.json` | full config, per-phase verification, memory telemetry |
| `mmaudio/results/drinking_mmaudio_v1_analysis.json` | all 15 objective measurements |
| `mmaudio/results/drinking_mmaudio_v1_report.md` | this report |

Nothing else was modified. The source video, Module 2 outputs, all previous WAVs and MP4s, the
MMAudio repository, and every existing environment are untouched.

---

## Recommendation

**Do not synchronise this.** There is no drinking audio to place.

Please still listen — my verdict is built on measurements, not on hearing it, and your ears are the
authority on the first two seconds. But the central finding does not depend on timbre: the drinking
window contains 0 events at −42 dB peak, so there is nothing there to sound like anything.

When you authorise a second generation, the highest-value single change is **fixing the prompt
truncation** — shortening the positive prompt to ≤ 77 tokens and moving the negations into
`negative_text`, where MMAudio can actually use them. Narrowing the context window so the cup pickup
does not dominate would be the natural second change. I have made neither, and will not, until you
say so.

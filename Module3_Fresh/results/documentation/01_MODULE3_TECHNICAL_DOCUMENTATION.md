# Module 3 — Technical Documentation
## Action-Conditioned Foley Generation and Visual Synchronisation for Silent Video

**Document version:** 1.0 (final)
**Implementation status:** complete and verified
**Build date:** 2026-08-25
**Verification:** 19 automated checks passed (17 numbered categories; the synchronisation check is
evaluated separately for walking, drinking and placement)

---

## 1. Module 3 Objective

Module 3 converts the action labels produced by Module 2 into synchronised Foley audio, and combines
that audio with the original silent video to produce a final audio-visual output.

The module addresses three distinct problems:

1. **Sound generation** — producing physically plausible Foley for each recognised action, from a
   text description of that action.
2. **Temporal localisation** — determining *when*, within a broad action interval, the audible event
   actually occurs.
3. **Assembly** — selecting, levelling and mixing the generated audio, then muxing it with the
   unmodified source video.

The distinguishing design decision is that Module 3 does not treat Module 2's action boundaries as
sound cues. Action intervals describe *what is happening over a span of time*; Foley requires
*the instant of contact*. Module 3 therefore performs an independent frame-level visual analysis to
locate those instants, and aligns audio to them.

---

## 2. Input

Module 3 consumes three inputs and modifies none of them:

| Input | Path | Role |
|---|---|---|
| Original silent video | `input/test_video.mp4` | picture track and timing reference |
| Module 2 action-recognition output | `module2/module2_action_segments.json` | recognised actions |
| Resolved action timeline | `resolved_actions` array within the above | non-overlapping action spans |

**Use of the resolved timeline.** The Module 2 output contains two action arrays. The raw `actions`
array retains the overlapping spans produced by the sliding-window recogniser — for example
`pick up cup` spans 2.0–6.0 s while `drink from cup` spans 5.0–9.0 s, overlapping by one second.
Overlapping spans are ambiguous for audio placement, because a single instant would belong to two
actions simultaneously.

The `resolved_actions` array is the deterministic non-overlapping timeline produced by Module 2's
midpoint boundary resolution. Module 3 uses this array exclusively.

**Source integrity.** The source video is verified by SHA-256 before and after every build
(`a620ee5820ab9dfc4d538f9cdc4ebabe3614045f3d178dbdd658afb0ce7aabc8`). It is never re-encoded: the
final mux uses `-c:v copy`, so the output picture stream is bit-identical to the input.

---

## 3. Action Timeline

### 3.1 Module 2 resolved timeline

| Action | Start | End | Duration | Module 2 status |
|---|---|---|---|---|
| Stand | 0.0 s | 1.5 s | 1.5 s | suspect |
| Walk around table | 1.5 s | 2.5 s | 1.0 s | suspect |
| Pick up cup | 2.5 s | 5.5 s | 3.0 s | confirmed |
| Drink from cup | 5.5 s | 8.5 s | 3.0 s | confirmed |
| Place cup on table | 8.5 s | 10.0 s | 1.5 s | suspect |

These boundaries are used as the authoritative action segmentation and were not modified.

### 3.2 Why visual-event localisation was required

Placing audio at action-boundary timestamps produces two failure modes, both of which were observed
during development:

**(a) The audible event is not at the interval start.** A "place cup on table" interval spanning
8.5–10.0 s contains 1.5 seconds of arm movement and one instant of contact. Playing a contact sound
at 8.5 s places it approximately 1.3 seconds before the mug actually touches the table.

**(b) An action label may not describe the whole interval it covers.** Module 2 labels 0.0–1.5 s as
`stand`, but flags that segment `status: suspect` with
`flags: ["first_segment (window sees pre-action framing)"]`. Frame-level measurement contradicts the
label:

| Interval | Module 2 label | Mean lower-body motion |
|---|---|---|
| 0.0 – 1.5 s | stand | **1.708** |
| 1.5 – 2.5 s | walk around table | **1.711** |
| 2.5 – 5.5 s | pick up cup | 0.954 |
| 5.5 – 8.5 s | drink from cup | 0.145 |
| 8.5 – 10.0 s | place cup on table | 0.446 |

Lower-body motion during the `stand` label is statistically indistinguishable from the labelled walk
interval, and falls only when the subject stops at the table. The subject is walking from
approximately 0.2 s. Restricting footstep audio to 1.5–2.5 s would omit the first two of four
visible foot contacts.

Module 3 therefore searches for foot contacts across the full pre-cup region
(`WALK_SEARCH_SPAN = 0.0–2.50 s`, declared in `scripts/m3_config.py` with the motion evidence above).
**The Module 2 timeline itself is not altered — only the region in which footstep audio is placed.**

---

## 4. Audio Generation Model

### 4.1 Model

**MOSS-SoundEffect v2.0** (OpenMOSS Team) is the sole Foley generation model in the final pipeline.

| Property | Value |
|---|---|
| Hugging Face repository | `OpenMOSS-Team/MOSS-SoundEffect-v2.0` |
| Model revision | `e35df4d82fbe87fcd5d14e5d100e349c0c3c076d` |
| Source repository | `github.com/OpenMOSS/MOSS-TTS`, commit `58b20a0` |
| Licence | Apache-2.0 |
| Checkpoint size | 11.23 GB |

### 4.2 Architecture

MOSS-SoundEffect v2.0 is a **text-conditioned** audio generation model. It accepts a natural-language
description and an optional negative prompt; it does not accept video, image or audio conditioning.

| Component | Parameters | Role |
|---|---|---|
| Diffusion Transformer (DiT) | 1,416.05 M | denoiser, trained with a Flow Matching objective |
| Qwen3 text encoder | 1,720.57 M | encodes the prompt (hidden size 2048) |
| DAC VAE | 371.59 M | decodes the latent to a 48 kHz waveform |
| **Total** | **3,508.21 M** | |

Output is **48 kHz mono**, with a maximum generation length of 30 seconds.

### 4.3 Duration handling

The pipeline **always denoises a fixed-size latent corresponding to 30 seconds** and crops the result
to the requested duration. Duration is communicated to the model as text — the string
`" duration: 10.0s"` is appended to the prompt, matching the training-time convention.

A practical consequence is that requesting a short output does not reduce computation, and does not
push the model outside its trained regime. All Module 3 generations requested 10 seconds.

### 4.4 Local execution on Apple Silicon

| Property | Value |
|---|---|
| Hardware | Apple M4, 17.18 GB unified memory |
| Operating system | macOS 26.2 (Darwin 25.2.0), arm64 |
| Python | 3.12.13 |
| PyTorch | 2.9.1 (default PyPI build; `torch.version.cuda` is `None`) |
| Compute device | MPS (Metal Performance Shaders), passed explicitly |
| Precision | bfloat16 parameters; float16 not used; CUDA not used |

MPS availability was verified before the checkpoint was downloaded. PyTorch issue #167679 reports
`MPS available: False` for torch 2.9.1 on macOS 26.0; the condition did not reproduce on macOS 26.2
and MPS was confirmed functional.

### 4.5 Memory-optimised phased inference

Loading all three components simultaneously in their as-shipped precision requires approximately
10.59 GB of resident weights, because the pipeline's `torch_dtype` argument is honoured only by the
text encoder — the DiT and VAE load in float32. On a 17.18 GB machine this produced approximately
**+9.8 GB of swap growth** during loading alone.

Module 3 therefore executes inference in three disjoint phases, with each component released before
the next is loaded:

| Phase | Component | Resident |
|---|---|---|
| 1 | Qwen3 text encoder | 3.44 GB |
| 2 | DiT | 2.85 GB |
| 3 | DAC VAE | 0.74 GB |

Parameters are cast to bfloat16 in the wrapper. This costs no inference precision: the pipeline's
own `__call__` already wraps the engine in `torch.autocast(device_type, dtype=torch.bfloat16)`, so
the forward pass computes in bfloat16 regardless of how weights are stored.

Measured effect, verified on the walking generation:

| Metric | All-resident (as shipped) | Phased + bfloat16 |
|---|---|---|
| Swap growth | +9.80 GB | **+0.01 GB** |
| Peak RAM | — | 11.68 GB |
| Minimum available RAM | — | 1.85 GB |
| Memory guard breach | — | none |

### 4.6 Wrapper-level MPS compatibility handling

Two compatibility issues were resolved **outside** the MOSS source tree:

**(a) Rotary position embeddings.** The DiT carries three complex128 RoPE tables
(`freqs_cis_0`, `freqs_cis_1`, `freqs_cis_2`). A blanket `.to(dtype=bfloat16)` discards their
imaginary component, silently destroying rotary encoding. The wrapper casts **parameters only**,
leaving buffers at their original dtype; the tables are downcast to complex64, which is lossless for
this use because `rope_apply` reads `.real` and `.imag` at float32.

**(b) `sinusoidal_embedding_1d`.** This function computes in float64, which MPS does not support.
The wrapper redirects that computation to CPU in three modules
(`wan_video_dit`, `wan_audio_dit`, `wan_audio`). Verified numerically identical to the upstream CPU
result: `max_abs_diff = 0.0`, `exact_match = true`.

**No file inside the MOSS repository was modified.** Repository cleanliness is asserted by
`git status --porcelain` returning empty in every build.

---

## 5. Prompts

All three generations used identical sampler settings: **seed 42, 50 inference steps, cfg_scale 4,
sigma_shift 5, 48 kHz mono, 10 s output (30 s denoised internally)**.

The full prompt text is reproduced in `04_PROMPTS_REFERENCE.md`. Summary:

| Action | Positive prompt | Negative prompt |
|---|---|---|
| Drinking | close-up sipping/swallowing from a ceramic mug, negations carried inline | *(empty)* |
| Walking | footsteps on a hard wooden floor, alternating heel/toe impacts | 15 terms |
| Cup placement | one ceramic-on-wood contact with short wooden resonance | 23 terms |

Two observations recorded during development, both supported by measurement:

- The drinking prompt used an **empty** negative prompt, with its negations written into the positive
  prompt. This is the configuration that produced the approved result.
- A cup-pickup attempt using a 24-term negative prompt produced degenerate output (peak −61.7 dBFS,
  1.06 dB dynamic range, 95 % harmonic content). Output level tracked negative-prompt length across
  the two attempts (17 terms → −36.0 dBFS; 24 terms → −61.7 dBFS). This is a two-point observation,
  not an established relationship, and it was not acted upon.

---

## 6. Audio Processing

Each generation produces 10 seconds of audio containing more material than a single action requires.
Module 3 selects the useful portion and prepares it for mixing.

### 6.1 Segment selection

| Action | Selection method | Source range used |
|---|---|---|
| Walking | continuous slice containing a run of four consecutive footsteps whose spacing matches the filmed gait | 0.498 – 2.839 s |
| Drinking | two isolated sip/swallow segments chosen by wet-band dominance (≥45 % energy in 200 Hz–1 kHz) and isolation from neighbouring transients | 8.976 – 9.676 s and 1.601 – 2.301 s |
| Cup placement | one contact-plus-resonance cluster, selected for the highest peak and the cleanest cut edges (−39.6 dB relative to the cluster peak) | 6.150 – 6.550 s |

The placement selection is stored as a derived asset,
`audio/generated/cup_placement_foley_final.wav` (400 ms), leaving the 10-second source unmodified.

### 6.2 Post-processing chain

Applied to each clip, in order:

| Stage | Setting | Purpose |
|---|---|---|
| DC removal | per-clip mean subtraction | removes offsets of order 1×10⁻⁴ |
| Zero-crossing snap | nearest crossing within ±3 ms | eliminates edit discontinuities at source rather than masking them |
| Fades | 12 ms raised cosine, in and out | continuous in slope, unlike a linear ramp |
| Level | active-RMS balancing | see §6.3 |
| Peak cap | −12 dBFS per clip | prevents any single clip dominating the bus |

Applied per-clip zero-crossing corrections were between −0.021 ms and +0.167 ms.

### 6.3 Level balancing

Levels are set by **active RMS** — the RMS of frames above each clip's own 60th-percentile level,
which ignores the silent portions that would otherwise bias a whole-file RMS measurement. Peak
normalisation was rejected because a transient impact and a sustained sip with the same peak are not
perceptually equal in loudness.

| Action | Measured active RMS | Target | Gain applied |
|---|---|---|---|
| Walk around table | −30.5 dBFS | −34.0 dBFS | **−4.05 dB** (peak cap engaged) |
| Drink from cup (1) | −46.0 dBFS | −38.0 dBFS | **+7.95 dB** |
| Drink from cup (2) | −46.8 dBFS | −38.0 dBFS | **+8.75 dB** |
| Place cup on table | −45.3 dBFS | −32.0 dBFS | **+13.27 dB** |

### 6.4 Bus processing

| Stage | Value |
|---|---|
| Summed peak before processing | −12.00 dBFS |
| Normalisation | **+6.00 dB, purely linear** |
| Normalisation target | −6.00 dBFS |
| Safety limiter threshold / ceiling | −6.0 / −3.0 dBFS |
| **Limiter gain reduction** | **0.00 dB — the limiter did not engage** |
| Final peak | −6.00 dBFS |
| Final RMS | −36.87 dBFS |
| Crest factor | 30.87 dB |

The limiter exists as protection against future changes producing an overshoot. Because it did not
engage, **no dynamic-range processing of any kind was applied**, and the inter-clip balance in §6.3
is exactly what is present in the output. A crest factor of 30.87 dB confirms transient structure is
intact.

### 6.5 Boundary handling

The placement clip would have extended to 10.098 s, beyond the video. Its tail was truncated by
**93.1 ms** with a fade rather than extending the timeline. This is a physical consequence of the
video ending while the mug's resonance is still decaying.

---

## 7. Visual Synchronisation

This is the central technical component of Module 3. Audio is aligned to measured visual events,
not to Module 2 action start times.

### 7.1 Frame analysis method

Frames are decoded with ffmpeg to a 320×180 greyscale raw stream at 24 fps (240 frames). Motion is
computed as the mean absolute inter-frame difference within a horizontal band:

| Band | Frame-height fraction | Used for |
|---|---|---|
| Feet | 0.62 – 1.00 | foot plants |
| Head | 0.00 – 0.50 | sip holds |
| Table | 0.40 – 0.85 | mug-table contact |

The feet band was selected empirically: across three prominence thresholds it recovered all four foot
plants, whereas a taller 0.55–1.00 band recovered only two at the default threshold.

### 7.2 Alignment anchor: true attack, not onset strength

An error identified and corrected during development is documented here because it materially affects
accuracy. The planner initially aligned **onset-strength peaks**, which lag or lead the actual
transient attack by −96 ms to +250 ms. Aligning a strength peak to a visual event therefore misplaces
the audible transient by that lag; a measured case was asset step "3.760 s", whose true attack is at
3.856 s, producing a 96 ms error in the rendered audio.

Onsets are now computed as **true envelope attack times**: each amplitude-envelope maximum is
back-tracked to the point where the envelope last rose through 20 % of that maximum.

### 7.3 Walking

A step is a leg swing (a prominent motion peak) resolving into a plant (the following local minimum).
The plant is the audible contact. Prominence-based peak detection is used; a simple threshold admits
low-amplitude ripples between real steps as false positives.

**Four foot plants were identified:**

| Plant | 0.458 s | 1.083 s | 1.667 s | 2.208 s |
|---|---|---|---|---|
| Interval from previous | — | 0.625 s | 0.584 s | 0.541 s |

The gait is natural and slightly decelerating. The generated walking Foley has its own cadence of
approximately 108 steps per minute.

**Alignment procedure.** Every consecutive run of four footsteps in the generated asset is scored on
how closely its internal spacing matches the four visible intervals. The best-matching run
(0.797, 1.403, 2.014, 2.560 s) is translated so its first step lands on the first visible plant.

**The clip is shifted only.** No time-stretching, resampling, or regeneration is performed. Residual
error is absorbed rather than corrected, because correcting it would require altering the approved
audio.

**Measured result on the rendered audio:**

| Visible plant | Rendered attack | Error |
|---|---|---|
| 0.458 s | 0.458 s | −0 ms |
| 1.083 s | 1.063 s | **−20 ms** |
| 1.667 s | 1.675 s | +8 ms |
| 2.208 s | 2.221 s | +13 ms |

The −20 ms residual reflects the difference between the generated cadence and the filmed gait.

### 7.4 Drinking

A sip is the mug held at the lips — a **sustained low-motion period** in the head region, bounded by
the raise and lower movements. Sip holds are therefore detected as motion minima, not peaks. This is
consistent with the drinking interval having the lowest mean motion of any action in the video (0.145
in the feet band, 0.386 in the head band).

Two sip holds were identified, at **6.625 s** and **7.792 s**. One isolated sip/swallow segment from
the approved drinking asset is placed per hold, each aligned by its own onset.

| Visible event | Rendered attack | Error |
|---|---|---|
| 6.625 s | 6.638 s | +13 ms |
| 7.792 s | 7.803 s | +11 ms |

### 7.5 Cup placement

Contact is detected as the final significant motion peak in the table region before motion collapses
to rest, at **9.833 s**.

The 400 ms contact segment is used rather than the full 10-second recording, with its attack aligned
to the visible contact.

| Visible event | Rendered attack | Error |
|---|---|---|
| 9.833 s | 9.833 s | −0 ms |

---

## 8. Final Mix

The four placements are summed into a single 48 kHz mono timeline matching the video duration.

**Why Foley events should not share a common loudness.** Equal-loudness normalisation would be
acoustically incorrect. In the filmed scene, a mug set on a hard table is the most percussive event;
footsteps are mid-ground; a sip at the mouth is intimate and quiet. Normalising all three to the same
level would place the sip at the loudness of a footstep, which does not correspond to any real
recording position.

The mix therefore targets a *scene-appropriate* balance (§6.3): drinking sits 4 dB below walking and
6 dB below the placement in active RMS terms. Gains remain within a −4.05 dB to +13.27 dB range, and
no per-asset dynamic processing is applied.

Actions with no approved Foley contribute nothing to the mix and are recorded explicitly as
unavailable. No audio bleeds into their intervals; this is verified automatically.

---

## 9. Final Output

| Artefact | Path | Specification |
|---|---|---|
| **Final video** | `output/final_silent_to_audio_polished.mp4` | 10.000 s video (240 frames, 1280×720, h264, stream-copied) + AAC 48 kHz mono |
| **Final audio** | `audio/mixed/final_synchronized_audio_polished.wav` | 10.005 s, 48 kHz, mono, PCM_16 |

Measured properties of the final audio:

| Property | Value |
|---|---|
| Sample rate | 48,000 Hz |
| Channels | 1 (mono) |
| Bit depth | 16-bit PCM |
| Duration | 10.005 s |
| Peak | −6.00 dBFS |
| RMS | −36.87 dBFS |
| Crest factor | 30.87 dB |
| Samples at or above full scale | 0 |
| NaN / Inf | 0 / 0 |

The AAC track inside the MP4 reports 9.984 s against a 10.000 s video stream; the difference is AAC
frame granularity and is within the 150 ms tolerance applied by the automated duration check.

Earlier build outputs (`final_silent_to_audio.mp4`, `final_synchronized_audio.wav`) are retained
unmodified for comparison.

---

## 10. Limitations

These are stated explicitly and are not resolved in the current implementation.

### 10.1 Cup pickup has no approved Foley — that interval is silent

**No usable cup-pickup sound was obtained. The 2.5–5.5 s interval contains no audio.**

Three approaches were attempted and all were rejected on measured evidence:

| Attempt | Result | Evidence |
|---|---|---|
| MOSS generation v1 | UNCERTAIN, not approved | peak −36.0 dBFS; 1.68 % of energy in 1–5 kHz |
| MOSS generation v2 | FAIL | peak −61.7 dBFS; 40 distinct sample values; 1.06 dB dynamic range; 95 % harmonic content |
| Extraction from the approved drinking asset | NOT VIABLE | the single qualifying transient is a lip-contact tink, not a table-contact-and-lift sequence |

For reference, the approved drinking asset — recorded from the same ceramic mug — contains **28.96 %**
of its energy in the 1–5 kHz band that characterises ceramic contact. Neither pickup attempt exceeded
1.68 %, which is indistinguishable from the walking asset's 1.63 %, and that asset contains no ceramic
at all.

The interval is recorded as unavailable in `final_synchronization_polished.json`, and an automated
check asserts that no audio is written there. **No substitute sound was fabricated.**

### 10.2 Cup placement was accepted on measurement, not on listening

The cup-placement asset was assessed as UNCERTAIN. It contains **0.52 %** of its energy in the
1–5 kHz band, against 28.96 % for the drinking asset from the same mug; its strong impacts have
dominant frequencies between 70 and 398 Hz. The measurements indicate a low wooden knock rather than
a ceramic-on-wood contact. It is included in the final mix as instructed. If it is judged unsuitable
on listening, the correction belongs in the asset, not in the synchronisation code.

### 10.3 Visual event confidence is not uniform

The four walking foot contacts are classified `high` confidence — they are prominent, well-separated
motion features. Drinking sip holds and the mug-table contact are `medium` confidence: they derive
from motion minima and from a final motion peak respectively, neither of which is as sharply defined.

### 10.4 Method scope

Visual localisation is motion-based, not object-tracking or pose-estimation based. It has been
validated on one 10-second video. Generalisation to other footage, camera angles, or subjects has
not been established.

---

## 11. Technical Contribution

The following distinguishes this implementation from attaching pre-recorded sound effects to a video.

| Contribution | Description |
|---|---|
| **Action-aware Foley generation** | Sounds are generated from text descriptions derived from Module 2's recognised actions, not selected from a sound library. |
| **Visual-event-aware synchronisation** | Audio is aligned to measured visual events, not to action-label boundaries. Frame-level motion analysis in region-specific bands locates foot plants, sip holds, and mug-table contact. |
| **Temporal alignment on true attack times** | Alignment uses envelope attack times rather than onset-strength peaks, removing a systematic error of up to 250 ms. |
| **Cadence-preserving placement** | For walking, a consecutive run of generated footsteps is matched to the filmed gait and translated into position. Audio is shifted, never time-stretched, so the generated cadence is preserved. |
| **Automatic segment selection** | Useful portions are selected from 10-second generations by measured criteria — wet-band dominance for sips, peak and edge-cleanliness for contact events. |
| **Automated mixing** | Level balancing by active RMS with a documented scene rationale, zero-crossing-safe cuts, raised-cosine fades, and transparent normalisation. |
| **Memory-constrained local inference** | A 3.5 B-parameter model executed on a 17.18 GB consumer laptop through phased loading, reducing swap growth from +9.80 GB to +0.01 GB, with no modification to the model repository. |
| **Objective QA verification** | 19 automated checks covering synchronisation accuracy measured on the rendered audio, clipping, NaN/Inf, duration, sample rate, edit-boundary discontinuities, dynamic range, and source-asset integrity by SHA-256. |
| **Explicit failure reporting** | Actions without a usable sound are left silent and documented rather than filled with a substitute. |

---

## 12. Reproducibility

The complete pipeline is rebuilt with a single command:

```bash
moss/venv-moss/bin/python scripts/run_module3.py
```

This executes ten stages in order: derive the placement asset, localise visual events, build the
synchronisation plan, mix, build the video, run the quality gate, write reports, polish the mix,
build the polished video, run the polished QA, and write the polished report.

The build is deterministic given the same inputs: the visual analysis is deterministic, all sampler
seeds are fixed at 42, and audio processing involves no stochastic stages. The Foley assets are not
regenerated by this command — they are read from `audio/generated/`.

### Environment

| Component | Version |
|---|---|
| Python | 3.12.13 (`moss/venv-moss`) |
| PyTorch | 2.9.1 |
| torchaudio | 2.9.1 |
| numpy | 1.26.4 |
| transformers | 4.57.1 |
| diffusers | 0.37.1 |
| descript-audiotools | 0.7.2 |
| soundfile, librosa, scipy | as pinned in the environment |

`flash-attn`, `xformers`, `triton` and `bitsandbytes` are not installed and are not required.
No NVIDIA or CUDA packages are present.

### Source-code layout

| File | Responsibility |
|---|---|
| `scripts/m3_config.py` | paths, asset registry, level targets, walking search span, unavailable-Foley declarations |
| `scripts/visual_events.py` | frame decoding, region motion analysis, per-action event localisation |
| `scripts/make_placement_asset.py` | derives the 400 ms placement asset from the 10 s source |
| `scripts/sync_actions.py` | true-attack onset detection, segment selection, alignment planning |
| `scripts/audio_mixer.py` | first-pass mix |
| `scripts/build_final_video.py` | first-pass mux |
| `scripts/analyze_sync.py` | first-pass quality gate |
| `scripts/write_reports.py` | first-pass JSON record |
| `scripts/polish_mix.py` | DC removal, zero-crossing snap, fades, active-RMS balance, normalisation, safety limiter |
| `scripts/build_polished_video.py` | final mux (`-c:v copy`) |
| `scripts/qa_polished.py` | final quality gate, sync measured on rendered audio |
| `scripts/write_polished_report.py` | final JSON record |
| `scripts/run_module3.py` | orchestrator |

---

## 13. Verification Summary

All checks were executed against the final artefacts. Full detail is in `05_RESULTS_AND_QA.md`.

| Category | Result |
|---|---|
| Final MP4 integrity | pass — 2 streams, opens correctly |
| Video duration preserved | pass — 10.005 s → 10.000 s |
| Video stream untouched | pass — 240 frames, stream-copied |
| Audio/video duration match | pass — within tolerance |
| Sample rate | pass — 48,000 Hz |
| Channel count | pass — mono |
| Clipping | pass — 0 samples at or above full scale |
| NaN / Inf | pass — none |
| Walking synchronisation | pass — −0 / −20 / +8 / +13 ms |
| Drinking synchronisation | pass — +13 / +11 ms |
| Placement synchronisation | pass — −0 ms |
| Edit-boundary discontinuities | pass — all 8 boundaries clean |
| Bleed into silent intervals | pass — none |
| Cup pickup unavailability | pass — silent and documented |
| Dynamic range | pass — limiter gain reduction 0.00 dB |
| Crest factor | pass — 30.87 dB |
| Source video integrity | pass — SHA-256 unchanged |
| Approved asset integrity | pass — both assets unchanged |
| Earlier outputs preserved | pass — not overwritten |

**Worst synchronisation error across all events: 20 ms.**

For context, the video is 24 fps, so one frame is 41.7 ms. All alignment errors are below half a
frame interval.

---

*End of technical documentation.*

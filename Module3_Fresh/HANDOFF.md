# PROJECT HANDOFF — Action Recognition and Sound Generation

Paste this whole file as the first message in a new session.

---

## WHO I AM AND WHAT THIS IS

Final-year engineering project: **ACTION RECOGNITION AND SOUND GENERATION** —
"Transform silent videos into synchronized sound". A web app that takes a silent video,
recognises the actions in it, generates matching Foley audio, aligns each sound to the
exact frame where the action is visible, mixes it, and returns a playable video.

Machine: **Apple M4, 17.18 GB RAM, macOS 26.2, MPS only** (no CUDA anywhere).
Project root: `/Users/bilalashfaque/Desktop/Silent-Video-Project/`
Working directory for everything: `Module3_Fresh/`

---

## READ THIS BEFORE TOUCHING ANYTHING

These are hard constraints established over the whole project. Violating them destroys
validated work.

**NEVER modify:**
- `moss/MOSS-TTS/` — the MOSS repository. Must stay pristine (`git status --porcelain`
  returns empty). All compatibility fixes live in wrappers outside it.
- `audio/generated/drinking_moss_v2_local_seed42.wav` and
  `audio/generated/walking_moss_v1_seed42.wav` — approved by listening, filesystem
  write-protected (`r--r--r--`), hashes recorded in `results/APPROVED_ASSETS.lock`.
- `input/test_video.mp4` — source video, SHA-256 `a620ee5820ab9dfc…`
- `output/final_silent_to_audio_polished.mp4` and
  `audio/mixed/final_synchronized_audio_polished.wav` — the validated Module 3 build.
- `module2/module2_action_segments.json` — Module 2 output.
- These virtual environments: `venv-qwen`, `venv-foley`, `venv-stable-audio`,
  `venv-audioldm2`, `venv-mmaudio`. They may be **run** but never modified, and no
  packages may be installed into them.

**Always verify after changes:**
```bash
cd /Users/bilalashfaque/Desktop/Silent-Video-Project/Module3_Fresh
shasum -a 256 -c <(grep -E '^[a-f0-9]{64}' results/APPROVED_ASSETS.lock)
(cd moss/MOSS-TTS && git status --porcelain)   # must be empty
```

---

## CURRENT STATE — ALL WORKING

- **59 automated tests pass** (36 main suite + 22 quality-gate + 1 E2E gate).
- Frontend builds clean (TypeScript strict).
- Full pipeline works end-to-end on new uploaded videos with live action recognition.

Run it:
```bash
# terminal 1 — backend
moss/venv-moss/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# terminal 2 — frontend
cd frontend && npm run dev        # http://localhost:5173
```

Tests:
```bash
moss/venv-moss/bin/python backend/tests/test_suite.py             # 36
moss/venv-moss/bin/python backend/tests/test_foley_validation.py  # 22
moss/venv-moss/bin/python backend/tests/e2e_gate.py               # cached E2E, ~5s
```

**IMPORTANT: restart the backend after any code change.** A running uvicorn holds old
code in memory — this already caused one confusing debugging session where a fix
appeared not to work.

---

## ARCHITECTURE

```
SILENT VIDEO → VALIDATION → MODULE 2 (action recognition) → ACTION TIMELINE
→ MODULE 3 (Foley generation) → FOLEY QUALITY VALIDATION → VISUAL EVENT LOCALIZATION
→ TEMPORAL ALIGNMENT → AUDIO MIXING → FFMPEG MUX → FINAL VIDEO
```

Nine stages, all reporting real backend progress (no fake progress bars).

**Three isolated processes.** Models run as subprocesses, never imported into the API
process — they need incompatible Python/torch versions and each peaks near 12 GB.

| Component | Environment | Model |
|---|---|---|
| Backend + Module 3 | `moss/venv-moss` (Python 3.12, torch 2.9.1) | MOSS-SoundEffect v2.0 |
| Module 2 | `.../qwen/venv-qwen` (Python 3.10, torch 2.13) | Qwen2.5-VL-3B-Instruct |
| Alternative backend | `.../stable-audio/venv-stable-audio` | Stable Audio Open 1.0 |

**Key files:**
```
backend/
  core/config.py             paths, backend registry, defaults, limits
  core/jobs.py               job store, 9-stage state machine, background worker
  services/
    prompt_map.py            16 Foley classes; action phrase -> prompt + sync strategy
    video_service.py         ffprobe validation
    action_recognition.py    subprocess -> venv-qwen
    sound_generation.py      subprocess -> backend; cache; multi-candidate selection
    foley_validation.py      quality gates + 0-100 score
    synchronization.py       frame motion -> visual events -> alignment plan
    audio_processing.py      per-clip polish, bus mix, normalisation, safety limiter
    video_render.py          ffmpeg mux (-c:v copy)
    pipeline.py              stage orchestration
  runners/
    run_module2.py           executed by venv-qwen; imports validated Module 2 code
    run_stable_audio.py      executed by venv-stable-audio
frontend/src/                React 18 + Vite 6 + TypeScript + Tailwind
scripts/                     validated Module 3 sync implementation (reused, not rewritten)
data/{uploads,jobs,generated,outputs}
docs/{architecture,api,pipeline,deployment}.md + README.md
results/documentation/       6-document Module 3 engineering package
```

---

## CRITICAL DESIGN DECISIONS AND WHY

These were learned the hard way. Do not undo them without strong reason.

**1. Audio is aligned to measured visual events, not action-label boundaries.**
Module 2 gives spans ("walking, 1.5–2.5 s") but Foley is an instant. Frame-level motion
analysis finds the actual moment. This is the core contribution of the project.

**2. Alignment uses TRUE ENVELOPE ATTACK times, not onset-strength peaks.**
Onset-strength peaks lag/lead the real transient by −96 to +250 ms. This caused a real
96 ms misalignment before it was fixed. Attack = envelope maximum back-tracked to where
it last rose through 20% of that maximum.

**3. Clips are SHIFTED, never time-stretched.** Where the generated cadence differs from
the filmed one, the residual is absorbed and reported.

**4. The `resolved_actions` array is used, never the raw `actions` array.** The raw one
overlaps by one stride, which is ambiguous for audio placement.

**5. Levels are set by ACTIVE RMS per class, not peak-matched.** A mug on a table is
percussive, footsteps mid-ground, a sip intimate. Equal loudness would be wrong.
The per-clip peak cap is −6 dBFS and is an OUTLIER GUARD ONLY — at −12 dBFS it was
binding on most clips and flattening inter-event dynamics.

**6. Quality gates are multi-criteria on purpose.** Single metrics mislead: one Stable
Audio candidate had 63.7% ceramic-band energy (more than the winner) but 1.3 dB dynamic
range — it was hiss. Gates: effective bits ≥ 9, dynamic range ≥ 6 dB, not a sustained
tone, not a pure tone (harmonic > 0.90 with flatness < 0.01), gain ≤ +25 dB.

**7. Multi-candidate generation.** Up to 3 seeds per class, stop early when one scores
≥ 45. Rescued cup pickup: seeds 42 and 43 failed, seed 44 passed with score 85.8. It was
a sampling failure, not a capability limit. A class that works first time costs one
generation.

**8. Nothing is fabricated.** An action with no usable Foley is left SILENT and reported
as `no_usable_foley` with measured values. Never filled with a substitute.

---

## MODEL DECISION — SETTLED, DO NOT REOPEN

**MOSS-SoundEffect v2.0 is the chosen model.** Confirmed by listening after a full A/B
against Stable Audio Open 1.0 through the identical pipeline.

Measured comparison (harmonic ratio is the discriminator — Foley must be inharmonic):

| Class | MOSS score / harmonic | Stable Audio score / harmonic |
|---|---|---|
| Walking | 97.1 / **0.00** | 92.7 / 0.03 |
| Drinking | 70.9 / **0.06** | 75.6 / 0.09 |
| Cup pickup | 85.8 / **0.00** | 53.1 / **0.88** |
| Cup placement | 49.8 / **0.02** | 53.4 / **0.87** |

Stable Audio produced *musical tones* for object contacts (one output was a pure 346 Hz
sine wave for "cup placed on table"). It is faster (66 s vs ~4 min per asset) and fine on
walking/drinking, but wrong for object Foley.

Stable Audio remains available: `FOLEY_BACKEND=stable_audio`. Default is `moss`.

**Previously evaluated and rejected:** Stable Audio Open Small, AudioLDM 2, FoleyCrafter,
MMAudio. Do not re-evaluate these. Do not download new models.

MOSS settings (validated, do not change without reason): seed 42, 50 steps, cfg_scale 4,
sigma_shift 5, 48 kHz mono, 10 s output (30 s denoised internally then cropped).

---

## KNOWN LIMITATIONS — STATE THESE HONESTLY, DO NOT HIDE

1. **Module 2 is the weakest link.** On a coffee-stirring test video it missed the cup
   placement entirely, emitted one stirring action under three different labels, and
   produced a caption ("Stirring a cup of coffee") rather than an action. Module 3 can
   only sound as good as that timeline. **This is where remaining quality gains are.**
2. **Output is sparse by nature** — roughly 18% of a 10 s timeline has audio for discrete
   object interactions. Silence between events is correct.
3. **Audio will not be "perfect."** A 1.3B text-to-audio model on a laptop has a ceiling.
   Walking and drinking are good; small quiet ceramic contacts are the hardest class.
4. **Apple Silicon only.** No CUDA or CPU path.
5. **Single-machine demonstrator** — no auth, no queue, no multi-user isolation.
6. **Validated on limited footage.** Visual localisation is motion-based, not pose or
   object tracking.

---

## BUGS ALREADY FOUND AND FIXED — DO NOT REINTRODUCE

- Onset-strength peaks used as alignment anchors (96 ms error) → true envelope attacks.
- `resolve_boundaries` returns `(segments, adjustments)`; assigning the tuple broke
  Module 2 on the live path.
- Bare `"place"`/`"pick"` keywords matched the wrong object — "place spoon on table" got
  ceramic-mug Foley. Every keyword now names its object; generic fallback classes are
  tried only after specific ones (specificity beats keyword length).
- Cache key was type-sensitive: `duration: 10` vs `10.0` produced different keys and
  regenerated identical audio. Numerics are normalised before hashing.
- `active_rms` collapsed to whole-file RMS when a clip was >60% digital silence.
- Dynamic range returned 183–201 dB (impossible for 16-bit) when files contained exact
  digital silence, scoring full marks. Now measured over signal-bearing frames, capped 96 dB.
- Tonality gate missed a pure 346 Hz sine because it required low dynamics too.
  Independent pure-tone gate added.
- Degenerate assets were amplified +48 dB, turning quantisation noise into audible hiss.
  Quality gate + hard +25 dB mixer limit added.
- Consecutive same-class intervals each replayed the SAME 1 s source segment (audible
  loop). Continuous activities are now merged into one span; discrete contacts are NOT
  merged (that lost a visual event when tried).
- `continuous` strategy placed audio at the label edge instead of the measured motion
  onset.
- End-of-video fragments below 45% of a clip are omitted rather than clipped to a click.
- `apg_scale` must be 0.0 for Stable Audio on MPS (library default 1.0 needs float64).

---

## WHAT TO DO NEXT (my recommendation, in order)

1. **Deliverables for submission** — the system works and is documented; what's likely
   missing is a project report, presentation slides, or a rehearsed demo script.
2. **Module 2 improvement** — biggest remaining quality lever. Prompt engineering on the
   Qwen side plus label normalisation (dedupe, strip caption phrasing). Work in a copy;
   never modify the validated Module 2 output.
3. Leave the audio alone unless something is measurably broken.

---

## HOW TO WORK ON THIS PROJECT

- Inspect before changing; reuse existing validated code rather than rewriting.
- Run the tests before and after every change.
- Restart the backend after code changes.
- Measure claims — do not assert audio quality without evidence.
- I (the user) am the authority on whether audio sounds right. Objective metrics support
  that judgement, they do not replace it.
- Be honest about failures and limitations rather than presenting partial success.

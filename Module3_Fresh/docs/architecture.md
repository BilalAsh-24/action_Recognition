# Architecture

## Overview

Three processes, isolated by design:

| Process | Runtime | Responsibility |
|---|---|---|
| Frontend | Node / browser | UI, upload, polling, presentation |
| Backend | Python 3.12 (`venv-moss`) | orchestration, sync, mixing, rendering, REST |
| Model runners | `venv-qwen` (3.10) and `venv-moss` (3.12) | Module 2 and Module 3 inference |

Models are invoked as **subprocesses**, never imported into the API process. Three
consequences follow, all deliberate:

1. **Memory isolation.** Qwen2.5-VL peaks near 12 GB and MOSS near 11.7 GB. Neither can
   leak into the long-lived API process, and process exit returns memory to the OS
   unconditionally — more reliable than garbage collection plus `torch.mps.empty_cache()`.
2. **Dependency isolation.** Module 2 needs Python 3.10 with torch 2.13; MOSS needs
   Python 3.12 with torch 2.9.1. These cannot coexist in one interpreter.
3. **Failure isolation.** A model crash returns a non-zero exit code and is converted to
   a readable message. It cannot take the server down.

## Backend layers

```
api/routes.py        HTTP surface; validation and error mapping only
core/jobs.py         job store, state machine, background worker, disk persistence
core/config.py       paths, interpreters, defaults, limits
services/
  video_service       probe + validation (ffprobe)
  action_recognition  subprocess -> venv-qwen  -> Module 2 JSON
  prompt_map          action phrase -> Foley class, prompt, sync strategy
  sound_generation    subprocess -> venv-moss  -> WAV, content-addressed cache
  synchronization     frame motion -> visual events -> alignment plan
  audio_processing    per-clip polish, bus mix, normalisation, safety limiter
  video_render        ffmpeg mux, video stream copied
  pipeline            stage orchestration, progress reporting
runners/
  run_module2.py      executed by venv-qwen; imports the validated Module 2 algorithm
```

## Reuse of the validated implementation

The web application does not reimplement any algorithm that already existed:

| Component | Reused from |
|---|---|
| Qwen windowing, prompt, response parsing, action-head extraction, merging | `03-FoleyCrafter-Test/action-recognition/action_recognition.py` |
| Boundary resolution, suspect flagging, timeline validation | `.../resolve_segments.py` |
| Frame decode, region motion, smoothing | `scripts/visual_events.py` |
| Phased MOSS wrapper, MPS compatibility shims | `moss/scripts/moss_phased.py`, `mps_compat.py` |
| Generation driver | `moss/scripts/moss_generate.py` |

`run_module2.py` imports the validated functions and supplies a parameterised video path.
Neither the Module 2 source nor the MOSS repository is modified.

**Verification of faithfulness:** the generalised synchronisation service reproduces the
validated reference exactly — foot plants `[0.458, 1.083, 1.667, 2.208]`, sip holds
`[6.625, 7.792]`, cup contact `[9.833]`, and walking alignment errors
`[0.0, −19.9, 8.0, 12.3] ms`. This is asserted in the test suite.

## Job model

A job is a serialisable record persisted to `data/jobs/<id>.json` after every transition,
so state survives a reload and is inspectable after the fact.

```
created → queued → running → completed
                          ↘ failed
```

Eight stages, each `pending | active | done | skipped | failed`:
`upload · validation · action_recognition · timeline · foley_generation · visual_sync ·
audio_mixing · rendering`.

Progress is a real function of stage completion. Within action recognition the runner
writes a progress file each window, which the pipeline polls — the percentage reflects
actual windows processed. **No progress value is fabricated on the client.**

## Foley quality validation and candidate selection

Generated audio is not trusted. Every asset is measured **raw** — before any gain or
normalisation — and must clear six gates: effective bits ≥ 9, dynamic range ≥ 6 dB, not
a sustained tone (harmonic ratio > 0.80 combined with < 10 dB range), required make-up
gain ≤ +25 dB, finite samples, correct sample rate.

The gates are deliberately multi-criteria. A single-metric check is not enough: one
observed cup-pickup candidate had 63.7 % of its energy in the ceramic band — more than
the candidate eventually chosen — but only 1.3 dB of dynamic range, making it continuous
hiss rather than a contact sound. Judged on ceramic content alone it would have won.

Passing candidates are ranked by a 0–100 quality score combining dynamic range (40),
signal level (25), gain headroom (20) and non-tonality (15). Up to three candidates are
generated with successive seeds; the loop stops early once one scores at least 45, so a
class that works immediately costs a single generation.

A rejected class never reaches the mixer. Its interval stays silent, the measured values
and reason are recorded, the asset is kept on disk for diagnostics, and processing
continues for every other action.

The mixer holds an independent second limit: no clip is ever automatically amplified by
more than +25 dB. A clip needing more is refused rather than clamped, because clamping
still admits amplified noise.

## Foley cache

Generation is the dominant cost (~4 minutes per action). Every asset is content-addressed
by a SHA-256 over `action key + prompt + negative prompt + seed + steps + cfg +
sigma_shift + duration + sample rate`, truncated to 16 hex characters. Numeric values are
normalised before hashing — without this, a client sending `duration: 10` and a default
of `10.0` produce different keys for byte-identical audio:

```
data/generated/<action_key>_<hash>.wav
```

An identical request reuses the file. Changing any setting produces a different key and a
new generation, so the cache can never return audio that does not match its request.

## Design decisions

**Why the resolved timeline and not the raw one.** Module 2's raw spans overlap by one
stride — `pick up cup` 2.0–6.0 s and `drink from cup` 5.0–9.0 s share a second. An
instant belonging to two actions is ambiguous for audio placement. The resolved timeline
is non-overlapping and deterministic.

**Why visual events and not action boundaries.** An action interval describes a span; a
Foley event is an instant. Placing a cup-contact sound at the start of an 8.5–10.0 s
interval puts it ~1.3 s before the mug touches the table.

**Why true attack times and not onset strength.** Onset-strength peaks lag or lead the
real transient by −96 to +250 ms. Aligning a strength peak to a visual event misplaces
the audible sound by that lag. Alignment uses the amplitude envelope, back-tracked to
where it last rose through 20 % of the local maximum.

**Why shifting and never stretching.** Time-stretching alters the generated audio's
character. Where the generated cadence differs from the filmed one, the residual is
absorbed and reported rather than corrected.

**Why per-clip levels differ.** A mug meeting a table is percussive, footsteps are
mid-ground, a sip is intimate. Normalising all three to equal loudness would not
correspond to any real recording position. Levels are set by active RMS against
per-class targets.

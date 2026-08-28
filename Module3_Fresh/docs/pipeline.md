# Processing Pipeline

Eight stages. Every stage reports real state to the job store; nothing is simulated.

```
1 Video uploaded            6 Foley quality validation
2 Video validation          7 Visual synchronization
3 Action recognition        8 Audio mixing
4 Action timeline           9 Final video rendering
5 Foley generation
```

---

## 1 · Video uploaded

Streamed to `data/uploads/<uid><ext>` in 1 MB chunks with the size limit enforced during
the stream, so an oversized file is rejected before it is fully written.

## 2 · Video validation

`ffprobe` reports duration, resolution, frame rate, codec and stream inventory.

| Condition | Outcome |
|---|---|
| No video stream | rejected |
| Duration ≤ 0.4 s or > 60 s | rejected |
| Size > 200 MB | rejected |
| Extension not in the allowed set | rejected |
| **Audio track present** | **accepted with a warning** — it is never decoded |
| Resolution < 64 px | accepted with a warning |

A video that already has sound is not an error. The source audio stream is never read at
any point in the pipeline, and the output contains only generated Foley.

## 3 · Action recognition (Module 2)

Runs `backend/runners/run_module2.py` inside `venv-qwen`.

| | |
|---|---|
| Model | Qwen2.5-VL-3B-Instruct, bfloat16, MPS |
| Windows | 2.0 s wide, 1.0 s stride |
| Frames | 8 per window, resized to 448×252 |
| Decode | `ffmpeg -map 0:v:0` — video stream only |

Each window is described independently; the model returns `ACTION:` and `EVIDENCE:` lines
which are parsed into a phrase plus its verb head. A memory guard aborts cleanly if
available RAM falls below 1.5 GB. Progress is written per window and polled by the
pipeline, so the reported percentage tracks real work.

## 4 · Action timeline

Per-window predictions are merged into spans by matching action heads, then resolved into
a **non-overlapping** timeline by midpoint boundary resolution. Segments supported by few
windows are flagged `suspect` rather than deleted, and surface in the UI as *Medium*
confidence.

The raw overlapping array is deliberately not used — see `docs/architecture.md`.

## 5 · Foley generation (Module 3)

Up to three candidates are generated per class using successive seeds. Generation stops
as soon as a candidate passes quality validation with a score of at least 45, so a class
that works on the first seed costs one generation. Every candidate is cached under its
own key.


Each distinct action is resolved to a Foley class through `prompt_map.py`, which supplies
the prompt, the negative prompt, the sync strategy and the level target. Actions with no
class are recorded as unsupported and their intervals stay silent.

Generation runs `moss/scripts/moss_generate.py` inside `venv-moss`, in three
memory-separated phases:

| Phase | Component | Resident |
|---|---|---|
| 1 | Qwen3 text encoder | 3.44 GB |
| 2 | MOSS DiT | 2.85 GB |
| 3 | DAC VAE | 0.74 GB |

Parameters are cast to bfloat16; buffers are left untouched because the DiT carries
complex RoPE tables that a blanket cast would destroy. `sinusoidal_embedding_1d` is
redirected to CPU because it computes in float64, which MPS does not support. Both shims
live in the wrapper — the MOSS repository is not modified.

Output is 48 kHz mono, 10 s (30 s denoised internally, then cropped). Results are cached;
an identical request returns in seconds.

## 6 · Foley quality validation

MOSS occasionally produces degenerate output — a near-constant, near-silent tone with
almost no dynamic range. Such a file contains no usable signal, but an active-RMS
leveller will still try to raise it to its class target, applying enormous gain and
turning quantisation noise into audible hiss.

Every generated asset is therefore measured **raw**, before any gain or normalisation:
sample rate, channels, peak dBFS, active RMS, dynamic range, effective bits, spectral
flatness, harmonic ratio, and the gain the mixer would apply.

| Gate | Reject when |
|---|---|
| Effective bits | < 9.0 (peak below about −42 dBFS) |
| Dynamic range | < 6 dB |
| Tonality | harmonic ratio > 0.80 **and** dynamic range < 10 dB |
| Automatic gain | required make-up gain > +25 dB |
| Integrity | NaN/Inf, wrong sample rate, or duration < 0.05 s |

No single metric decides. A rejected asset:

- never reaches the mixer;
- has its action interval marked `no_usable_foley` and left silent;
- has its measured values and rejection reason recorded in the job result;
- remains on disk for diagnostics.

Processing continues for every other action — one unusable asset does not fail the job.
If every asset is rejected, the video is still produced with a silent track.

A second, independent limit lives in the mixer: no clip is ever automatically amplified
by more than **+25 dB**. A clip needing more is refused rather than clamped, because
clamping still admits amplified noise.

## 7 · Visual synchronization

The stage that makes the result correct rather than merely present.

Frames are decoded to 320×180 greyscale at 24 fps and motion is computed as the mean
absolute inter-frame difference within a region band:

| Band | Frame-height fraction |
|---|---|
| feet | 0.62 – 1.00 |
| head | 0.00 – 0.50 |
| table | 0.40 – 0.85 |
| full | 0.00 – 1.00 |

Detection depends on the physics of the action:

| Strategy | Method | Rationale |
|---|---|---|
| `footstep` | prominence peak → following minimum | the swing is the peak; the **plant** is audible |
| `hold` | sustained motion **minimum** | a sip is the vessel held still at the lips |
| `contact` | final motion peak before rest | the object meets the surface as movement stops |
| `continuous` | whole interval | no discrete instant to find |

Footstep search may extend beyond the labelled interval, because footsteps commonly begin
while a previous label is still active.

**Segment selection** cuts the 10 s asset down to what is needed:

| Selection | Method |
|---|---|
| `steps` | a continuous slice containing a run of footsteps whose spacing best matches the filmed gait |
| `wet_segment` | isolated segments dominated by 200 Hz–1 kHz energy, one per detected hold |
| `event` | the single contact-plus-resonance window with the highest peak and cleanest edges |
| `slice` | a continuous slice spanning the interval |

**Alignment** positions each clip so its **true envelope attack** coincides with the
visual event. Clips are shifted, never time-stretched; residual error is reported.

## 8 · Audio mixing

Per clip, in order:

| Step | Setting |
|---|---|
| DC removal | per-clip mean subtraction |
| Zero-crossing snap | nearest crossing within ±3 ms |
| Fades | 12 ms raised cosine |
| Level | active RMS against the class target |
| Peak cap | −6 dBFS (outlier guard only) |

The peak cap is a guard, not a leveller. At −12 dBFS it was binding on most clips, which
made the cap — rather than the per-class RMS targets — the thing setting relative level,
flattening the dynamics between events. Raised so RMS balancing governs.

A clip crossing the end of the video is truncated with a fade. If less than 45 % of it
would survive, it is omitted instead: a sliver of a contact sound reads as a click rather
than as the event.

Bus: sum → linear normalisation to −6 dBFS → safety limiter (threshold −6, ceiling −3).
The limiter is protection, not an effect; its gain reduction is always reported and is
normally 0.00 dB. Clips crossing the end of the video are truncated with a fade so the
timeline length is preserved.

The mix is rejected if it contains NaN/Inf or clips.

## 9 · Final video rendering

```bash
ffmpeg -i source.mp4 -i mixed.wav -map 0:v:0 -map 1:a:0 \
       -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest out.mp4
```

`-c:v copy` means the picture is **stream-copied**: not re-encoded, no quality loss, and
bit-identical to the source. Only an audio track is added.

---

## Failure handling

| Failure | User sees |
|---|---|
| Not a video | "This file could not be read as a video…" |
| Too long | "…the current limit is 60 s, because action recognition cost grows with duration." |
| Model environment missing | "The action-recognition environment is unavailable on this machine." |
| Out of memory | "…the machine ran low on memory. Close other applications and try again." |
| No supported action found | "Action recognition completed, but no supported Foley action was found. The original video can still be exported without generated audio." |
| No visual event locatable | "Foley was generated, but no visual event could be located to synchronise it to." |
| Render failure | "Final video rendering failed." |

Every failure sets the job to `failed`, marks the stage, and stores a readable message.
Full tracebacks go to the backend log only.

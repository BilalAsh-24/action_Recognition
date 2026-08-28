# MMAudio — Model Evaluation for Module 3

**Date:** 2026-08-25
**Target machine:** Apple M4, 17.18 GB unified memory, macOS (Darwin 25.2.0)
**First test case:** `drink from cup`, 5.50 – 8.50 s, 3.00 s duration
**Status:** evaluation only — nothing installed, nothing downloaded, no audio generated, no environment created.

---

## How this evaluation was performed

Everything below is derived from **direct inspection of MMAudio source and checkpoints already
present on this machine**, not from documentation claims. Specifically:

- Source read at `03-FoleyCrafter-Test/action-recognition/mmaudio/MMAudio` (upstream
  `hkchengrex/MMAudio`, commit `974010a`) — **read-only, not modified**.
- Parameter counts measured by memory-mapping the four checkpoints (`torch.load(..., mmap=True)`)
  — no model was constructed, no weights materialised.
- MPS operator/dtype support probed with tiny synthetic tensors.
- Prior-run telemetry recovered from an earlier Module 3 attempt in the same tree
  (`monitor_mmaudio.json`, `mmaudio_drinking_v1.log`, `mps_validation.json`).

Nothing in `01-Lip-Reading`, `02-Auto-AVSR-Test`, or `03-FoleyCrafter-Test` was written to.
`venv-qwen`, `venv-foley`, `venv-stable-audio`, `venv-audioldm2` were not touched.
`venv-mmaudio` was used **read-only** to run `torch.load` and op probes, with
`PYTHONDONTWRITEBYTECODE=1` and without ever importing the `mmaudio` package (so no `__pycache__`
was written into the repository).

### Material finding before we start

An earlier Module 3 attempt already downloaded every checkpoint (6.75 GB, all MD5-verified) and
**already tried this exact test case — and was killed by the memory guard.**

```
monitor_mmaudio.json:
  peak_used  12.41 GB   min_avail  0.15 GB   peak_swap  3.77 GB
  breach: "available 0.15GB < 1.5GB"   killed: true
```

That run used the all-resident official path in float32. This evaluation explains precisely why it
died and what changes to make. **The failure was memory strategy, not model incompatibility.**

---

## A. Why MMAudio is suitable for this project

**Suitable — and it is the only candidate whose architecture matches the requirement.**

Module 3 needs `VIDEO + ACTION/PROMPT → ACTION-APPROPRIATE FOLEY AUDIO`. MMAudio is built exactly
for that: it takes video and text jointly and produces temporally-aligned audio.

It uses **two separate visual encoders with different jobs**, which is what makes it right for
"drink from cup":

| Encoder | Rate | Role |
|---|---|---|
| CLIP (DFN5B ViT-H-14-384) | 8 fps | *semantic* — what the scene is (a person, a cup, a room) |
| Synchformer (MotionFormer) | 25 fps | *temporal* — when motion events happen |

Synchformer is a model trained specifically for **audio-visual synchronisation**. Its features are
computed on overlapping 16-frame segments at 25 fps, then upsampled to the audio-latent rate and
added **per-latent-frame** (`networks.py:237-248`):

```python
sync_f = sync_f.view(bs, num_sync_segments, 8, -1) + self.sync_pos_emb
sync_f = F.interpolate(sync_f, size=self._latent_seq_len, mode='nearest-exact')
```

This is genuine frame-aligned motion conditioning, not a global scene embedding. For a sip — where
the audible event must land on the actual lip/cup contact — this is the difference between usable
and unusable.

**Compared with the models already trialled in this project:**

| Model | Conditioning | Temporal alignment to motion |
|---|---|---|
| Stable Audio Open | text only | none — cannot see the video |
| AudioLDM2 | text only | none |
| FoleyCrafter | video + text | semantic adapter; weak frame-level sync |
| **MMAudio** | **video + text, joint** | **explicit, via Synchformer at 25 fps** |

The three text-only paths can only ever produce "a plausible drinking sound of about the right
length." MMAudio can produce one that lands on the right frame. Given that Module 3's whole purpose
is action-appropriate Foley, this is the correct choice.

**Verified by source inspection, not assumed:**

- Video + text conditioning is real and simultaneous — `eval_utils.generate()` encodes
  `clip_video`, `sync_video`, `text`, and `negative_text`, and all four reach the network.
- Text is optional (`--mask_away_clip`, or empty prompt), video is optional (text-to-audio mode).
  Both together is the default and intended path.

---

## B. Official model / checkpoint

Upstream: **https://github.com/hkchengrex/MMAudio** (CVPR 2025), weights at
`https://huggingface.co/hkchengrex/MMAudio`. Checkpoints are **CC-BY-NC 4.0 — non-commercial.**

Inference needs **four** components (`docs/MODELS.md`): flow-prediction network + CLIP + Synchformer
+ VAE + vocoder.

| Component | File | Size | Status on this machine |
|---|---|---|---|
| Flow net, small 44.1 kHz | `mmaudio_small_44k.pth` | 630 MB | **present, MD5 verified** |
| Flow net, large 44.1 kHz v2 *(upstream default)* | `mmaudio_large_44k_v2.pth` | 3.9 GB | not downloaded |
| 44.1 kHz VAE | `v1-44.pth` | 1.22 GB | **present, MD5 verified** |
| Synchformer visual encoder | `synchformer_state_dict.pth` | 950 MB | **present, MD5 verified** |
| CLIP DFN5B ViT-H-14-384 | HF `apple/DFN5B-CLIP-ViT-H-14-384` | 3.95 GB | **present in HF cache** |
| BigVGAN v2 44 kHz vocoder | HF `nvidia/bigvgan_v2_44khz_128band_512x` | 490 MB | **present in HF cache** |

**Nothing needs to be downloaded.** Total already on disk: ~11.2 GB.

**For 44.1 kHz specifically:** the mode is set by the VAE + vocoder, not the flow net — `v1-44.pth`
plus BigVGAN-v2-44kHz give 44.1 kHz output for any `*_44k` variant. `CONFIG_44K` confirms
`sampling_rate=44100`.

**Recommended variant for us: `small_44k`.** Upstream defaults to `large_44k_v2`, but on a 17.18 GB
machine the large net costs ~3.9 GB against small's 0.63 GB — a 3.3 GB penalty in the exact
resource we are short of. `small_44k` is already downloaded and verified. Upstream's own note is
that `_v2` "performs worse in benchmarking... but generalizes better to new data," so the quality
ordering is not clean-cut anyway. Start small; escalate only if quality demands it.

---

## C. Input requirements

**Video.** Any `pyav`-readable container. Two behaviours matter:

1. **The AAC track is never touched.** `read_frames()` (`av_utils.py:53-90`) opens only
   `container.streams.video[0]` and demuxes only that stream. The audio stream is not decoded, not
   read, not passed anywhere. **Video-only conditioning is guaranteed by construction, not by
   convention.** Our `test_video.mp4` has an AAC track; it is irrelevant.

2. **`load_video()` always reads from t=0.** The call is hard-coded
   `read_frames(..., start_sec=0, end_sec=duration_sec, ...)` (`eval_utils.py:243`). There is **no
   start-offset parameter.** To condition on 5.50–8.50 s you must **pre-cut that span into its own
   clip file** with ffmpeg first. (The earlier attempt did exactly this —
   `work/drink_clip_5.5_8.5.mp4`.) This is easy to miss and produces silently wrong conditioning if
   missed.

Internal preprocessing: CLIP branch → 8 fps, resize 384×384, `[0,1]`. Sync branch → 25 fps, resize
short side 224, centre-crop 224, normalised to `[-1,1]`.

**Text.** Plain string prompt plus optional negative prompt, both encoded by CLIP's text tower.

**Duration — a real caveat.** Trained at 8 s. README: *"a large deviation from the training duration
may result in a lower quality."* Our segment is 3.00 s. Worse, cutting 5.50–8.50 from a 24 fps
source yields only **2.96 s** of frames, and `load_video` silently truncates to the shorter branch:

```
WARNING: Sync video is too short: 2.96 < 3.00
WARNING: Truncating to 2.96 sec
```

See §N for how to handle this.

---

## D. Expected output

- Mono float32 waveform at **44,100 Hz**, shape `(1, num_samples)`.
- `demo.py` writes `.flac` and, unless `--skip_video_composite`, muxes an `.mp4`.
- **`reencode_with_audio()` writes a new MP4 containing only the generated audio** — the original
  AAC is discarded, never mixed. Note it *re-encodes* the video (h264, 10 Mbps), so it is
  generation-quality-lossy on the picture; for Module 3 we should mux with ffmpeg `-c:v copy`
  instead and leave the original video stream bit-exact.
- Latent length for 3.0 s: `ceil(3.0 × 44100 / 512 / 2)` = **130** (the 2.96 s actual gave 128).

---

## E. MPS compatibility

**Supported in code; explicitly unsupported in policy.**

`demo.py:70-76` has a first-class MPS branch:

```python
if torch.cuda.is_available():      device = 'cuda'
elif torch.backends.mps.is_available(): device = 'mps'
```

This was added in response to GitHub issue #17 "Mac support" (closed completed, Dec 2024). But the
README states plainly: **"We have only tested this on Ubuntu."** So MPS is a supported code path
with no upstream testing guarantee — any numerical or op-coverage problem is ours to find.

**We tested the op coverage ourselves.** Every operator on MMAudio's inference path, in all three
dtypes on this machine (torch 2.7.1):

| Op | fp32 | bf16 | fp16 |
|---|---|---|---|
| matmul | ok | ok | ok |
| `scaled_dot_product_attention` | ok | ok | ok |
| `nn.RMSNorm` | ok | ok | ok |
| Conv1d | ok | ok | ok |
| Conv2d (ViT patch embed, 384²) | ok | ok | ok |
| `interpolate(mode='nearest-exact')` | ok | ok | ok |
| ConvTranspose1d (BigVGAN upsample) | ok | ok | ok |

Two specific hazards checked and cleared:

- **`torch.amp.autocast(device_type='cuda', enabled=False)`** appears twice in
  `ext/rotary_embeddings.py` on the hot path. On a CUDA-less machine this could plausibly raise or
  warn. Tested: **runs clean on MPS, no exception, no warning.** Because `enabled=False`, it is a
  no-op context manager.
- **`nn.RMSNorm`** — the cause of closed issue #34 ("OSX torch no attribute RMSNorm", marked *not
  planned*). That was a stale-PyTorch problem; `RMSNorm` needs torch ≥ 2.4. Confirmed present in
  2.7.1.

Prior run also validated MPS numerics directly (`mps_validation.json`): fp32 matmul agrees with CPU
to 2.3e-10, conv1d/conv2d finite, no NaN/Inf, isolation `OK`.

**Verdict: MPS is viable.** The earlier failure was memory, not MPS.

---

## F. Float32 feasibility

**Feasible, and it works — but it is the wrong default and it is what killed the previous run.**

`demo.py` default is **bfloat16**; fp32 is opt-in via `--full_precision`. The prior attempt used
fp32, which **doubled every weight** and contributed directly to the OOM kill.

|  | fp32 | bf16 |
|---|---|---|
| All weights resident | **6.26 GB** | **3.13 GB** |
| Largest single component (CLIP) | 3.95 GB | 1.97 GB |

bf16 numerics on MPS are sound: all ops pass (§E), and an 8-layer matmul/tanh chain drifts only
`1.2e-2` max-abs from fp32 — acceptable for a generative flow model where the sampler is
stochastic anyway.

**One caveat that limits the saving.** `open_clip` constructs CLIP in fp32 and loads an fp32
checkpoint; the cast to bf16 happens *after*. So bf16 halves **steady-state** memory but does **not**
reduce the **construction transient** (§G), which is the actual binding constraint. bf16 is still
clearly worth taking — it just is not sufficient on its own.

**Recommendation:** bf16 for CLIP and Synchformer (feature extractors, tolerant), and **fp32 for the
diffusion net and the VAE/vocoder decode** — those are small (0.63 GB and 1.20 GB), so precision
there is nearly free, and the vocoder is where quantisation noise would actually be audible. This
mixed policy is not an upstream feature but requires no repo modification: it is just what dtype you
pass to `.to()` in each phase.

---

## G. Estimated memory usage

Measured by memory-mapping each checkpoint — no model constructed.

### Live parameters per component

| Component | Live params | fp32 | bf16 |
|---|---|---|---|
| CLIP DFN5B ViT-H-14-384 | 986.7 M | 3.95 GB | 1.97 GB |
| Synchformer (visual branch only) | 122.4 M | 0.49 GB | 0.24 GB |
| VAE `v1-44` decoder (encoder deleted) | 176.4 M | 0.71 GB | 0.35 GB |
| BigVGAN v2 44 kHz | 122.2 M | 0.49 GB | 0.24 GB |
| MMAudio net `small_44k` | 157.5 M | 0.63 GB | 0.31 GB |
| **Total** | **1565.2 M** | **6.26 GB** | **3.13 GB** |

**This decomposition is validated against the real run.** Summing the four `FeaturesUtils`
components gives 1407.7 M; the killed run logged `FeaturesUtils ... (1407.6M)`. Exact match — the
model below is trustworthy.

Two source facts make the live count much smaller than the file sizes suggest:

- **Synchformer loads only its visual branch.** `Synchformer.__init__` builds *only*
  `vfeat_extractor`; `load_state_dict` then **discards every other key**:
  ```python
  sd = {k: v for k, v in sd.items() if k.startswith('vfeat_extractor')}
  ```
  So of the checkpoint's 237.5 M params (afeat 92.4 M + transformer 21.4 M + projections), only
  **122.4 M** ever become live. The 950 MB file is ~2× larger than what it instantiates.
- **The VAE encoder is deleted.** `need_vae_encoder=False` triggers `del self.vae.encoder`, dropping
  129.1 M of the 305.5 M.

### Peak transients — the thing that actually matters

Steady-state totals are not what killed the run. Each component is briefly **double-resident**:
the checkpoint is fully loaded into RAM, *then* the module is populated, *then* the checkpoint is
freed. On unified memory there is no separate VRAM pool to hide this.

| Load step | Checkpoint in RAM | Module in RAM | Transient peak |
|---|---|---|---|
| **CLIP** | 3.95 GB | 3.95 GB | **7.90 GB** ← binding constraint |
| Synchformer | 0.95 GB (full file, then filtered) | 0.49 GB | 1.44 GB |
| VAE `v1-44` | 1.22 GB | 1.22 GB (enc+dec, then trimmed) | 2.44 GB |
| BigVGAN | 0.49 GB | 0.49 GB | 0.98 GB |
| Net `small_44k` | 0.63 GB | 0.63 GB | 1.26 GB |

**CLIP construction alone transiently needs ~7.9 GB**, regardless of target dtype. This single fact
dominates the entire memory strategy.

Activations are secondary but not trivial: CLIP encodes 24 frames at 384² through a 32-layer
ViT-H (~1.5–2.5 GB peak), Synchformer 8 overlapping 16-frame segments (~1–2 GB). The diffusion loop
itself is cheap — latent is only `130 × 448`.

One more limit: `torch.mps.recommended_max_memory()` on this machine reports **11.84 GB**. That is
the MPS allocator's own watermark and is well below total RAM.

---

## H. Expected memory peak on our 17.18 GB M4

Measured baseline before anything loads: **7.03 GB used / 8.28 GB available** (`mmaudio_baseline.txt`).

### What the previous run did (all-resident, fp32) — and why it died

| Stage | Cumulative RAM |
|---|---|
| Baseline | 7.03 GB |
| + net `small_44k` (fp32) | 7.66 GB |
| + CLIP construction transient | **15.6 GB** ← ~1.6 GB headroom on a 17.18 GB machine |
| + Synchformer + VAE + vocoder | ~13.3 GB steady |
| + generation activations | **~16 GB** |

Observed: `peak_used 12.41 GB, min_avail 0.15 GB, peak_swap 3.77 GB` → **killed**. The machine went
into swap thrash and the guard fired. This is entirely consistent with the model above.

### What a phase-split run should do (§K), bf16 feature extractors

Because only one phase is resident at a time, the peak is the **worst single phase**, not the sum:

| Phase | Resident | Transient peak above baseline |
|---|---|---|
| 1 — CLIP + Synchformer | 2.21 GB (bf16) | **~7.9 GB** (CLIP construction) |
| 2 — diffusion net only | 0.63 GB (fp32) | ~1.3 GB |
| 3 — VAE decoder + vocoder | 1.20 GB (fp32) | ~2.4 GB |

**Projected peak = baseline + ~7.9 GB**, driven entirely by Phase 1:

| Baseline at launch | Projected peak | Headroom | Assessment |
|---|---|---|---|
| 7.03 GB (as measured) | ~14.9 GB | ~2.3 GB | marginal — above the 1.5 GB guard, but uncomfortable |
| **≤ 5.0 GB (recommended)** | **~12.9 GB** | **~4.3 GB** | **safe** |
| ≤ 4.0 GB | ~11.9 GB | ~5.3 GB | comfortable |

**This fits — but only with the phase split, and only if we free host memory before starting.**
Quitting other applications is not housekeeping advice here; it is a load-bearing requirement worth
~3 GB, which is more than any other single optimisation available to us.

---

## I. Dependencies

Upstream `pyproject.toml` requires Python **≥ 3.9** and torch **≥ 2.5.1**. The known-good set on
this machine (already installed in the prior `venv-mmaudio`, verified working on MPS):

| Package | Version | Note |
|---|---|---|
| Python | **3.10.20** | via pyenv; matches the other module venvs |
| torch | **2.7.1** | ≥ 2.5.1 required; ≥ 2.4 needed for `nn.RMSNorm` |
| torchvision | **0.22.1** | must match torch 2.7.1 — used for `transforms.v2` |
| torchaudio | **2.7.1** | must match torch 2.7.1 |
| **numpy** | **1.26.4** | **pinned `<2.1` by upstream — must stay on 1.x** |
| scipy | 1.15.3 | |
| av (PyAV) | 17.1.0 | the actual video reader |
| open_clip_torch | 3.3.0 | ≥ 2.29.0 required |
| timm | 1.0.28 | ≥ 1.0.12 required |
| einops, hydra-core, torchdiffeq, librosa, tensordict, nitrous-ema, colorlog | as installed | |

Note `numpy < 2.1` is a **hard upstream constraint**. This matches the pinning discipline already
established elsewhere in this project.

### One dependency trap worth knowing about

`torchcodec` is a **declared dependency** in `pyproject.toml`, so `pip install -e .` will pull it —
and on this machine **it installs but cannot be imported**:

```
Symbol not found ... libtorchcodec_image.dylib
Expected in: .../torch/lib/libtorch_cpu.dylib
```

torchcodec 0.16.0 is ABI-pinned to a different torch build. **This is harmless**: `grep -rn
torchcodec` across the entire repository returns **zero imports** — MMAudio reads video with `av`.
The broken package sits inert. Do not spend time fixing it, and do not let it block the install.

---

## J. CUDA dependency status

**No CUDA dependency on the inference path. Confirmed by exhaustive grep, not by assumption.**

Every CUDA reference in the package falls into one of three harmless categories:

| Location | What it is | Impact on us |
|---|---|---|
| `runner.py` (`.cuda()`, `autocast('cuda')` ×6) | **training** runner | never imported by `demo.py` |
| `synchformer.py:45`, `networks.py:465` | `__main__` self-test blocks | not executed on import |
| `ext/rotary_embeddings.py:19,31` | `autocast(device_type='cuda', enabled=False)` | **on the hot path** — tested clean on MPS (§E) |
| `autoencoder.py:31` | `use_cuda_kernel=False` passed explicitly | opt-out already taken |

`demo.py` sets `torch.backends.cuda.matmul.allow_tf32 = True` at module level — a no-op without CUDA.

**flash-attn / xformers / triton: none required, none referenced.** Zero occurrences anywhere in the
package. Attention is plain `F.scaled_dot_product_attention`, which has a native MPS kernel.

**BigVGAN's CUDA kernel is optional and already disabled.** `AutoEncoderModule` hard-codes
`use_cuda_kernel=False`, selecting the pure-PyTorch anti-aliased activation path
(`bigvgan_v2/alias_free_activation/torch/`). No compilation, no nvcc.

One genuinely CUDA-only line exists in `demo.py` itself — the final
`torch.cuda.max_memory_allocated()` log call, which would raise on MPS. It is the last statement
after the audio is already saved, and our own driver script will not include it.

---

## K. Low-memory possibilities

This is the decisive question, so it is answered concretely.

### Does the official `generate()` assume all components stay resident?

**Yes.** `eval_utils.generate()` takes a single fully-constructed `feature_utils` plus `net` and
calls, in order: `encode_video_with_clip` → `encode_video_with_sync` → `encode_text` ×2 → 25
diffusion steps on `net` → `decode` → `vocode`. It reads `feature_utils.device`/`.dtype` up front
and never releases anything. **Using it as-is means everything co-resident for the whole run.**

There are **no official low-memory options.** No offload flag, no sequential-load mode, no
`low_cpu_mem_usage`, no CPU-offload hook. README's only memory statement is *"around 6GB of GPU
memory (in 16-bit mode),"* which assumes a discrete GPU with host RAM to spare — not unified memory.

### But the components are used in strictly disjoint phases

This is the key structural fact. Reading `generate()` as a dataflow:

```
Phase 1  CLIP + Synchformer  →  clip_features, sync_features, text_features, neg_text_features
Phase 2  net (diffusion)     →  x1 latent            [needs NO feature_utils]
Phase 3  VAE decoder + BigVGAN → waveform            [needs NO CLIP, NO Synchformer, NO net]
```

Nothing from Phase 1 is needed after Phase 1 except four small feature tensors. The 4.44 GB of
CLIP+Synchformer is dead weight through Phases 2 and 3.

### And the constructor already supports splitting them — no repo modification needed

`FeaturesUtils.__init__` has two independent switches that partition it exactly along the phase
boundary:

```python
if enable_conditions:                 # CLIP + Synchformer + tokenizer
    ...
else:
    self.clip_model = None; self.synchformer = None; self.tokenizer = None

if tod_vae_ckpt is not None:          # VAE + vocoder
    ...
else:
    self.tod = None
```

So two disjoint instances are constructible **using only the public constructor**:

| Phase | Construction | Loads |
|---|---|---|
| 1 | `FeaturesUtils(enable_conditions=True, tod_vae_ckpt=None, synchformer_ckpt=...)` | CLIP + Synchformer only |
| 3 | `FeaturesUtils(enable_conditions=False, tod_vae_ckpt=v1-44.pth, need_vae_encoder=False)` | VAE decoder + vocoder only |

**This is the single most important finding in this evaluation.** The split needs no patch, no fork,
and no monkey-patching — the upstream repository stays byte-identical. We reimplement the *body* of
`generate()` in our own script, calling the same methods in the same order.

### Techniques assessed

| Technique | Verdict |
|---|---|
| **Phase-split component loading** | **Yes — primary strategy.** Public constructor flags; no repo change. Cuts peak from sum-of-all to worst-single-phase. |
| **Subprocess per phase** | **Yes — strongly recommended.** Python GC + `torch.mps.empty_cache()` do not reliably return unified memory to the OS; process exit does, 100%, every time. Passing four small tensors between phases via `torch.save` is trivial. This converts "should free" into "did free." |
| **Cache features to disk** | **Yes — high value.** Phase 1 is 71% of the memory cost and its output depends only on (video segment, prompt). Cache it and prompt/seed/CFG iteration never loads CLIP again. Given that we *will* iterate on prompts, this is the difference between a 7.9 GB peak per attempt and a 2.4 GB one. |
| **bf16 feature extractors** | **Yes.** Halves steady-state CLIP+Sync from 4.44 → 2.21 GB. Does not reduce the construction transient (§F). |
| **`need_vae_encoder=False`** | **Already default in `demo.py`.** Saves 129.1 M params. Keep it. |
| **Reduce host baseline** | **Yes — worth ~3 GB**, more than any code change. Quit other apps before Phase 1. |
| **`small_44k` over `large_44k_v2`** | **Yes.** Saves ~3.3 GB; already downloaded. |
| **Activation chunking** | **Partially available, already tuned.** `encode_video_with_clip/sync` accept `batch_size`; `generate()` passes 40×. For our 3 s clip that is 24 CLIP frames and 8 sync segments — a *single* batch either way, so lowering it below 24 is the only lever, and upstream's own changelog notes 40× "without using more memory." Low value here; useful only if we later batch multiple actions. |
| **CPU/MPS component movement** | **Available but inferior.** `.to('cpu')` on unified memory does not free the underlying RAM the way it would on a discrete GPU — it moves between heaps that share the same physical pool. Subprocess isolation achieves the goal properly. |
| **Diffusion-only / decoder-only loading** | **Yes — that is exactly Phases 2 and 3.** Confirmed viable via the constructor flags above. |
| **Avoid CLIP entirely (`--mask_away_clip`)** | **No.** It drops *image* CLIP features, but `encode_text` still needs CLIP's text tower — so CLIP loads anyway. All cost, no saving, and worse quality. |

### Residual risk

**The ~7.9 GB CLIP construction transient cannot be removed without modifying the repository**
(`open_clip.create_model_from_pretrained` builds fp32-on-CPU then loads an fp32 checkpoint). Since
the constraint is "do not modify MMAudio," we accept it and isolate it in a dedicated subprocess run
once, at a low baseline. §H shows that fits with ~4.3 GB headroom at a 5 GB baseline.

---

## L. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **CLIP construction transient ~7.9 GB** | **High** | Phase 1 in its own subprocess at ≤5 GB baseline; cache features so it runs once |
| 2 | **Repeating the previous OOM kill** | **High** | Do not use all-resident `generate()`. Phase split + arm a memory guard before loading |
| 3 | **3.0 s vs 8 s training duration** → thin/degraded output | **Medium-High** | Generate on an 8 s window, crop to 5.5–8.5 (§N) |
| 4 | **`load_video` ignores start time** — silently conditions on 0–3 s instead of 5.5–8.5 | **Medium** | Pre-cut the segment with ffmpeg; assert clip duration and first-frame content |
| 5 | Frame shortfall → silent truncation 3.00 → 2.96 s | Medium | Cut with a small tail margin; log `video_info.duration_sec` and assert |
| 6 | MPS untested upstream ("only tested on Ubuntu") | Medium | Ops pre-verified (§E); check for NaN/Inf after each phase |
| 7 | bf16 quality drift in the vocoder | Low-Medium | fp32 for Phase 3 — costs only 1.2 GB |
| 8 | **CC-BY-NC 4.0 — non-commercial weights** | **Medium (non-technical)** | Fine for research/demo. Must be revisited before any commercial use |
| 9 | `torchcodec` import failure | Low | Cosmetic — zero imports in repo (§I) |
| 10 | `demo.py`'s trailing `torch.cuda.max_memory_allocated()` | Low | Our driver omits it |
| 11 | MPS allocator watermark 11.84 GB | Low-Medium | Per-phase resident stays ≤2.3 GB; far below |
| 12 | Swap thrash before the guard fires | Medium | Guard on *both* available RAM and swap growth |

---

## M. Recommended installation strategy

Nothing is installed here — this is the plan to execute on approval.

1. **Fresh isolated venv** at `Module3_Fresh/models/venv-mmaudio-fresh`, Python **3.10.20** (pyenv).
   Never activate any existing venv. Verify `sys.prefix` and assert no `sys.path` leakage into
   `01-Lip-Reading`, `02-Auto-AVSR-Test`, or `03-FoleyCrafter-Test` — the same isolation check used
   for Auto-AVSR.

2. **Install torch first, pinned, before anything else:**
   ```
   torch==2.7.1  torchvision==0.22.1  torchaudio==2.7.1
   ```
   Default PyPI wheels — **no `--index-url .../cu118`**; the README's CUDA index is for Linux/NVIDIA
   and must not be copied.

3. **Pin numpy to `1.26.4`** *before* installing MMAudio, so no transitive dependency drags in
   numpy ≥ 2.1 (upstream requires `<2.1`).

4. **Clone MMAudio fresh** into `Module3_Fresh/models/MMAudio`. Do **not** reuse or reference the
   existing clone at `03-FoleyCrafter-Test/.../mmaudio/MMAudio` — that tree stays untouched.
   Install with `pip install -e .`. **Expect `torchcodec` to install broken; ignore it** (§I).

5. **Reuse the checkpoints already on disk — download nothing.** All six components are present and
   MD5-verified. Copy or symlink into `Module3_Fresh/models/weights/` and `ext_weights/`, then
   re-verify MD5 against `download_utils.py`. CLIP and BigVGAN resolve from `~/.cache/huggingface`
   automatically. **This saves 6.75 GB of downloads and ~7 minutes.**
   - Copy rather than symlink if we want Module3_Fresh fully self-contained; symlink if disk is
     tight. Either way the originals stay read-only.

6. **Do not modify the MMAudio repository.** All phase-split logic lives in
   `Module3_Fresh/scripts/`, importing MMAudio as a library.

7. **Verify before generating:** torch version, MPS available, isolation clean, numpy 1.x,
   `nn.RMSNorm` present, all six checkpoint MD5s, and the §E op probe.

---

## N. Recommended first-generation configuration

**Test case:** `drink from cup`, 5.50–8.50 s.

### Model and precision

| Setting | Value | Why |
|---|---|---|
| Variant | `small_44k` | already on disk; saves 3.3 GB vs `large_44k_v2` |
| Sample rate | 44,100 Hz | `v1-44.pth` + BigVGAN-v2-44kHz |
| Device | `mps` | ops verified (§E) |
| CLIP + Synchformer dtype | **bfloat16** | halves 4.44 → 2.21 GB; upstream default |
| Net + VAE + vocoder dtype | **float32** | only 1.83 GB total; protects audible quality |
| Steps | 25 (euler) | upstream default |
| CFG strength | 4.5 | upstream default |
| Seed | 42 | fixed, for reproducibility |

Keep every sampler parameter at upstream defaults for the first run. If output is wrong we need to
know whether it is *MMAudio* or *our configuration*, and that requires a clean baseline.

Note `ode_wrapper` calls `predict_flow` **twice per step** when `cfg_strength ≥ 1.0` (conditional +
unconditional), so 25 steps = 50 network forwards. Cheap for a 157 M net at latent length 130.

### Duration — recommendation

**Primary: generate at 8 s, then crop.** Cut **2.00–10.00 s** from the source, generate the full 8 s
(matching training duration), then crop 5.50–8.50 from the result. This keeps MMAudio inside its
trained regime and gives the model the approach-and-lift context that makes a sip land correctly.

**Control: generate the 2.96 s segment directly.** Cut 5.50–8.50, generate natively. This is the
literal reading of the task and the cheaper run.

Generate **both** and listen. They cost the same, and this is precisely the question the first
experiment should answer. My expectation is the 8 s window wins clearly, but that is a prediction,
not a measurement, and it should be settled by listening rather than by assumption.

### Execution plan

Pre-cut with ffmpeg (`-c:v copy` where possible), asserting the output duration — remembering that
`load_video` **always reads from t=0**, so the cut file *is* the conditioning window (§C).

Three subprocesses, one per phase:

```
Phase 1  CLIP + Synchformer (bf16)  → save clip/sync/text/neg_text features → exit
Phase 2  net small_44k (fp32)       → load features → 25 euler steps → save latent → exit
Phase 3  VAE decoder + BigVGAN (fp32) → load latent → decode + vocode → save WAV → exit
```

Each phase exits fully before the next starts, so the OS reclaims all memory.

Arm the memory guard **before** Phase 1: WARN at 2.0 GB available, ABORT at 1.5 GB, plus a swap-growth
ceiling. **Confirm baseline ≤ 5 GB before launching** (§H) — the previous run started at 7.03 GB and
died.

Prompt: describe the sound, not the scene, with negatives for music/speech/ambience. The Module 2
label is `drink from cup` with evidence *"man holds white mug in right hand and drinks from it"* —
that maps to sipping, swallowing, and light ceramic handling.

Write only into `Module3_Fresh/`. Output WAV to `Module3_Fresh/audio/generated/`. **No MP4 muxing and
no synchronisation in this first run** — validate the audio in isolation first.

### Expected cost

Model load ~60 s (prior run measured 61.5 s all-resident; split will be somewhat higher due to
repeated process startup). Diffusion and decode a few tens of seconds. **Budget 3–6 minutes per
generation**, dropping to well under a minute for prompt iterations once Phase 1 features are cached.

---

## Final verdict

# ✅ RECOMMEND MMAUDIO

MMAudio is the right model for Module 3, and it is the only evaluated candidate whose architecture
actually satisfies the requirement. Its Synchformer branch provides explicit 25 fps motion
conditioning aligned per audio-latent-frame — precisely what "drink from cup" needs and precisely
what Stable Audio, AudioLDM2, and FoleyCrafter cannot provide.

The technical preconditions check out:

- **Video + text conditioning** — confirmed in source, both used simultaneously.
- **44.1 kHz** — `v1-44.pth` + BigVGAN-v2-44kHz, both already downloaded and MD5-verified.
- **No CUDA requirement** — every CUDA reference is training-only, a `__main__` block, or an
  already-taken opt-out. No flash-attn, no xformers, no triton.
- **MPS works** — every operator on the inference path verified on this machine in fp32, bf16, and
  fp16, including the two hazards (`autocast('cuda')`, `RMSNorm`) that could plausibly have broken it.
- **Audio-free video input is guaranteed** — `read_frames` demuxes only the video stream; the AAC
  track is never opened.
- **Nothing needs downloading** — all 11.2 GB of weights are already present and verified.

**The one serious obstacle is memory, and it is solved.** The earlier attempt was killed at 0.15 GB
available because it used the all-resident official path in float32. That path is genuinely
unworkable here: `generate()` holds ~6.26 GB of weights resident while CLIP construction alone
transiently needs 7.9 GB, against a 17.18 GB machine that starts at 7.03 GB used.

But the components are used in **strictly disjoint phases**, and `FeaturesUtils.__init__` already
exposes the exact switches needed to load them separately — `enable_conditions` and `tod_vae_ckpt`.
**The phase split requires no modification to the MMAudio repository at all.** Combined with
subprocess isolation, bf16 feature extractors, `small_44k`, and a reduced host baseline, projected
peak drops from ~16 GB to **~12.9 GB, leaving ~4.3 GB of headroom**.

That said, two things should be stated plainly rather than buried:

1. **Upstream has only tested this on Ubuntu.** MPS is a supported code path with no upstream
   guarantee. We have de-risked it as far as static inspection and op-probing allow, but the first
   real generation is still the first real test.
2. **The 3 s / 8 s duration mismatch is an unquantified quality risk**, not a solved problem. §N
   proposes generating both and listening. Until we do, quality is a prediction.

Neither is a reason to choose a different model — both are reasons to make the first run a careful
one.

**Recommended next step:** approve the §M installation plan and the §N first-generation
configuration, then execute Phase 1 only and inspect the cached features before generating any audio.

---

*Evaluation complete. No packages installed, no checkpoints downloaded, no environment created, no
audio generated, no existing file modified.*

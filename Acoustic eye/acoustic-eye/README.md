# Acoustic Eye

**Recovering Acoustic Information from Visual Vibrations**

Acoustic Eye is a web application that takes a video as input and attempts to
reconstruct the sound that was present while the video was recorded, using the
tiny sound-induced vibrations visible on objects in the frame. It is a
front-end + REST API + processing pipeline built around a **phase-based Visual
Microphone** (Davis et al., SIGGRAPH 2014).

> ⚠️ **Scientific scope.** This does **not** recover arbitrary audio from an
> arbitrary video. The output sample rate equals the camera frame rate, so with
> ordinary 30–60 fps footage the recoverable band is only a few tens of Hz
> (Nyquist = fps / 2). Expect a low rumble correlated with the sound, not
> intelligible speech. High-speed (120–960 fps) footage of a loud source next to
> a light, resonant object gives the best results.

---

## 1. Project overview

| Stage | What happens |
|-------|--------------|
| Video upload | Drag-and-drop or file picker (MP4 / AVI / MOV / MKV / WEBM). |
| Video validation | Opened with OpenCV; real decodable frame count measured; audio-only / corrupt / too-short files rejected with a friendly message. |
| Visual Microphone processing | Per frame: complex steerable pyramid → local phase → phase difference vs. first frame → amplitude weighting → per-band scalar signal. |
| Acoustic signal reconstruction | Per-band signals cross-correlation-aligned and summed (paper eqs. 4–5). |
| WAV audio generation | Butterworth high-pass, normalise to [-1, 1], write 16-bit PCM WAV at `sample_rate = fps`. |
| Audio playback | HTML5 `<audio>` element streams the WAV from the API. |
| Waveform / spectrogram | Rendered server-side with Matplotlib (Agg) from the exact signal written to the WAV. |
| The audio in text | An always-on plain-English + tabular description of the recovered signal (dominant frequency, band energy, loudness, burst timestamps). Optional offline speech-to-text (`faster-whisper`) for high-speed captures. |
| Download | Direct download of the reconstructed WAV (and an optional spectral-subtraction denoised WAV). |

Everything shown in the UI comes from the uploaded video and the real
processing. There is no synthetic audio, fake progress, or placeholder art.

---

## 2. Architecture

```
Browser (HTML5 / CSS3 / vanilla JS)
   |  fetch() REST calls
   v
FastAPI + Uvicorn  (backend/main.py, backend/api/routes.py)
   |  background worker thread per job
   v
Video processing        (backend/processing/video_reader.py)   -- OpenCV, robust frame counting
   |
Visual Microphone core  (backend/processing/visual_microphone.py) -- pyrtools complex steerable pyramid
   |
Signal processing       (backend/processing/signal_processing.py)  -- SciPy: high-pass, scaling, spectral subtraction
   |
WAV + visualisation     (backend/processing/audio_writer.py)   -- SoundFile + Matplotlib
   |
outputs/<job_id>.wav  +  <job_id>_waveform.png  +  <job_id>_spectrogram.png
   |
Browser  (audio player, download link, images)
```

### Project tree

```
acoustic-eye/
├── backend/
│   ├── __init__.py
│   ├── main.py                     FastAPI app; also serves the frontend
│   ├── config.py                   all tunable parameters + paths (pathlib, no absolute paths)
│   ├── requirements.txt
│   ├── config.json                 (optional, git-ignored) on-disk parameter overrides
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               /health /upload /process /status /result endpoints + job store
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── video_reader.py         open/validate/iterate video; real frame counting
│   │   ├── visual_microphone.py    phase-based core (adapted from visual-mic-master)
│   │   ├── signal_processing.py    scaling / high-pass / spectral subtraction (adapted)
│   │   ├── audio_writer.py         WAV writing + waveform/spectrogram PNGs
│   │   ├── text_report.py          signal-to-text description + optional speech-to-text
│   │   └── pipeline.py             glue: runs the full flow, emits stage progress
│   └── utils/
│       ├── __init__.py
│       └── file_handler.py         safe filenames, size limits, path-traversal guards
├── frontend/
│   ├── index.html                  Home / How It Works / About
│   ├── css/style.css               light + dark professional theme
│   └── js/app.js                   upload, preview, params, polling, results
├── uploads/.gitkeep                stored uploads (git-ignored contents)
├── outputs/.gitkeep                generated WAV + PNG (git-ignored contents)
├── tests/
│   ├── conftest.py                 synthetic tiny-video fixtures
│   ├── test_video.py               reader / validation / frame counting
│   ├── test_processing.py          signal helpers + full pipeline (slow, needs pyrtools)
│   └── test_api.py                 FastAPI smoke tests
├── run.py                          cross-directory launcher: `python run.py`
├── start.bat                       Windows one-click: venv + deps + launch
├── pytest.ini
├── README.md
├── .gitignore
└── LICENSE                         MIT + third-party attribution
```

---

## 3. Installation (Windows)

### Easiest: `start.bat`

Double-click **`acoustic-eye\start.bat`** (or run it from a terminal). On the
first run it creates the virtual environment, installs every dependency, opens
your browser, and starts the server. On later runs it just starts the server.
Requires Python 3.10–3.12 on your PATH ("Add python.exe to PATH" during the
Python installer). If it fails, read the messages it prints and see §12.

### Manual

From a `cmd` or PowerShell prompt, in the folder that contains `acoustic-eye/`:

```bash
cd acoustic-eye
python -m venv .venv
```

Activate the virtual environment:

* **PowerShell:**

  ```bash
  .venv\Scripts\Activate.ps1
  ```

  (if PowerShell blocks the script: `Set-ExecutionPolicy -Scope Process RemoteSigned`)

* **cmd.exe:**

  ```bash
  .venv\Scripts\activate.bat
  ```

Upgrade pip and install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

### About `pyrtools` on Windows

`pyrtools` provides the complex steerable pyramid and is the core of the Visual
Microphone. It is **pure Python** (NumPy/SciPy/Matplotlib underneath) and ships
as a wheel — no C compiler or MSVC Build Tools are required in the normal case.

```bash
pip install pyrtools
```

If `pip` still tries to build from source and fails:

1. Make sure `pip`, `setuptools`, and `wheel` are current:
   `python -m pip install --upgrade pip setuptools wheel`
2. Install its scientific deps first: `pip install numpy scipy matplotlib`
3. Retry `pip install pyrtools`.
4. Only as a last resort install the "Desktop development with C++" workload from
   the [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   and retry.

The app still starts and validates videos without `pyrtools`; `/health` and a
banner in the UI report that reconstruction is unavailable until it is
installed.

### `opencv-python` vs `opencv-python-headless`

`requirements.txt` pins `opencv-python-headless` (no GUI libs — smaller, fewer
Windows DLL issues, and the app never opens a window). If you already have the
full `opencv-python` installed, that works too; do not install both.

---

## 4. Running

**Option 1 — `start.bat`** (double-click, or run it in a terminal). Handles the
venv, deps and launch, and opens the browser for you.

**Option 2 — the launcher script** (works from *any* directory, venv active or
not as long as deps are installed):

```bash
python run.py
```
```bash
python run.py --port 9000          # different port
python run.py --host 0.0.0.0       # reachable from other devices on your LAN
python run.py --reload             # auto-restart on code edits (development)
```

**Option 3 — uvicorn directly** — you MUST be in the `acoustic-eye/` folder
(the one containing both `backend/` and `frontend/`), or you'll get
`ModuleNotFoundError: No module named 'backend'`:

```bash
uvicorn backend.main:app --reload
```

Then open **http://127.0.0.1:8000** in a browser. The same server hosts the API
and the website — there is no second process, and you should **not** open
`frontend/index.html` as a file (it needs the backend). Interactive API docs:
`http://127.0.0.1:8000/docs`.

---

## 5. Usage

1. **Upload video** — drag a clip onto the drop zone or click *Select Video*.
   *For a file too big to upload,* use the **“process a file already on this
   computer”** panel instead (path + start time + segment length) — see §7a.
2. **Preview video** — the browser plays your file; the panel shows filename,
   size, resolution, FPS, duration, **actual frames read**, and the container's
   (often wrong) frame count for comparison.
3. **Start reconstruction** — optionally open *Advanced parameters* (down-sample
   factor, pyramid scales / orientations, high-pass cutoff, denoise toggle),
   then click **START ACOUSTIC RECONSTRUCTION**.
4. **Wait for processing** — a stage checklist updates live:
   `✓ Validating video → ✓ Reading & preprocessing frames → ⟳ Extracting local
   phase (NN%) → Reconstructing … → Filtering … → Generating WAV … → Rendering
   visualisations → Analysing signal & writing text`. Phase extraction shows a
   true percentage; other stages use an indeterminate animation (no fake numbers).
5. **Listen to output** — the recovered WAV plays in-page.
6. **View waveform / spectrogram** — rendered from the exact output signal; the
   Nyquist limit for your video is printed under the spectrogram.
7. **Read "The audio, in text"** — a plain-English description of the recovered
   signal (duration, dominant frequency, loudness, energy per frequency band,
   and the timestamps of louder bursts), with a **Copy text** button. This is
   always produced. Below it, an optional **speech-to-text** panel: it stays
   empty at normal frame rates (there is no speech-band content to transcribe)
   and only does anything for very high-speed captures with `faster-whisper`
   installed and the *Advanced parameters* toggle ticked.
8. **Download WAV** — *Download reconstructed audio*. If denoising was enabled a
   second player + download appears.

### Testing procedure with one sample video

```bash
# 1. Record or find a short clip: phone on a tripod, ~10 s, pointed at a
#    chip bag / sheet of paper / leaf, with music or a tone playing loudly
#    nearby. Higher fps ("slo-mo", 120/240 fps) works far better.
# 2. Start the server:
uvicorn backend.main:app --reload
# 3. Open http://127.0.0.1:8000 , upload the clip, click START.
# 4. When it finishes, play the WAV and inspect the spectrogram — look for
#    energy that tracks the sound you played, within 0..(fps/2) Hz.
```

A ready-made example is bundled with the reference implementation
(`visual-mic-master/examples/`), and `visual-mic-master` also documents where to
download MIT's original high-speed test videos.

---

## 6. API reference

| Method | Path | Body | Purpose |
|--------|------|------|---------|
| `GET` | `/` | – | Serves `frontend/index.html`. |
| `GET` | `/health` | – | `{ pyrtools_available, pyrtools_error, max_upload_mb, min_usable_frames, max_process_frames, default_processing, local_ingest: { enabled, allowed_roots, segment_default_seconds, segment_max_seconds } }`. |
| `POST` | `/upload` | `multipart/form-data` field `file` | Stores + validates the video. Returns `{ job_id, video: {width,height,fps,frame_count_metadata,frames_read,duration_seconds,fourcc,...}, limits }`. |
| `POST` | `/process` | JSON `{ job_id, options?: {downsample,scales,orientations,high_pass_frequency,spectral_subtraction} }` | Starts a background job. Returns `{ job_id, status: "running" }`. |
| `POST` | `/process-local` | JSON `{ path, start_seconds?, duration_seconds?, options? }` | **For videos too large to upload.** Reads a segment of a file already on the server machine (no upload, no size limit). Validates the window synchronously, then starts a job. Returns `{ job_id, status, video, segment }`. Path must be a whitelisted video inside an allowed root (see §7). |
| `GET` | `/status/{job_id}` | – | `{ status: queued\|running\|done\|error, stages: [{key,state,fraction}], error, result }`. |
| `GET` | `/result/{filename}` | – | Streams a produced file (`audio/wav` or `image/png`). Path-traversal protected. |

`result` (when `status == "done"`) contains: `sample_rate`, `nyquist_hz`,
`frames_processed`, `wav_filename`, `waveform_filename`, `spectrogram_filename`,
optional `denoised_*` filenames, `wav_properties`, `notes[]`, **`analysis`**
(dict: `duration_seconds`, `dominant_frequency_hz`, `spectral_centroid_hz`,
`rms`, `peak`, `crest_factor_db`, `band_energy_percent`, `bursts[]`, `summary`),
**`analysis_text`** (the plain-English summary string), and **`transcript`**
(`{ available, text, segments[], note }` — empty unless transcription is enabled).

---

## 7. Configuration

All tunables live in [`backend/config.py`](backend/config.py). You can override
the processing defaults without editing code by creating
`backend/config.json` (git-ignored):

```json
{
  "processing": {
    "downsample": 0.1,
    "scales": 1,
    "orientations": 2,
    "high_pass_frequency": 0.05,
    "spectral_subtraction": true,
    "spec_sub_quantile": 0.5
  }
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `downsample` | `0.25` | Frame scale factor before the pyramid. Lower = faster / less detail. The reference uses `0.1`. Auto-relaxed if it would shrink a side below 24 px. |
| `scales` | `1` | Steerable-pyramid scales (`nscale`). |
| `orientations` | `2` | Steerable-pyramid orientations (`norientation`); passed to pyrtools as `orientations - 1`. |
| `high_pass_frequency` | `0.05` | Butterworth high-pass cutoff as a **fraction of Nyquist** (matches the reference's hard-coded `0.05`). At 30 fps that removes < ~0.75 Hz drift. |
| `high_pass_order` | `3` | Butterworth order. |
| `spectral_subtraction` | `true` | Also produce a denoised WAV + visualisations. |
| `spec_sub_quantile` | `0.5` | Per-frequency noise-floor quantile for spectral subtraction. |
| `enable_transcription` | `false` | Run optional offline speech-to-text (`faster-whisper`) on the result. No-op unless the package is installed; only meaningful for multi-kHz-fps captures. The always-on **signal-analysis text** does not need this. |

Server-side settings live at the top level of `config.json` (not under
`"processing"`):

```json
{
  "max_upload_mb": 250,
  "min_usable_frames": 30,
  "max_process_frames": 4000,
  "allow_local_path_ingest": true,
  "local_path_allowed_roots": ["C:\\Users\\you\\Videos", "D:\\footage"],
  "segment_default_seconds": 10.0,
  "segment_max_seconds": 30.0,
  "result_ttl_seconds": 21600
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `max_upload_mb` | `250` | Hard cap on browser-upload size. |
| `min_usable_frames` | `30` | Reject jobs with fewer real decoded frames. |
| `max_process_frames` | `4000` | Global frame ceiling per job (time / memory guard). |
| `allow_local_path_ingest` | `true` | Enable `POST /process-local` (read a file straight from disk, no upload). Set `false` to disable the feature. |
| `local_path_allowed_roots` | `[<your home>, <project root>]` | A local path must resolve **inside** one of these folders (blocks `..` escapes and arbitrary file reads). |
| `segment_default_seconds` | `10` | Default segment length for `/process-local`. |
| `segment_max_seconds` | `30` | Maximum segment length accepted by `/process-local`. |
| `result_ttl_seconds` | `21600` (6 h) | Age after which uploads/outputs are cleaned up. |

---

## 7a. Handling very large videos (> the upload limit)

The Visual Microphone only needs a **short, high-frame-rate segment** while the
sound is playing — a few seconds. A multi-GB clip is neither necessary nor
practical (browser upload is fragile, and the pipeline caps at
`max_process_frames`). You have two options.

### Option A — point the app at the file (no upload)

With `allow_local_path_ingest` enabled (default), the Home page shows an **“Or
process a file already on this computer”** panel:

1. Paste the **full path** to the video (e.g. `C:\Users\you\Videos\big.mp4`).
2. Set a **start time** (seconds into the clip) and a **segment length**
   (≤ `segment_max_seconds`).
3. Click **Process local file segment**.

The backend seeks to the start time and reads only that window — the huge file
is never copied or moved. The file must sit inside one of
`local_path_allowed_roots` (your home folder by default; add drives/folders in
`config.json`).

Equivalent API call:

```bash
curl -X POST http://127.0.0.1:8000/process-local ^
  -H "Content-Type: application/json" ^
  -d "{\"path\":\"C:\\Users\\you\\Videos\\big.mp4\",\"start_seconds\":30,\"duration_seconds\":10}"
```

### Option B — trim the file first with ffmpeg, then upload normally

You already have `ffmpeg` installed. Inspect, then cut a small clip
(**do not change the frame rate** — output sample rate = fps, and lowering fps
throws away exactly the high-frequency content that makes a high-speed clip
worth using):

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,width,height,duration -of default=nw=1 "BIGVIDEO.mp4"
```

```bash
ffmpeg -ss 00:00:30 -i "BIGVIDEO.mp4" -t 10 -an -vf "scale=640:-2" -c:v libx264 -preset veryfast -crf 18 "clip.mp4"
```

`-ss 00:00:30` start at 30 s · `-t 10` keep 10 s · `-an` drop audio ·
`-vf scale=640:-2` spatial downscale (safe; the app downsamples anyway) ·
**no `-r`** so the frame rate is preserved. The result is typically 5–40 MB and
uploads normally. Lossless cut without re-encoding:
`ffmpeg -ss 00:00:30 -i "BIGVIDEO.mp4" -t 10 -an -c copy "clip_raw.mp4"`.

Keep the segment ≤ ~15 s at native fps so you stay under `max_process_frames`.

---

## 8. Limitations (read this)

* **Camera frame rate is the ceiling.** Output sample rate = video fps. You get
  **one audio sample per frame**.
* **Nyquist.** The highest representable frequency is `fps / 2`. 30 fps → 15 Hz;
  60 fps → 30 Hz; 240 fps → 120 Hz. Speech (~100–8000 Hz) and music are **not**
  recoverable from normal-fps video.
* **You need visible, sound-induced vibration.** A rigid wall, a distant object,
  or a quiet room produces essentially nothing.
* **Object / material matters.** Light, high-contrast, resonant surfaces (chip
  bags, foil, paper, thin plastic, leaves, water surface) work; heavy/rigid ones
  don't.
* **Lighting & noise.** Flicker (mains-frequency light beating with the shutter),
  rolling-shutter artefacts, sensor noise, compression blocking, and any camera
  motion all inject noise or destroy the signal. Use a tripod and bright, steady
  light.
* **Processing time / resources.** Cost ≈ `frames × pyramid_size`. A complex
  steerable pyramid is built for **every frame**. Defaults (downsample 0.25,
  1 scale, 2 orientations) keep a ~10 s clip to seconds–minutes on a normal
  laptop; raising resolution/scales/orientations or clip length grows it fast.
  RAM scales with per-frame frame size, not clip length (only small per-band
  scalars are retained).
* **Single-process job store.** Jobs live in memory; restarting the server
  forgets them. Fine for a local demo, not for production/multi-user.
* **It does not magically recover arbitrary audio from any video.**

---

## 9. Attribution

### Original research

> A. Davis, M. Rubinstein, N. Wadhwa, G. J. Mysore, F. Durand, W. T. Freeman.
> **The Visual Microphone: Passive Recovery of Sound from Video.**
> ACM Transactions on Graphics (Proc. SIGGRAPH) 33(4), 2014.

The Visual Microphone algorithm is **not** our invention.

### Reference implementation (adapted)

> **visual-mic-master** — Python re-implementation of MIT's Visual Microphone by
> **Antonio Musolino** and **Davide Sforza**. **MIT License**, Copyright © 2020.
> Provided to this project as `visual-mic-master.zip`. Based on the original
> MATLAB code by the paper authors. Uses `pyrtools`
> (Lab for Computational Vision, MIT License) for complex steerable pyramids.

### Clear separation of contributions

```
Existing research (Davis et al., SIGGRAPH 2014)
        +
Adapted implementation (visual-mic-master, MIT — Musolino & Sforza)
        +
Our Acoustic Eye web application (FastAPI backend, REST API, HTML/CSS/JS UI)
        +
Our integration / robustness fixes / testing / visualisation / packaging
```

---

## 10. What was adapted from `visual-mic-master`

Inspected files in the ZIP:

| File | Role |
|------|------|
| `video2sound.py` | CLI entry point (argparse). Reads video with OpenCV, calls `sound_from_video`, writes WAV with `scipy.io.wavfile`, plots a spectrogram. |
| `visualmic/sound_from_video.py` | **Core algorithm.** `align_vectors()` + `sound_from_video()`. |
| `visualmic/sound_spectral_subtraction.py` | `get_scaled_sound()` + `get_soud_spec_sub()` (spectral subtraction). |
| `visualmic/__init__.py` | Empty package marker. |
| `notebooks/test.ipynb` | Parameter-sweep experiments (references a `sound_from_video` signature with extra return values that does **not** exist in the shipped `.py` — not used). |
| `examples/` | Sample `.wav` / `.png` outputs. |
| `LICENSE` | MIT, Copyright © 2020 Antonio Musolino and Davide Sforza. |
| `README.md` | Usage + references to the paper and pyrtools. |

**Language:** Python 3. **Entry point:** `video2sound.py`.
**Dependencies:** `opencv-python`, `numpy`, `scipy`, `pyrtools`, `matplotlib`.
**Input:** any OpenCV-readable video. **Output:** float WAV via
`scipy.io.wavfile.write` + Matplotlib spectrogram.
**Sample rate:** `round(CAP_PROP_FPS)` unless overridden with `-s`.
**License:** MIT — reuse permitted with the copyright notice retained
(kept in `LICENSE` and in each adapted source file's header).

### Reused / adapted (logic preserved)

`backend/processing/visual_microphone.py`
* `align_vectors(v1, v2)` — cross-correlation alignment (paper eq. 4), logic
  identical to the reference; added a `NaN`/empty guard.
* `sound_from_frames(...)` — adaptation of `sound_from_video(...)`. Preserves,
  step for step:
  * complex steerable pyramid per frame:
    `pt.pyramids.SteerablePyramidFreq(frame, nscale, norientation - 1, is_complex=True)`
  * amplitude `np.abs(coeffs)`; wrapped phase difference vs. the first frame
    `np.mod(pi + angle(cur) - angle(ref), 2*pi) - pi` (eq. 2)
  * amplitude-weighted signal `mean(dphase * amp**2) / sum(amp)` (eq. 3)
  * per-band alignment to band `(0, 0)` then summation (eqs. 4–5)

`backend/processing/signal_processing.py`
* `get_scaled_sound()` — same centre-and-scale-to-[-1,1] as the reference.
* Butterworth high-pass — same `scipy.signal.butter(order, cutoff,
  btype='highpass', output='sos')` + `sosfilt` the reference applies at the end
  of `sound_from_video` (moved here so the core returns the raw signal).
* `spectral_subtraction()` — adaptation of `get_soud_spec_sub()` (STFT →
  per-frequency quantile noise floor → subtract → clip → ISTFT).

### Changed / fixed relative to the reference

| # | Reference behaviour | Problem | Fix in Acoustic Eye |
|---|---------------------|---------|---------------------|
| 1 | `nframes = int(video.get(cv.CAP_PROP_FRAME_COUNT))`, then `sound = np.zeros(nframes)` | Container metadata is often wrong (VFR, dropped/corrupt frames, truncated files); mismatched lengths break the final `sound += sig_aligned` broadcast. | Never allocate from metadata. `video_reader` counts frames it can actually grab/decode; the output length is `len(signals[ref_band])`; every band signal is length-harmonised before summation. |
| 2 | Per-frame decode/gray/normalise happen inside the algorithm loop with no error handling | One unreadable frame throws (`cvtColor`/`resize` on `None`) and aborts the whole run. | `video_reader.iter_gray_norm_frames` isolates decoding, skips bad frames, and yields only usable ones. |
| 3 | `get_scaled_sound` divides by `max - min` unconditionally | Silent / constant signal → divide-by-zero → `inf`/`nan` in the WAV. | Guard: range ≤ 1e-12 → return zeros. |
| 4 | `total_amp = np.sum(amp)` used as a divisor with no check | Fully dark / zero-contrast band → divide-by-zero → `nan` propagates into the sum. | `total_amp <= 0` → contribute `0.0` for that frame/band. |
| 5 | `get_soud_spec_sub` reconstructs the STFT as `st_mags * (1j * st_angles)` | That is **not** a phasor (`magnitude · exp(iθ)`); it scrambles phase and produces a distorted result. | Correct reconstruction `mags * np.exp(1j * angles)`; ISTFT output trimmed/padded back to the input length. |
| 6 | `downsample_factor=0.1` hard-wired at the call site | On small frames `0.1×` collapses the image and the pyramid fails. | `downsample` is configurable and auto-relaxed so the shorter side stays ≥ 24 px (a processing note reports when this happens). |
| 7 | `import pyrtools` at module top | Missing dependency → raw `ImportError` traceback for the user. | Guarded import; typed `PyrtoolsUnavailableError`; `/health` + a UI banner explain the fix. |
| 8 | Output written with `scipy.io.wavfile` as 64-bit float WAV | 64-bit float WAV is not reliably playable in browsers. | Written with `soundfile` as 16-bit PCM. |
| 9 | Spectrogram window `NFFT` defaults (256) | Fails / warns on very short recovered signals. | `NFFT` chosen as the largest power of two ≤ signal length (32–1024). |
| 10 | Alignment reference hard-coded to key `(0, 0)` | `KeyError` for unusual pyramid configs (e.g. `scales`/`orientations` combos without that key). | Uses `(0, 0)` when present, else the first oriented band, else the first key. |
| 11 | Blocking CLI, `plt.show()` | Not usable from a web server. | Non-blocking pipeline with a background worker, staged progress, Matplotlib `Agg`. |

### Newly written for Acoustic Eye

* `backend/main.py`, `backend/api/routes.py` — FastAPI app, endpoints, in-memory
  job store, background worker, stage-progress reporting.
* `backend/config.py` — all parameters + limits + pathlib paths, optional
  `config.json` overrides.
* `backend/processing/video_reader.py` — robust open/validate/probe/iterate with
  real frame counting.
* `backend/processing/audio_writer.py` — `soundfile` WAV writing, waveform &
  spectrogram PNG rendering.
* `backend/processing/text_report.py` — signal-to-text description (`analyze_signal`)
  and optional offline speech-to-text (`transcribe`, `faster-whisper`).
* `backend/processing/pipeline.py` — end-to-end orchestration + `PipelineResult`.
* `backend/utils/file_handler.py` — unique server-side filenames, extension
  whitelist, size cap, path-traversal guards, TTL cleanup.
* `frontend/` — the entire website (upload, preview, params, polling, results).
* `tests/` — synthetic-fixture tests for the reader, signal helpers, pipeline,
  and API.

### License / attribution requirements met

* MIT text retained in `LICENSE` with the original copyright line for
  Musolino & Sforza; each adapted source file carries an attribution header.
* The paper and `pyrtools` are cited in `README.md`, `LICENSE`, and the site's
  *About* page.
* No claim of originality over the Visual Microphone algorithm.

---

## 11. Testing

With the venv active, from `acoustic-eye/`:

```bash
pip install -r backend/requirements.txt
pytest
```

* `tests/test_video.py` — valid video probes; empty / corrupt / missing /
  too-short rejected; `iter_gray_norm_frames` shape, count, `max_frames`, and
  small-input down-sample relaxation.
* `tests/test_processing.py` — `get_scaled_sound` range + constant-input safety;
  high-pass removes DC; spectral subtraction shape/finiteness; `to_int16`
  clipping; WAV writing + `wav_info`; visualisation files exist; **full pipeline
  end-to-end** (marked `slow`, auto-skipped without `pyrtools`) asserting
  `sample_rate == fps`, `frames_processed`, and that the WAV + PNGs exist with
  the expected properties.
* `tests/test_api.py` — `/health` (incl. `local_ingest`, `transcription_available`),
  index served, upload rejects bad extension / empty file, upload accepts a real
  synthetic video, `/result` path-traversal blocked, unknown job → 404,
  `/process-local` path guards + a full local-segment run.
* `tests/test_text_report.py` — `analyze_signal` dominant-frequency / band-energy /
  burst detection, silent- and tiny-input safety, and that `transcribe` degrades
  gracefully whether or not `faster-whisper` is installed.

37 tests total (the `slow` end-to-end runs need `pyrtools`; everything else is fast).

Fast subset (no pyrtools / no heavy run):

```bash
pytest -m "not slow"
```

---

## 12. Troubleshooting

**"The website isn't working" / page won't load / buttons do nothing**
Work through these in order:

1. **Is the server running?** You need a terminal window showing
   `Uvicorn running on http://127.0.0.1:8000`. If not, run `start.bat` or
   `python run.py`. Closing that window stops the site.
2. **Did you open the file directly?** Opening `frontend/index.html` by
   double-click (`file:///…/index.html`) will show the page but nothing works —
   there is no backend. You must visit **http://127.0.0.1:8000**.
3. **`ModuleNotFoundError: No module named 'backend'`** when starting — you ran
   `uvicorn` from the wrong folder. `cd` into `acoustic-eye/` first, or just use
   `python run.py` / `start.bat` (they don't care about the current directory).
4. **`'uvicorn' is not recognized`** — the venv isn't active. Use
   `.venv\Scripts\python.exe run.py`, or activate with
   `.venv\Scripts\activate` first.
5. **Browser says "can't connect" / `ERR_CONNECTION_REFUSED`** — the server
   isn't up on that port, or another program uses 8000. Try
   `python run.py --port 9000` and open `http://127.0.0.1:9000`.
6. **Yellow banner "pyrtools is not installed"** — upload/validation work but
   reconstruction won't. `pip install pyrtools` (see below) and restart.
7. Still stuck? Open `http://127.0.0.1:8000/health` — if that returns JSON the
   server is fine and the problem is in the browser (hard-refresh with
   Ctrl+F5); if it doesn't load, the server isn't running.

**`pyrtools` won't install / `ModuleNotFoundError: pyrtools`**
Pure-Python wheel; usually just `pip install pyrtools`. If it tries to compile:
`python -m pip install --upgrade pip setuptools wheel`, then
`pip install numpy scipy matplotlib`, then retry. Last resort: install the
Visual Studio Build Tools "Desktop development with C++" workload. The app runs
without it (validation only) and tells you so via `/health` and a banner.

**MSVC / "Microsoft Visual C++ 14.0 or greater is required"**
Only appears if a dependency falls back to a source build. Upgrading
`pip`/`setuptools`/`wheel` and installing `numpy`/`scipy` first almost always
avoids it. Otherwise install the C++ Build Tools linked above.

**OpenCV: `ImportError: DLL load failed` / `cv2` won't import**
Use the pinned `opencv-python-headless`. Don't install both `opencv-python` and
`opencv-python-headless` — `pip uninstall opencv-python opencv-python-headless`
then reinstall only the headless one. On a minimal Windows image you may also
need the [VC++ 2015–2022 Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

**Upload fails with "could not be opened as a video"**
The container/codec isn't supported by your OpenCV build (some `.mkv`/HEVC
files). Re-encode to H.264 MP4, e.g. with ffmpeg:
`ffmpeg -i input.mov -c:v libx264 -an output.mp4`.

**"too few usable frames" / "no image frames could be read"**
The clip is shorter than `MIN_USABLE_FRAMES` (30) real frames, is audio-only, or
every frame failed to decode. Use a longer clip with an actual video stream.

**Processing is very slow**
Lower `downsample` (e.g. `0.1`), keep `scales = 1` and `orientations = 2`, use a
shorter and/or lower-resolution clip, and reduce `MAX_PROCESS_FRAMES`. A pyramid
is built per frame — cost is roughly linear in frame count and frame area.

**`MemoryError` during "Extracting local phase"**
Same levers as above (smaller `downsample`, fewer scales/orientations, shorter
clip). Per-frame memory depends on frame size, not clip length.

**Server starts but the page is unstyled / JS 404s**
Run `uvicorn` from the `acoustic-eye/` directory (the one containing both
`backend/` and `frontend/`), so `/css` and `/js` mounts resolve.

**PowerShell "running scripts is disabled"**
`Set-ExecutionPolicy -Scope Process RemoteSigned` before activating the venv, or
use `cmd.exe` with `.venv\Scripts\activate.bat`.

**Browser can't play the WAV**
It's 16-bit PCM and should play everywhere; if not, download it and open in any
audio player. Check `http://127.0.0.1:8000/docs` → `/health` is reachable.

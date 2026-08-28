# API Reference

Base URL `http://127.0.0.1:8000` · all endpoints under `/api` · JSON unless noted.
Interactive documentation at `/docs`.

Errors return `{"detail": "<readable message>"}`. Stack traces are never returned to the
client; full detail is logged on the backend.

---

## `GET /api/health`

Component availability and server configuration.

```json
{
  "status": "ok", "ffmpeg": true,
  "action_recognition_env": true, "sound_generation_env": true,
  "moss_checkpoints": true, "demo_available": true,
  "stages": [{"key": "upload", "label": "Video uploaded"}, "..."],
  "defaults": {"seed": 42, "steps": 50, "cfg_scale": 4.0,
               "sigma_shift": 5.0, "duration": 10.0, "sample_rate": 48000},
  "limits": {"max_upload_mb": 200, "max_video_seconds": 60,
             "allowed": [".avi", ".m4v", ".mkv", ".mov", ".mp4"]}
}
```

## `GET /api/actions/supported`

The registered Foley classes and the keywords that map to them.

## `POST /api/upload`

`multipart/form-data`, field `file`. Creates a job.

**200** `{"job_id", "video": {...}, "warnings": [...], "original_filename"}`
**400** unsupported extension, undecodable file, too long, too large
**413** exceeds the size limit

## `POST /api/demo`

Creates a job against the bundled validated clip. Reuses the stored Module 2 timeline for
that specific video; every other stage runs for real.

## `POST /api/process/{job_id}`

Starts background processing. Optional body overrides settings:

```json
{"seed": 42, "steps": 50, "cfg_scale": 4, "sigma_shift": 5,
 "duration": 10, "sample_rate": 48000}
```

Unknown keys are ignored. Returns immediately — poll `/api/status`.

## `GET /api/status/{job_id}`

```json
{
  "job_id": "a1b2c3", "status": "running", "progress": 57.0,
  "current_stage": "foley_generation",
  "stages": {"upload": "done", "validation": "done",
             "action_recognition": "done", "timeline": "done",
             "foley_generation": "active", "visual_sync": "pending",
             "audio_mixing": "pending", "rendering": "pending"},
  "errors": [], "warnings": [], "counts": {},
  "generated_audio": [{"key": "walking", "label": "Walking", "cached": false}],
  "updated_at": "2026-08-25T15:18:51Z"
}
```

Poll every 1–2 s. `status` becomes `completed` or `failed`.

## `GET /api/actions/{job_id}`

Action timeline, located visual events, and intervals left silent. Available as soon as
the `timeline` stage completes, so the UI can show it during Foley generation.

```json
{
  "actions": [{"action": "walk around table", "start": 1.5, "end": 2.5,
               "status": "suspect", "confidence": "Medium"}],
  "visual_events": [{"action": "walk around table", "kind": "foot_contact",
                     "t_s": 0.458, "confidence": "high", "basis": "..."}],
  "unsupported": [{"action": "stand", "start": 0.0, "end": 1.5, "reason": "..."}]
}
```

## `GET /api/result/{job_id}`

Full result. **409** if the job is not `completed`.

```json
{
  "job_id": "a1b2c3",
  "video_url": "/api/video/a1b2c3", "audio_url": "/api/audio/a1b2c3",
  "download_url": "/api/download/a1b2c3",
  "counts": {"actions_detected": 5, "sounds_generated": 4,
             "placements": 6, "unsupported_actions": 1},
  "sync": {"worst_error_ms": 20.3, "note": "..."},
  "mix": {"peak_dbfs": -6.0, "rms_dbfs": -36.9, "crest_db": 30.9,
          "clipped_samples": 0, "duration_s": 10.005},
  "render": {"video_codec": "h264", "audio_codec": "aac", "frames": 240,
             "audio_sample_rate": 48000, "video_stream_copied": true},
  "actions": [...], "generated": [...], "unsupported": [...]
}
```

## Media endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/preview/{job_id}` | the uploaded source video (for the pre-processing preview) |
| `GET /api/video/{job_id}` | the final video, inline |
| `GET /api/audio/{job_id}` | the mixed audio, 48 kHz mono WAV |
| `GET /api/download/{job_id}` | the final video as `final_silent_to_audio.mp4` |
| `GET /api/report/{job_id}` | the full processing report as JSON |

## `GET /api/jobs?limit=20`

Recent jobs with id, status, progress and creation time.

---

## Status codes

| Code | Meaning |
|---|---|
| 200 | success |
| 400 | invalid input — unsupported format, undecodable, too long |
| 404 | unknown job, or artefact not ready |
| 409 | job not in a state that allows the request |
| 413 | upload exceeds the size limit |
| 500 | unexpected server error (details logged, not returned) |

## Typical client flow

```js
const { job_id } = await api.upload(file)
await api.process(job_id, settings)
const poll = setInterval(async () => {
  const s = await api.status(job_id)
  if (s.stages.timeline === 'done') showTimeline(await api.actions(job_id))
  if (s.status === 'completed') { clearInterval(poll); show(await api.result(job_id)) }
  if (s.status === 'failed')    { clearInterval(poll); showError(s.errors[0]) }
}, 1500)
```

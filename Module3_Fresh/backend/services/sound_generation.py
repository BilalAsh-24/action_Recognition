"""Module 3 Foley generation. Calls the validated phased MOSS wrapper, with caching.

Generation costs several minutes, so every asset is cached by a content hash over
(action key, prompt, negative prompt, seed, steps, cfg, sigma_shift, duration,
sample rate). An identical request reuses the cached WAV.
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C
from services.prompt_map import FoleySpec
from services import foley_validation as FV


class SoundGenerationError(Exception):
    pass


def _backend_name(settings: dict) -> str:
    return settings.get("backend") or C.GENERATION_BACKEND


def cache_key(spec: FoleySpec, settings: dict) -> str:
    """Content hash over everything that affects the audio.

    Numeric settings are normalised before hashing. Without this, a client sending
    `duration: 10` (int) and a default of `10.0` (float) serialise differently and
    produce different keys for byte-identical audio, causing needless regeneration.
    """
    payload = {"backend": _backend_name(settings),
               "action": spec.key, "prompt": spec.prompt, "negative": spec.negative,
               "seed": int(settings["seed"]), "steps": int(settings["steps"]),
               "cfg": round(float(settings["cfg_scale"]), 4),
               "sigma": round(float(settings["sigma_shift"]), 4),
               "seconds": round(float(settings["duration"]), 4),
               "sr": int(settings["sample_rate"]), "model": str(settings["model"])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def cached_path(spec: FoleySpec, settings: dict) -> Path:
    return C.GENERATED / f"{_backend_name(settings)}_{spec.key}_{cache_key(spec, settings)}.wav"


def _to_pipeline_format(src: Path, dst: Path, sample_rate: int) -> None:
    """Convert a runner's native output to the pipeline format: mono, 48 kHz, PCM_16."""
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
                        str(dst)], capture_output=True, text=True)
    if r.returncode != 0 or not dst.is_file():
        raise SoundGenerationError(f"Could not convert generated audio: "
                                   f"{(r.stderr or '').strip()[:200]}")


def _guard_memory(min_gb: float) -> None:
    import psutil
    avail = psutil.virtual_memory().available / 1e9
    if avail < min_gb:
        raise SoundGenerationError(
            f"Sound generation was not started because only {avail:.1f} GB of memory is "
            f"free. Close other applications and try again.")


def generate(spec: FoleySpec, settings: dict, timeout_s: int = 3600) -> tuple[Path, bool]:
    """Return (wav_path, was_cached). Dispatches to the active generation backend.

    Output is always normalised to the pipeline format (48 kHz mono PCM_16) regardless
    of what the backend natively produces, so the rest of the system is backend-agnostic.
    """
    name = _backend_name(settings)
    if name not in C.BACKENDS:
        raise SoundGenerationError(f"Unknown generation backend '{name}'.")
    b = C.BACKENDS[name]
    out = cached_path(spec, settings)
    if out.is_file() and out.stat().st_size > 1000:
        return out, True
    if not Path(b["python"]).exists():
        raise SoundGenerationError(
            f"The environment for {b['label']} is unavailable on this machine.")
    _guard_memory(C.MIN_AVAILABLE_GB)

    sr = int(settings["sample_rate"])
    if name == "moss":
        if not C.MOSS_CKPT.is_dir():
            raise SoundGenerationError("MOSS-SoundEffect checkpoints were not found.")
        cmd = [str(b["python"]), str(C.MOSS_SCRIPTS / "moss_generate.py"),
               "--label", f"web_{spec.key}_{cache_key(spec, settings)}",
               "--out", str(out.relative_to(C.MODULE3)),
               "--prompt", spec.prompt, "--negative", spec.negative,
               "--seed", str(settings["seed"]), "--seconds", str(settings["duration"]),
               "--steps", str(settings["steps"]), "--cfg", str(settings["cfg_scale"]),
               "--sigma_shift", str(settings["sigma_shift"]),
               "--full-seconds", str(int(settings.get("full_seconds", 10)))]
        native = out                      # MOSS already emits 48 kHz mono
    else:
        native = out.with_suffix(".native.wav")
        cmd = [str(b["python"]), str(C.RUNNERS / "run_stable_audio.py"),
               "--out", str(native), "--prompt", spec.prompt,
               "--negative", spec.negative, "--seconds", str(settings["duration"]),
               "--steps", str(settings["steps"]), "--cfg", str(settings["cfg_scale"]),
               "--seed", str(settings["seed"])]

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                       env=C.ENV_NO_PYC, cwd=str(C.MODULE3))
    if p.returncode != 0 or not native.is_file():
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
        msg = " / ".join(tail) if tail else "unknown error"
        try:
            msg = json.loads(tail[-1]).get("error", msg)
        except Exception:
            pass
        if ("available" in msg and "GB" in msg) or "MemoryError" in msg:
            raise SoundGenerationError(
                "Sound generation stopped because the machine ran low on memory. "
                "Close other applications and try again.")
        raise SoundGenerationError(f"Sound generation failed for '{spec.label}' "
                                   f"using {b['label']}: {msg}")

    if native != out:
        _to_pipeline_format(native, out, sr)
        native.unlink(missing_ok=True)   # intermediate, not a cache entry
    return out, False


def generate_best(spec: FoleySpec, settings: dict, max_candidates: int = 3,
                  on_progress=None, timeout_s: int = 3600) -> tuple[dict | None, list[dict]]:
    """Generate up to `max_candidates` variants and return the best that passes the gate.

    MOSS occasionally collapses to degenerate output for a given seed — a sampling
    failure rather than a capability limit. Trying a different seed is therefore the
    cheapest available remedy.

    Cost control: candidates are generated one at a time and the loop stops as soon as
    one passes the gate with a score at or above GOOD_ENOUGH_SCORE. A class that works
    on the first seed costs exactly one generation. Every candidate is cached under its
    own key, so nothing is ever generated twice.

    Returns (best_or_None, attempts).
    """
    attempts: list[dict] = []
    best: dict | None = None
    base = int(settings["seed"])

    for i in range(max(1, max_candidates)):
        st = {**settings, "seed": base + i}
        if on_progress:
            on_progress(i + 1, max_candidates, st["seed"])
        path, cached = generate(spec, st, timeout_s=timeout_s)
        v = FV.validate(path, spec.target_rms_dbfs, int(st["sample_rate"]))
        rec = {"candidate": i + 1, "seed": st["seed"], "path": str(path),
               "cached": cached, "ok": v.ok, "score": v.score,
               "reason": v.reason, "failures": v.failures,
               "metrics": v.metrics.dict()}
        attempts.append(rec)

        if v.ok and (best is None or v.score > best["score"]):
            best = rec
        if v.ok and v.score >= FV.GOOD_ENOUGH_SCORE:
            break

    return best, attempts

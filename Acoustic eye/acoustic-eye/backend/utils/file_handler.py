"""
Safe file handling helpers: unique names, extension whitelisting, size limits
and path-traversal protection.  Uploaded files are only ever written to
``uploads/`` and results are only ever read from ``outputs/``.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import BinaryIO, Iterable

from .. import config as _cfg
from ..config import (
    ALLOWED_VIDEO_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    OUTPUT_DIR,
    RESULT_TTL_SECONDS,
    UPLOAD_DIR,
)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CHUNK = 1024 * 1024  # 1 MiB


class UploadError(Exception):
    """User-facing upload / file validation failure."""


def new_job_id() -> str:
    """Opaque, collision-resistant identifier for a job / its files."""
    return uuid.uuid4().hex


def validate_extension(filename: str) -> str:
    """Return the lower-case extension if allowed, else raise :class:`UploadError`."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(ALLOWED_VIDEO_EXTENSIONS)
        raise UploadError(
            f"Unsupported file type '{ext or '(none)'}'. "
            f"Please upload one of: {allowed}."
        )
    return ext


def save_stream_to_upload(stream: BinaryIO, original_filename: str) -> tuple[Path, str]:
    """Stream an upload to ``uploads/<job_id><ext>`` with a hard size cap.

    The user-supplied filename is used **only** to pick a validated extension;
    the stored name is server-generated, so path traversal and clobbering are
    impossible.

    Returns ``(stored_path, job_id)``.
    """
    ext = validate_extension(original_filename)
    job_id = new_job_id()
    dest = UPLOAD_DIR / f"{job_id}{ext}"

    total = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise UploadError(
                        f"File too large. The maximum upload size is "
                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                    )
                out.write(chunk)
    except UploadError:
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise UploadError(f"Could not save the uploaded file: {exc}") from exc

    if total == 0:
        dest.unlink(missing_ok=True)
        raise UploadError("The uploaded file is empty.")

    return dest, job_id


def resolve_output_file(filename: str) -> Path:
    """Resolve ``filename`` inside ``outputs/`` safely.

    Rejects anything that is not a plain name or that escapes the directory.
    Raises :class:`UploadError` (400-worthy) or ``FileNotFoundError`` (404).
    """
    name = Path(filename).name  # strip any directory component
    if name != filename or not _SAFE_NAME_RE.match(name):
        raise UploadError("Invalid result filename.")
    candidate = (OUTPUT_DIR / name).resolve()
    if OUTPUT_DIR.resolve() not in candidate.parents:
        raise UploadError("Invalid result path.")
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate


def find_upload(job_id: str) -> Path:
    """Locate a previously stored upload by job id. Raises ``FileNotFoundError``."""
    if not _SAFE_NAME_RE.match(job_id or ""):
        raise UploadError("Invalid job id.")
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        p = UPLOAD_DIR / f"{job_id}{ext}"
        if p.is_file():
            return p
    raise FileNotFoundError(job_id)


class LocalIngestError(Exception):
    """User-facing error for the local-file (no-upload) processing path."""


def resolve_local_video_path(raw_path: str) -> Path:
    """Validate a user-supplied local filesystem path for /process-local.

    Guards:
      * the feature must be enabled (``ALLOW_LOCAL_PATH_INGEST``),
      * the path must exist and be a regular file,
      * its extension must be a whitelisted video container,
      * it must resolve *inside* one of ``LOCAL_PATH_ALLOWED_ROOTS``
        (blocks ``..`` escapes and reading arbitrary system files).

    The file is never copied, moved, modified or deleted -- only read.
    """
    if not getattr(_cfg, "ALLOW_LOCAL_PATH_INGEST", False):
        raise LocalIngestError(
            "Local-file processing is disabled on this server "
            "(set allow_local_path_ingest to true in backend/config.json)."
        )
    if not raw_path or not raw_path.strip():
        raise LocalIngestError("No file path was provided.")

    try:
        candidate = Path(raw_path.strip().strip('"')).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise LocalIngestError(f"That path could not be understood: {exc}") from exc

    if candidate.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(ALLOWED_VIDEO_EXTENSIONS)
        raise LocalIngestError(
            f"Unsupported file type '{candidate.suffix or '(none)'}'. Allowed: {allowed}."
        )
    if not candidate.is_file():
        raise LocalIngestError(f"No file exists at: {candidate}")

    roots = [Path(r).expanduser().resolve(strict=False)
             for r in getattr(_cfg, "LOCAL_PATH_ALLOWED_ROOTS", ())]
    if roots and not any(
        candidate == root or root in candidate.parents for root in roots
    ):
        pretty = " ; ".join(str(r) for r in roots)
        raise LocalIngestError(
            "For safety, local files must live inside an allowed folder. "
            f"Allowed: {pretty}. "
            "Add more via local_path_allowed_roots in backend/config.json."
        )
    return candidate


def cleanup_old_files(dirs: Iterable[Path] | None = None, ttl_seconds: int = RESULT_TTL_SECONDS) -> int:
    """Delete files older than ``ttl_seconds`` from the given dirs (default:
    uploads + outputs). Returns the number of files removed. Best-effort."""
    targets = list(dirs) if dirs is not None else [UPLOAD_DIR, OUTPUT_DIR]
    now = time.time()
    removed = 0
    for d in targets:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.name == ".gitkeep" or not f.is_file():
                continue
            try:
                if now - f.stat().st_mtime > ttl_seconds:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed

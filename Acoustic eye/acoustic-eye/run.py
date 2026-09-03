#!/usr/bin/env python
"""
One-command launcher for Acoustic Eye.

    python run.py                 # http://127.0.0.1:8000
    python run.py --port 9000
    python run.py --host 0.0.0.0  # reachable from other devices on your LAN
    python run.py --reload        # auto-restart on code changes (development)

Works from any directory: it resolves its own location, switches into the
project root and makes it importable, so "no module named 'backend'" and
"frontend not found" can't happen regardless of where you launch it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the Acoustic Eye web app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true",
                    help="auto-reload on code changes (development only)")
    args = ap.parse_args()

    try:
        import uvicorn
    except ModuleNotFoundError:
        sys.stderr.write(
            "\n[Acoustic Eye] Python dependencies are not installed.\n"
            "  1) create a venv:   python -m venv .venv\n"
            "  2) activate it:     .venv\\Scripts\\activate   (Windows)\n"
            "  3) install:         pip install -r backend/requirements.txt\n"
            "  ...or just run  start.bat  which does all of this.\n\n"
        )
        return 1

    try:
        import backend.main  # noqa: F401  (import check only)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"\n[Acoustic Eye] The application failed to load: "
            f"{type(exc).__name__}: {exc}\n\n"
        )
        return 1

    url_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(
        "\n"
        "  ------------------------------------------------\n"
        "   Acoustic Eye is running.\n"
        f"   Open  http://{url_host}:{args.port}  in your browser.\n"
        "   Press Ctrl+C in this window to stop it.\n"
        "  ------------------------------------------------\n",
        flush=True,
    )
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

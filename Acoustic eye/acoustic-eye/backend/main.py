"""
Acoustic Eye -- FastAPI application entry point.

Run locally (from the repository root, i.e. the folder that contains
``backend/`` and ``frontend/``)::

    uvicorn backend.main:app --reload

Then open  http://127.0.0.1:8000  in a browser.

The frontend (static HTML/CSS/JS) is served by this same app, so there is no
separate web server and no CORS hassle for the default setup.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, FRONTEND_DIR
from .api.routes import router as api_router

app = FastAPI(
    title="Acoustic Eye",
    description="Recovering acoustic information from visual vibrations "
    "(phase-based Visual Microphone, Davis et al., SIGGRAPH 2014).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# API routes first so they take precedence over the static mount.
app.include_router(api_router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.is_file():
        return JSONResponse(  # type: ignore[return-value]
            status_code=500,
            content={"detail": "Frontend not found. Expected frontend/index.html."},
        )
    return FileResponse(index_file, media_type="text/html")


# Static assets (css/, js/, and index.html itself under /static for safety).
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    # Also expose css/ and js/ at the paths index.html references.
    css_dir = FRONTEND_DIR / "css"
    js_dir = FRONTEND_DIR / "js"
    if css_dir.is_dir():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


if __name__ == "__main__":  # pragma: no cover - convenience launcher
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)

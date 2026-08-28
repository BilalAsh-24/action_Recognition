"""ACTION RECOGNITION AND SOUND GENERATION — FastAPI backend."""
from __future__ import annotations
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api.routes import router

app = FastAPI(title="Action Recognition and Sound Generation",
              description="Transform silent videos into synchronized sound",
              version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def root():
    return {"name": "ACTION RECOGNITION AND SOUND GENERATION",
            "subtitle": "Transform silent videos into synchronized sound",
            "docs": "/docs", "health": "/api/health"}

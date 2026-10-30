import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import create_router
from app.config import DATABASE_URL, UPLOADS
from app.db import make_session_factory
from app.jobs import Runner


def _default_runner() -> Runner:
    from app.pipeline import run_clip  # imported late: pulls in the model clients, which tests replace

    return run_clip


def create_app(database_url: str = DATABASE_URL, uploads: Path = UPLOADS, runner: Runner | None = None) -> FastAPI:
    app = FastAPI(title="LedgerEyes API")

    # Comma-separated list of allowed frontend origins (the Vercel domain in production).
    origins = [o for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(create_router(make_session_factory(database_url), uploads, runner or _default_runner()))
    return app


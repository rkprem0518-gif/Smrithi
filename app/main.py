"""FastAPI app factory: routers, static UI, startup (DB, demo seed, poller)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import health
from app.db import init_db
from app.settings import get_settings

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.demo_mode:
        settings.require_live()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Smriti", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()

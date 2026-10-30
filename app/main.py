"""FastAPI app factory: routers, static UI, startup (DB, demo seed, poller)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import demo, health, review, sessions, webhook
from app.db import init_db
from app.logs import log
from app.services.orchestrator import seed_demo_sessions
from app.services.poller import run_poller
from app.settings import get_settings

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.demo_mode:
        settings.require_live()  # fail fast with a clear message
    init_db()
    stop = asyncio.Event()
    poller: asyncio.Task | None = None
    if settings.demo_mode:
        seed_demo_sessions(settings)
    else:
        poller = asyncio.create_task(run_poller(settings, stop))
        if not settings.webhook_reachable:
            log("webhook_not_reachable", hint="PUBLIC_BASE_URL is not public https; relying on the poller")
    log("startup", demo_mode=settings.demo_mode, bolna_configured=settings.bolna_configured)
    yield
    stop.set()
    if poller:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller


def create_app() -> FastAPI:
    app = FastAPI(title="Smriti", version="0.1.0", lifespan=lifespan)
    for module in (health, sessions, webhook, review, demo):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/index.html")

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()

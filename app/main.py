"""FastAPI app factory: routers, static UI, startup (DB, demo seed, poller)."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import demo, events, family, health, ops, review, sessions, webhook
from app.db import init_db, new_db
from app.family import seed as family_seed
from app.logs import log
from app.services.ops import reset_wallet_cache
from app.services.orchestrator import seed_demo_sessions
from app.services.poller import run_poller
from app.settings import get_settings

WEB_DIR = Path(__file__).resolve().parent / "web"
_TOKEN_IN_URL = re.compile(r"(token=)[^&\s\"]+")


class _RedactTokenFilter(logging.Filter):
    """uvicorn's access log prints full URLs; hide the webhook token in them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_IN_URL.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        record.msg = _TOKEN_IN_URL.sub(r"\1***", str(record.msg))
        return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.getLogger("uvicorn.access").addFilter(_RedactTokenFilter())
    if not settings.demo_mode:
        settings.require_live()  # fail fast with a clear message
    init_db()
    reset_wallet_cache()
    if settings.seed_family_demo:
        with new_db() as db:
            family_seed.seed(db, settings)  # no-op once the demo parent exists
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
    for module in (health, sessions, webhook, review, demo, events, ops, family):
        app.include_router(module.router)
    app.include_router(family.care)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/index.html")

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()

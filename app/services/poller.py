"""Background poller: for open sessions, GET /executions/{id} every POLL interval.

Used when Bolna cannot reach our webhook (no public URL), and as a safety net otherwise.
Gives up after `poll_give_up_minutes` and marks the session failed.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, timedelta

from sqlmodel import select

from app.db import new_db
from app.logs import log
from app.models import Session, Status, utcnow
from app.services.bolna_client import BolnaClient, BolnaError
from app.services.orchestrator import apply_execution
from app.settings import Settings


async def poll_once(settings: Settings, client: BolnaClient) -> int:
    """One sweep. Returns the number of sessions checked."""
    give_up = timedelta(minutes=settings.poll_give_up_minutes)
    with new_db() as db:
        open_sessions = db.exec(
            select(Session).where(
                Session.status.in_(Status.OPEN),  # type: ignore[attr-defined]
                Session.execution_id.is_not(None),  # type: ignore[union-attr]
                Session.deleted_at.is_(None),  # type: ignore[union-attr]
                Session.is_demo == False,  # noqa: E712
            )
        ).all()
        for session in open_sessions:
            created = session.created_at if session.created_at.tzinfo else session.created_at.replace(tzinfo=UTC)
            if utcnow() - created > give_up:
                session.status = Status.FAILED
                session.error = "No final call status from Bolna within the time limit."
                session.updated_at = utcnow()
                db.add(session)
                db.commit()
                log("poll_gave_up", session_id=session.id, execution_id=session.execution_id)
                continue
            try:
                execution = await client.get_execution(session.execution_id or "")
                await apply_execution(db, session, execution, settings)
            except BolnaError as exc:
                log("poll_error", session_id=session.id, status_code=exc.status_code)
        return len(open_sessions)


async def run_poller(settings: Settings, stop: asyncio.Event) -> None:
    log("poller_started", interval_s=settings.poll_interval_seconds)
    async with BolnaClient.from_settings(settings) as client:
        while not stop.is_set():
            try:
                await poll_once(settings, client)
            except Exception as exc:  # never let the loop die
                log("poller_crash", error=type(exc).__name__)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)

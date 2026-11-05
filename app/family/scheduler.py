"""Runs scheduled check-ins when they are due. Off unless SCHEDULER_ENABLED=1, so a demo laptop never places a
real call by surprise; "Run now" in the app starts one on purpose.

A real scheduled call needs the parent's phone number, which Smriti does not store in plain text. Until an
encrypted number vault exists, the scheduler only runs in demo mode (simulated calls)."""

from __future__ import annotations

import asyncio
import contextlib

from sqlmodel import select

from app.db import new_db
from app.family import people, service
from app.family.models import Parent, Schedule
from app.logs import log
from app.models import utcnow
from app.settings import Settings


async def run_once(settings: Settings) -> int:
    started = 0
    with new_db() as db:
        for s in db.exec(select(Schedule).where(Schedule.active == True)).all():  # noqa: E712
            if not people.due(s):
                continue
            parent = db.get(Parent, s.parent_id)
            s.last_run_at = utcnow()
            db.add(s)
            db.commit()
            if not parent or parent.calls_paused or not settings.demo_mode:
                people.log(
                    db, s.parent_id, f"“{s.label}” is due. Start it from the app (Run now).", kind="schedule", ref=s.id
                )
                continue
            data, topics, remembered = service.checkin_user_data(db, parent, questions=s.questions)
            await service.start_call(
                db,
                kind="checkin",
                parent=parent,
                phone=None,
                settings=settings,
                user_data=data,
                topics=topics,
                remembered=remembered,
            )
            started += 1
    return started


async def run_scheduler(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await run_once(settings)
        except Exception as exc:  # keep the loop alive; the next tick tries again
            log("scheduler_error", error=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=30)

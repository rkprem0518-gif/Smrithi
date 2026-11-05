"""Server-Sent Events: the UI's live view of session status changes.

    GET /api/events?session_id=<id>     one session (anyone holding the session id, like its report)
    GET /api/events                     every session; needs the reviewer token (header or ?token=,
                                        since a browser EventSource cannot send headers)

Each message is `id: <n>` + `data: <json>` with no `event:` name, so `EventSource.onmessage` gets
everything; the JSON has a `type`: `snapshot` (current status, sent first for one session),
`session_status` or `session_ops`. A `: keep-alive` comment goes out every SSE_KEEPALIVE_SECONDS.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.api.review import check_reviewer_token
from app.db import new_db
from app.models import Session
from app.services.events import Subscription, bus
from app.settings import get_settings

router = APIRouter(tags=["events"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def format_sse(event: dict[str, Any]) -> str:
    return f"id: {event.get('id', 0)}\ndata: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"


def _snapshot(session_id: str) -> dict[str, Any]:
    with new_db() as db:
        session = db.get(Session, session_id)
        if not session or session.deleted_at:
            raise HTTPException(404, "Session not found")
        return {"id": 0, "type": "snapshot", "session_id": session.id, "status": session.status,
                "review_status": session.review_status, "is_demo": session.is_demo}


async def _stream(sub: Subscription, first: dict[str, Any] | None, keepalive: float) -> AsyncIterator[str]:
    try:
        yield "retry: 3000\n\n"
        if first:
            yield format_sse(first)
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=keepalive)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield format_sse(event)
    finally:  # client went away (the response task is cancelled) or the server is shutting down
        bus.unsubscribe(sub)


@router.get("/api/events")
async def session_events(
    session_id: str | None = None, token: str = "", authorization: str = Header(default="")
) -> StreamingResponse:
    if not session_id:
        check_reviewer_token(token or authorization.removeprefix("Bearer ").strip())
    # Subscribe before the snapshot so nothing published in between is lost (at worst it arrives twice).
    sub = bus.subscribe(session_id)
    first: dict[str, Any] | None = None
    if session_id:
        try:
            first = _snapshot(session_id)
        except HTTPException:
            bus.unsubscribe(sub)
            raise
    return StreamingResponse(_stream(sub, first, get_settings().sse_keepalive_seconds),
                             media_type="text/event-stream", headers=SSE_HEADERS)

"""In-process pub/sub for live UI updates (served as Server-Sent Events by app/api/events.py).

Publishers are plain functions called from sync or async code, on the event loop or in a worker
thread (sync FastAPI endpoints run in a threadpool), so delivery goes through
`loop.call_soon_threadsafe` onto each subscriber's own loop. Events carry ids and statuses only,
never transcripts or phone data. One process only: with several workers each has its own bus.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import threading
from dataclasses import dataclass, field
from typing import Any

from app.models import utcnow

QUEUE_SIZE = 100  # a slow browser loses events rather than growing memory; it re-reads the session anyway


@dataclass(eq=False)
class Subscription:
    session_id: str | None
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_running_loop)

    def wants(self, event: dict[str, Any]) -> bool:
        return self.session_id is None or event.get("session_id") == self.session_id


class EventBus:
    def __init__(self) -> None:
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()
        self._seq = itertools.count(1)

    def subscribe(self, session_id: str | None = None) -> Subscription:
        """Must be called from inside a running event loop (the SSE endpoint)."""
        sub = Subscription(session_id)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        event = {"id": next(self._seq), "ts": utcnow().isoformat(), **event}
        with self._lock:
            targets = [s for s in self._subs if s.wants(event)]
        for sub in targets:
            try:
                sub.loop.call_soon_threadsafe(_offer, sub.queue, event)
            except RuntimeError:  # that subscriber's loop is closed: it is gone
                self.unsubscribe(sub)
        return event


def _offer(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(event)


bus = EventBus()


def publish_status(session: Any, previous: str | None = None) -> None:
    """A session's status changed (created, calling, in_progress, call_ended, scoring, final ...)."""
    bus.publish({
        "type": "session_status",
        "session_id": session.id,
        "parent_id": getattr(session, "parent_id", None),
        "status": session.status,
        "previous": previous,
        "review_status": session.review_status,
        "is_demo": session.is_demo,
    })


def publish_ops(session: Any) -> None:
    """New call ops data (cost, duration, latency) was stored for a session."""
    bus.publish({
        "type": "session_ops",
        "session_id": session.id,
        "parent_id": getattr(session, "parent_id", None),
        "status": session.status,
        "total_cost": session.total_cost,
        "call_duration": session.call_duration,
        "time_to_first_audio": session.time_to_first_audio,
    })


def publish_activity(parent_id: str, kind: str, text: str, audience: str = "all", ref: str | None = None) -> None:
    """Something happened in a family circle (for the live feed in the family, elder and clinic apps)."""
    bus.publish({"type": "activity", "parent_id": parent_id, "kind": kind, "text": text, "audience": audience,
                 "ref": ref})

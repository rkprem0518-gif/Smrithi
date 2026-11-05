"""Live events (SSE), call ops data, /api/ops/summary and the webhook path. Bolna is mocked with respx."""

# ruff: noqa: F811  (pytest fixtures imported from tests.test_api are redefined as parameters)

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import select

from app.db import get_engine, init_db, new_db
from app.models import Score, Session, Status
from app.services import events, orchestrator
from app.services.events import bus
from app.settings import get_settings
from tests.test_api import (  # noqa: F401
    BASE,
    PHONE,
    TOKEN,
    _execution,
    _make_app,
    _start_live_call,
    auth,
    demo_client,
    live_client,
    wait_for,
)

HOOK = "/api/bolna/webhook?token=hook-secret"


def post_call_payload(fx_name: str = "normal", **extra: Any) -> dict:
    """Bolna's post-call execution body: the fields its webhook and GET /executions/{id} carry."""
    body = _execution(fx_name)
    body.update({
        "batch_id": None,
        "updated_at": "2026-10-28T04:52:10.000Z",
        "answered_by_voice_mail": False,
        "conversation_duration": 187.4,
        "total_cost": 9.62,
        "cost_breakdown": {"llm": 1.1, "network": 0.0, "platform": 2.0, "synthesizer": 3.2, "transcriber": 3.32},
        "latency_data": {"time_to_first_audio": 1.84, "region": "in", "stream": True},
        "extracted_data": {"language_chosen": "hi"},
        "context_details": {"recipient_data": {"session_id": "ignored-for-phone"}, "recipient_phone_number": PHONE},
        "error_message": None,
    })
    body["telephony_data"].update({
        "from_number": "+918000000000", "provider": "plivo", "call_type": "outbound",
        "hangup_by": "agent", "hangup_reason": "Call ended by agent", "provider_call_id": "pc-1",
    })
    body.update(extra)
    return body


@pytest.fixture
def published(monkeypatch) -> list[dict]:
    """Every event published on the bus, in order (subscribers still get them)."""
    seen: list[dict] = []
    original = bus.publish

    def spy(event: dict) -> dict:
        out = original(event)
        seen.append(out)
        return out

    monkeypatch.setattr(bus, "publish", spy)
    return seen


def statuses_for(seen: list[dict], sid: str) -> list[str]:
    return [e["status"] for e in seen if e["type"] == "session_status" and e["session_id"] == sid]


# ---------------------------------------------------------------- the bus

async def test_bus_filters_by_session_and_cleans_up() -> None:
    before = bus.subscriber_count
    everything, only_a = bus.subscribe(None), bus.subscribe("a")
    assert bus.subscriber_count == before + 2
    bus.publish({"type": "session_status", "session_id": "a", "status": "calling"})
    bus.publish({"type": "session_status", "session_id": "b", "status": "calling"})
    await asyncio.sleep(0)
    assert [e["session_id"] for e in _drain(everything)] == ["a", "b"]
    got = _drain(only_a)
    assert [e["session_id"] for e in got] == ["a"] and got[0]["id"] and got[0]["ts"]
    bus.unsubscribe(everything)
    bus.unsubscribe(only_a)
    assert bus.subscriber_count == before


async def test_bus_accepts_publishes_from_worker_threads() -> None:
    sub = bus.subscribe("t")
    try:
        await asyncio.to_thread(bus.publish, {"type": "session_status", "session_id": "t", "status": "scored"})
        event = await asyncio.wait_for(sub.queue.get(), timeout=2)
        assert event["status"] == "scored"
    finally:
        bus.unsubscribe(sub)


def _drain(sub: events.Subscription) -> list[dict]:
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


# ---------------------------------------------------------------- the SSE endpoint (driven as raw ASGI)

class SSEClient:
    """Calls the ASGI app directly so we can read an endless stream and then hang up."""

    def __init__(self, app: Any, query: str) -> None:
        self.app, self.query = app, query
        self.chunks: list[str] = []
        self.status: int | None = None
        self._hangup = asyncio.Event()
        self._sent_request = False
        self.task: asyncio.Task | None = None

    async def _receive(self) -> dict:
        if not self._sent_request:
            self._sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._hangup.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            self.chunks.append(message.get("body", b"").decode())

    def start(self) -> SSEClient:
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": "/api/events", "raw_path": b"/api/events",
            "query_string": self.query.encode(), "root_path": "", "headers": [(b"host", b"test")],
            "client": ("127.0.0.1", 5000), "server": ("test", 80),
        }
        self.task = asyncio.create_task(self.app(scope, self._receive, self._send))
        return self

    @property
    def text(self) -> str:
        return "".join(self.chunks)

    def events(self) -> list[dict]:
        return [json.loads(line[6:]) for line in self.text.splitlines() if line.startswith("data: ")]

    async def wait_for(self, needle: str, timeout: float = 3) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while needle not in self.text:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(f"{needle!r} never arrived; got {self.text!r}")
            await asyncio.sleep(0.01)

    async def hang_up(self) -> None:
        self._hangup.set()
        assert self.task is not None
        await asyncio.wait_for(self.task, timeout=3)


@pytest.fixture
def raw_app(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, SSE_KEEPALIVE_SECONDS="0.05")
    init_db()
    yield app
    get_settings.cache_clear()
    get_engine.cache_clear()


def _new_session(status: str = Status.CREATED) -> str:
    with new_db() as db:
        session = Session(status=status)
        db.add(session)
        db.commit()
        return session.id


async def test_sse_streams_snapshot_changes_and_keepalive_then_cleans_up(raw_app) -> None:
    sid = _new_session(Status.CALLING)
    other = _new_session(Status.CALLING)
    before = bus.subscriber_count
    client = SSEClient(raw_app, f"session_id={sid}").start()
    await client.wait_for('"snapshot"')
    assert client.status == 200 and client.text.startswith("retry: 3000")
    assert bus.subscriber_count == before + 1

    with new_db() as db:  # the same helper the webhook and poller paths use
        orchestrator._touch(db, db.get(Session, other), Status.IN_PROGRESS)
        orchestrator._touch(db, db.get(Session, sid), Status.IN_PROGRESS)
    await client.wait_for('"in_progress"')
    await client.wait_for(": keep-alive")
    await client.hang_up()

    kinds = [(e["type"], e["session_id"], e["status"]) for e in client.events()]
    assert kinds == [("snapshot", sid, "calling"), ("session_status", sid, "in_progress")]
    assert client.events()[1]["previous"] == "calling"
    assert bus.subscriber_count == before  # unsubscribed on disconnect


async def test_sse_all_sessions_stream_with_token_in_query(raw_app) -> None:
    a, b = _new_session(), _new_session()
    client = SSEClient(raw_app, f"token={TOKEN}").start()
    await client.wait_for("retry")
    with new_db() as db:
        orchestrator._touch(db, db.get(Session, a), Status.CALLING)
        orchestrator._touch(db, db.get(Session, b), Status.FAILED)
    await client.wait_for('"failed"')
    await client.hang_up()
    assert [(e["session_id"], e["status"]) for e in client.events()] == [(a, "calling"), (b, "failed")]


def test_sse_needs_token_for_all_sessions_and_a_known_session_id(demo_client) -> None:
    before = bus.subscriber_count
    assert demo_client.get("/api/events").status_code == 401
    assert demo_client.get("/api/events?token=wrong").status_code == 401
    assert demo_client.get("/api/events", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert demo_client.get("/api/events?session_id=nope").status_code == 404
    assert bus.subscriber_count == before


# ---------------------------------------------------------------- events from the real flows

def test_demo_call_publishes_every_status(demo_client, published) -> None:
    sid = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone"}).json()["session_id"]
    wait_for(demo_client, sid, {"scored", "invalid"})
    assert statuses_for(published, sid) == ["created", "calling", "in_progress", "call_ended", "scoring", "scored"]
    assert all("transcript" not in e and "phone" not in json.dumps(e) for e in published)


def test_webhook_path_publishes_status_and_ops_events(live_client, published) -> None:
    sid = _start_live_call(live_client)
    route = live_client.bolna.get("/executions/ex-1")
    route.respond(200, json={"id": "ex-1", "status": "in-progress"})
    live_client.post(HOOK, json={"id": "ex-1", "status": "in-progress"})
    route.respond(200, json=post_call_payload())
    live_client.post(HOOK, json=post_call_payload())
    assert statuses_for(published, sid) == ["created", "calling", "in_progress", "scoring", "scored"]
    ops_events = [e for e in published if e["type"] == "session_ops" and e["session_id"] == sid]
    assert len(ops_events) == 1 and ops_events[0]["total_cost"] == 9.62


def test_poller_path_publishes_status_events(live_client, published) -> None:
    from app.services.bolna_client import BolnaClient
    from app.services.poller import poll_once

    sid = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=post_call_payload())
    settings = get_settings()

    async def sweep() -> int:
        async with BolnaClient.from_settings(settings) as c:
            return await poll_once(settings, c)

    asyncio.run(sweep())
    assert statuses_for(published, sid)[-2:] == ["scoring", "scored"]
    assert live_client.get(f"/api/sessions/{sid}").json()["call_ops"]["total_cost"] == 9.62


def test_poller_give_up_publishes_failed(live_client, published, monkeypatch) -> None:
    from app.services.bolna_client import BolnaClient
    from app.services.poller import poll_once

    sid = _start_live_call(live_client)
    monkeypatch.setenv("POLL_GIVE_UP_MINUTES", "0")
    get_settings.cache_clear()
    settings = get_settings()

    async def sweep() -> int:
        async with BolnaClient.from_settings(settings) as c:
            return await poll_once(settings, c)

    asyncio.run(sweep())
    assert statuses_for(published, sid)[-1] == "failed"


# ---------------------------------------------------------------- call ops data

def test_ops_fields_stored_from_post_call_payload(live_client) -> None:
    sid = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=post_call_payload())
    assert live_client.post(HOOK, json=post_call_payload()).status_code == 204

    ops = live_client.get(f"/api/sessions/{sid}").json()["call_ops"]
    assert ops["total_cost"] == 9.62
    assert ops["cost_breakdown"]["transcriber"] == 3.32
    assert ops["latency_data"]["time_to_first_audio"] == 1.84 and ops["time_to_first_audio"] == 1.84
    assert ops["call_duration"] == 187.4
    assert (ops["hangup_by"], ops["hangup_reason"]) == ("agent", "Call ended by agent")
    assert ops["has_recording"] is True and ops["recording_url"] is None  # the voice needs the reviewer token
    assert ops["simulated"] is False and ops["updated_at"]

    with_token = live_client.get(f"/api/sessions/{sid}", headers=auth()).json()["call_ops"]
    assert with_token["recording_url"] == "https://api.bolna.ai/recordings/call/ex-1"


def test_cost_arriving_after_scoring_is_still_stored_and_scored_once(live_client) -> None:
    sid = _start_live_call(live_client, "refer")
    route = live_client.bolna.get("/executions/ex-1")
    route.respond(200, json=_execution("refer"))  # Bolna has not computed the cost yet
    live_client.post(HOOK, json={"id": "ex-1"})
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "scored" and body["call_ops"]["total_cost"] is None
    assert body["call_ops"]["call_duration"] == 300.0  # telephony_data.duration ("300") as fallback

    route.respond(200, json=post_call_payload("refer"))
    live_client.post(HOOK, json={"id": "ex-1"})
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "scored" and body["call_ops"]["total_cost"] == 9.62
    review_item = next(i for i in live_client.get("/api/review", headers=auth()).json()["items"]
                       if i["session_id"] == sid)
    assert review_item["call_ops"]["recording_url"].endswith("/ex-1")
    with new_db() as db:
        assert len(db.exec(select(Score).where(Score.session_id == sid)).all()) == 1


def test_extract_call_ops_tolerates_missing_and_odd_fields() -> None:
    assert orchestrator.extract_call_ops({"status": "ringing"}) == {}
    ops = orchestrator.extract_call_ops({
        "total_cost": "4.5", "conversation_time": "61", "latency_data": "not-a-dict", "cost_breakdown": {},
        "hangup_by": "user", "time_to_first_audio": "nan", "telephony_data": None,
    })
    assert ops == {"total_cost": 4.5, "call_duration": 61.0, "hangup_by": "user"}


def test_delete_clears_recording_url_but_keeps_cost(live_client) -> None:
    sid = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=post_call_payload())
    live_client.post(HOOK, json={"id": "ex-1"})
    assert live_client.delete(f"/api/sessions/{sid}").status_code == 204
    with new_db() as db:
        s = db.get(Session, sid)
        assert s.recording_url is None and s.total_cost == 9.62


def test_old_database_gets_the_new_columns(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "test.db"
    con = sqlite3.connect(db_file)  # the session table as an older version created it
    con.execute("CREATE TABLE session (id VARCHAR PRIMARY KEY, created_at DATETIME, updated_at DATETIME, "
                "mode VARCHAR, language VARCHAR, schooling_years INTEGER, schooling_band VARCHAR, "
                "word_form VARCHAR, consent_ui BOOLEAN, consent_call BOOLEAN, phone_hash VARCHAR, "
                "phone_last4 VARCHAR, ip_hash VARCHAR, execution_id VARCHAR, status VARCHAR, "
                "review_status VARCHAR, is_demo BOOLEAN, error VARCHAR, deleted_at DATETIME)")
    con.execute("INSERT INTO session VALUES ('old-1', '2026-10-01 10:00:00', '2026-10-01 10:00:00', 'phone', 'hi', "
                "NULL, NULL, 'A', 1, 1, NULL, NULL, NULL, 'ex-old', 'failed', 'not_needed', 0, NULL, NULL)")
    con.commit()
    con.close()
    with TestClient(_make_app(tmp_path, monkeypatch)) as c:
        body = c.get("/api/sessions/old-1").json()
        assert body["status"] == "failed" and body["call_ops"]["total_cost"] is None
    columns = {row[1] for row in sqlite3.connect(db_file).execute("PRAGMA table_info(session)")}
    assert {"total_cost", "cost_breakdown", "latency_data", "time_to_first_audio", "call_duration",
            "recording_url", "hangup_reason", "hangup_by", "ops_simulated", "ops_updated_at"} <= columns
    get_settings.cache_clear()
    get_engine.cache_clear()


# ---------------------------------------------------------------- /api/ops/summary

def test_ops_summary_requires_token(demo_client) -> None:
    assert demo_client.get("/api/ops/summary").status_code == 401
    assert demo_client.get("/api/ops/summary", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_ops_summary_in_demo_mode_is_marked_simulated(demo_client) -> None:
    sid = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone"}).json()["session_id"]
    wait_for(demo_client, sid, {"scored", "invalid"})
    assert demo_client.get(f"/api/sessions/{sid}").json()["call_ops"]["simulated"] is True
    body = demo_client.get("/api/ops/summary", headers=auth()).json()
    assert body["mode"] == "demo" and body["simulated"] is True
    assert body["bolna"]["source"] == "demo" and body["bolna"]["wallet"] is None
    stats = body["sessions"]
    assert stats["count"] == 1 and stats["completed"] == 1 and stats["simulated_ops"] == 1  # samples excluded
    assert stats["avg_cost"] is not None and stats["recent"][0]["simulated"] is True


def test_ops_summary_live_reads_wallet_once_per_minute(live_client) -> None:
    me = live_client.bolna.get("/user/me").respond(
        200, json={"id": "u1", "name": "Demo", "email": "x@example.com", "wallet": "123.45",
                   "concurrency": {"max": 3, "current": 1}})
    done = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=post_call_payload())
    live_client.post(HOOK, json={"id": "ex-1"})
    with new_db() as db:  # a second call that never connected, without ops data
        db.add(Session(status=Status.NO_ANSWER, execution_id="ex-2"))
        db.commit()

    first = live_client.get("/api/ops/summary", headers=auth()).json()
    second = live_client.get("/api/ops/summary", headers=auth()).json()
    assert me.call_count == 1
    assert first["mode"] == "live" and first["simulated"] is False
    assert first["bolna"] | {"fetched_at": None} == {
        "source": "bolna", "wallet": 123.45, "concurrency": {"max": 3, "current": 1}, "fetched_at": None,
        "cached": False, "error": None}
    assert "email" not in first["bolna"]
    assert second["bolna"]["cached"] is True
    stats = first["sessions"]
    assert (stats["count"], stats["completed"], stats["not_connected"], stats["in_flight"]) == (2, 1, 1, 0)
    assert stats["avg_cost"] == 9.62 and stats["total_cost"] == 9.62
    assert stats["avg_call_duration"] == 187.4 and stats["avg_time_to_first_audio"] == 1.84
    assert done in {r["session_id"] for r in stats["recent"]}


def test_ops_summary_tolerates_bolna_errors(live_client) -> None:
    live_client.bolna.get("/user/me").respond(500, json={"message": "down"})
    r = live_client.get("/api/ops/summary", headers=auth())
    assert r.status_code == 200
    bolna = r.json()["bolna"]
    assert bolna["wallet"] is None and bolna["concurrency"] is None and bolna["source"] == "unavailable"
    assert "500" in bolna["error"]


# ---------------------------------------------------------------- webhook

def test_webhook_full_post_call_payload_scores_once_with_poller(live_client) -> None:
    from app.services.bolna_client import BolnaClient
    from app.services.poller import poll_once

    sid = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=post_call_payload())
    for _ in range(2):
        assert live_client.post(HOOK, json=post_call_payload()).status_code == 204
    settings = get_settings()

    async def sweep() -> int:
        async with BolnaClient.from_settings(settings) as c:
            return await poll_once(settings, c)

    assert asyncio.run(sweep()) == 0  # already final: the poller has nothing left to do
    with new_db() as db:
        assert len(db.exec(select(Score).where(Score.session_id == sid)).all()) == 1
        assert db.get(Session, sid).status == "scored"


def test_webhook_links_a_web_call_by_session_id_in_recipient_data(live_client) -> None:
    sid = _start_live_call(live_client)
    with new_db() as db:  # a web call whose run id was not known when it started
        s = db.get(Session, sid)
        s.execution_id = None
        db.add(s)
        db.commit()
    payload = post_call_payload(id="ex-web", context_details={"recipient_data": {"session_id": sid}})
    live_client.bolna.get("/executions/ex-web").respond(200, json=payload)
    assert live_client.post(HOOK, json=payload).status_code == 204
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "scored" and body["call_ops"]["total_cost"] == 9.62


def test_webhook_in_demo_mode_never_calls_bolna(demo_client) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.get("/executions/demo").respond(200, json={})
        r = demo_client.post(HOOK, json={"id": "demo", "status": "completed"})
    assert r.status_code == 204 and not route.called

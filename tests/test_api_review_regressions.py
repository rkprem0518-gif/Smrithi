"""Regression tests for issues found by the API/reliability peer review (30 Oct 2026)."""

from __future__ import annotations

import asyncio
import io
import json
import logging

import httpx
import pytest
import respx
from sqlmodel import select

from app.db import new_db
from app.models import CallArtifact, Review, Score, Session
from app.services import orchestrator
from app.services.bolna_client import BolnaClient, BolnaNetworkError, BolnaServerError
from app.settings import LiveConfigError, Settings, get_settings
from tests.test_api import PHONE, _execution, _start_live_call, auth, demo_client, live_client  # noqa: F401

BASE = "https://api.bolna.ai"


# B1: webhook and poller (or duplicate webhooks) must score a call exactly once
def test_duplicate_completion_scores_once(live_client) -> None:  # noqa: F811
    sid = _start_live_call(live_client)
    live_client.bolna.get("/executions/ex-1").respond(200, json=_execution("normal"))
    for _ in range(3):
        assert live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1"}).status_code == 204
    with new_db() as db:
        assert len(db.exec(select(Score).where(Score.session_id == sid)).all()) == 1
        assert len(db.exec(select(CallArtifact).where(CallArtifact.session_id == sid)).all()) == 1
        assert db.get(Session, sid).status == "scored"


def test_concurrent_apply_execution_claims_once(live_client) -> None:  # noqa: F811
    sid = _start_live_call(live_client)
    settings = get_settings()

    async def both() -> None:
        with new_db() as a, new_db() as b:
            sa, sb = a.get(Session, sid), b.get(Session, sid)
            await asyncio.gather(
                orchestrator.apply_execution(a, sa, _execution("normal"), settings),
                orchestrator.apply_execution(b, sb, _execution("normal"), settings),
            )

    asyncio.run(both())
    with new_db() as db:
        assert len(db.exec(select(Score).where(Score.session_id == sid)).all()) == 1


def test_status_never_moves_backwards(live_client) -> None:  # noqa: F811
    sid = _start_live_call(live_client)
    route = live_client.bolna.get("/executions/ex-1")
    for status in ("in-progress", "ringing"):
        route.respond(200, json={"id": "ex-1", "status": status})
        live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1"})
    assert live_client.get(f"/api/sessions/{sid}").json()["status"] == "in_progress"


# B2: a delete that lands before scoring wins; nothing is written back
def test_deleted_session_is_never_scored(live_client) -> None:  # noqa: F811
    sid = _start_live_call(live_client)
    assert live_client.delete(f"/api/sessions/{sid}").status_code == 204
    with new_db() as db:
        session = db.get(Session, sid)
        asyncio.run(orchestrator.apply_execution(db, session, _execution("normal"), get_settings()))
        assert not db.exec(select(Score).where(Score.session_id == sid)).all()
        assert not db.exec(select(CallArtifact).where(CallArtifact.session_id == sid)).all()


def test_delete_also_removes_reviews(demo_client) -> None:  # noqa: F811
    sid = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone", "demo_fixture": "refer"}).json()["session_id"]
    for _ in range(200):
        if demo_client.get(f"/api/sessions/{sid}").json()["status"] == "scored":
            break
        asyncio.run(asyncio.sleep(0.02))
    demo_client.post(f"/api/review/{sid}", headers=auth(), json={"reviewer": "Dr X", "decision": "agree"})
    assert demo_client.delete(f"/api/sessions/{sid}").status_code == 204
    with new_db() as db:
        assert not db.exec(select(Review).where(Review.session_id == sid)).all()


# B3: spoofed X-Forwarded-For and per-number cap
def test_spoofed_forwarded_for_does_not_bypass_limit(live_client) -> None:  # noqa: F811
    live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-1"})
    codes = []
    for i in range(5):
        headers = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}  # client-forged prefix, proxy-added last
        r = live_client.post("/api/sessions", headers=headers,
                             json={"consent": True, "mode": "phone", "phone": f"+9198765400{i:02d}"})
        codes.append(r.status_code)
    assert codes == [201, 201, 201, 429, 429]


def test_same_number_capped_per_day(live_client) -> None:  # noqa: F811
    live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-1"})
    codes = [live_client.post("/api/sessions", headers={"X-Forwarded-For": f"198.51.100.{i}"},
                              json={"consent": True, "mode": "phone", "phone": PHONE}).status_code for i in range(3)]
    assert codes == [201, 201, 429]


# B4: live mode refuses the example secrets
def test_live_mode_refuses_default_secrets() -> None:
    s = Settings(_env_file=None, demo_mode=False, bolna_api_key="k", bolna_agent_id="a")
    with pytest.raises(LiveConfigError, match="SECRET_SALT"):
        s.require_live()


# B5: a crash while scoring does not leave the session stuck in "scoring"
def test_scoring_crash_marks_failed(live_client, monkeypatch) -> None:  # noqa: F811
    sid = _start_live_call(live_client)

    def boom(*a, **k):
        raise RuntimeError("bad transcript")

    monkeypatch.setattr(orchestrator, "score_session", boom)
    with new_db() as db, pytest.raises(RuntimeError):
        asyncio.run(orchestrator.apply_execution(db, db.get(Session, sid), _execution("normal"), get_settings()))
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "failed" and body["review_status"] == "pending"


# B6: never dial twice
@respx.mock
async def test_call_not_retried_after_read_timeout() -> None:
    route = respx.post(f"{BASE}/call").mock(side_effect=httpx.ReadTimeout("slow"))
    async with BolnaClient(api_key="k", base_url=BASE, backoff=0) as c:
        with pytest.raises(BolnaNetworkError):
            await c.make_call("ag-1", PHONE)
    assert route.call_count == 1


@respx.mock
async def test_call_not_retried_after_5xx_but_connect_errors_are() -> None:
    route = respx.post(f"{BASE}/call").respond(502)
    async with BolnaClient(api_key="k", base_url=BASE, backoff=0) as c:
        with pytest.raises(BolnaServerError):
            await c.make_call("ag-1", PHONE)
    assert route.call_count == 1
    route = respx.post(f"{BASE}/call").mock(side_effect=[httpx.ConnectError("down"), httpx.Response(200, json={"execution_id": "e"})])
    async with BolnaClient(api_key="k", base_url=BASE, backoff=0) as c:
        assert await c.make_call("ag-1", PHONE) == "e"


# B7: shared samples cannot be deleted
def test_samples_cannot_be_deleted(demo_client) -> None:  # noqa: F811
    assert demo_client.delete("/api/sessions/demo-normal").status_code == 403
    assert demo_client.get("/api/sessions/demo-normal").status_code == 200


# B8: the webhook token never reaches the access log
def test_access_log_hides_webhook_token(live_client) -> None:  # noqa: F811
    from app.main import _RedactTokenFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(_RedactTokenFilter())
    logger = logging.getLogger("uvicorn.access")
    logger.addHandler(handler)
    try:
        logger.warning('%s - "%s %s HTTP/%s" %d', "1.2.3.4", "POST", "/api/bolna/webhook?token=hook-secret", "1.1", 204)
    finally:
        logger.removeHandler(handler)
    assert "hook-secret" not in stream.getvalue() and "token=***" in stream.getvalue()


# B9: phone hash is keyed by the secret salt
def test_phone_hash_depends_on_secret() -> None:
    assert orchestrator.hash_value(PHONE, "a") != orchestrator.hash_value(PHONE, "b")


# A1: no webhook_url key is sent when there is no public URL
def test_payload_omits_null_webhook() -> None:
    from app.config_loader import agent_prompt, agent_template
    from app.services.agent_builder import build_agent_payload

    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt())
    assert "webhook_url" not in payload["agent_config"]
    assert "null" not in json.dumps(payload["agent_config"]["tasks"])

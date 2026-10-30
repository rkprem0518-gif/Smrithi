"""API smoke + end-to-end tests. Bolna is mocked with respx; nothing leaves the machine."""

from __future__ import annotations

import io
import logging
import time

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import select

from app.config_loader import load_fixture
from app.db import get_engine, new_db
from app.models import CallArtifact, Score, Session
from app.services.segmenter import turns_from_json, turns_to_bolna_transcript
from app.settings import LiveConfigError, get_settings

BASE = "https://api.bolna.ai"
TOKEN = "review-secret"
PHONE = "+919876543210"


def _make_app(tmp_path, monkeypatch, **env):
    defaults = {
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "DEMO_MODE": "1",
        "ADMIN_REVIEW_TOKEN": TOKEN,
        "BOLNA_WEBHOOK_TOKEN": "hook-secret",
        "BOLNA_API_KEY": "",
        "BOLNA_AGENT_ID": "",
        "BOLNA_FROM_NUMBER": "",
        "PUBLIC_BASE_URL": "http://localhost:8000",
        "ASR_PROVIDER": "none",
        "APP_ENV": "development",
        "MAX_CALLS_PER_IP_PER_DAY": "3",
        "DEMO_CALL_STEP_SECONDS": "0.01",
        "BOLNA_RETRY_BACKOFF_SECONDS": "0",
        "POLL_INTERVAL_SECONDS": "3600",
        "HELPLINE_TEXT": "",
    }
    for k, v in {**defaults, **env}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(tmp_path)  # no developer .env leaks in
    get_settings.cache_clear()
    get_engine.cache_clear()
    from app.main import create_app

    return create_app()


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    with TestClient(_make_app(tmp_path, monkeypatch)) as c:
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, DEMO_MODE="0", BOLNA_API_KEY="k", BOLNA_AGENT_ID="ag-1")
    with respx.mock(base_url=BASE, assert_all_called=False) as mock, TestClient(app) as c:
        c.bolna = mock  # type: ignore[attr-defined]
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


def auth() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


def wait_for(client: TestClient, sid: str, statuses: set[str], timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/sessions/{sid}").json()
        if body["status"] in statuses:
            return body
        time.sleep(0.02)
    raise AssertionError(f"session {sid} stuck in {body['status']}")


# ---------------------------------------------------------------- demo mode

def test_health(demo_client) -> None:
    body = demo_client.get("/api/health").json()
    assert body == {**body, "ok": True, "demo_mode": True, "bolna_configured": False}


@pytest.mark.parametrize(
    ("sid", "outcome", "status", "review"),
    [("demo-normal", "NORMAL", "scored", "not_needed"), ("demo-uncertain", "UNCERTAIN", "scored", "pending"),
     ("demo-refer", "REFER", "scored", "pending"), ("demo-invalid-hearing", "INVALID", "invalid", "pending")],
)
def test_demo_reports_seeded_on_startup(demo_client, sid, outcome, status, review) -> None:
    body = demo_client.get(f"/api/sessions/{sid}").json()
    assert (body["outcome"], body["status"], body["review_status"]) == (outcome, status, review)
    report = body["report"]
    assert report["not_a_diagnosis"] is True
    assert report["rule_fired"]
    assert set(report["domains"]) == {"word_learning", "delayed_recall", "animal_naming", "orientation"}
    assert report["next_step_text"]["en"] and report["next_step_text"]["hi"]


def test_static_pages_served(demo_client) -> None:
    assert demo_client.get("/").status_code == 200


def test_consent_required(demo_client) -> None:
    r = demo_client.post("/api/sessions", json={"consent": False, "language": "hi", "mode": "phone", "phone": PHONE})
    assert r.status_code == 400


def test_demo_session_runs_the_state_machine(demo_client) -> None:
    r = demo_client.post("/api/sessions", json={"consent": True, "language": "hi", "mode": "phone",
                                                "demo_fixture": "refer"})
    assert r.status_code == 201 and r.json()["demo"] is True
    body = wait_for(demo_client, r.json()["session_id"], {"scored", "invalid"})
    assert body["outcome"] == "REFER"
    # The simulated call must be scored against the fixture's own word form (C), not the rotation.
    assert body["report"]["word_form"] == "C"
    assert body["report"]["domains"]["delayed_recall"]["score"] == 2
    assert body["report"]["domains"]["word_learning"]["total"] == 9


def test_delete_wipes_data(demo_client) -> None:
    r = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone", "phone": PHONE})
    sid = r.json()["session_id"]
    wait_for(demo_client, sid, {"scored", "invalid"})
    assert demo_client.delete(f"/api/sessions/{sid}").status_code == 204
    assert demo_client.get(f"/api/sessions/{sid}").status_code == 404
    with new_db() as db:
        s = db.get(Session, sid)
        assert s.deleted_at and s.phone_hash is None and s.phone_last4 is None
        assert not db.exec(select(CallArtifact).where(CallArtifact.session_id == sid)).all()
        assert not db.exec(select(Score).where(Score.session_id == sid)).all()


def test_phone_never_stored_in_clear(demo_client) -> None:
    sid = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone", "phone": PHONE}).json()["session_id"]
    with new_db() as db:
        s = db.get(Session, sid)
        assert s.phone_last4 == "3210" and PHONE not in (s.phone_hash or "")
        assert PHONE not in s.model_dump_json()


def test_bad_phone_rejected(demo_client) -> None:
    r = demo_client.post("/api/sessions", json={"consent": True, "mode": "phone", "phone": "98765"})
    assert r.status_code == 422


def test_review_requires_token(demo_client) -> None:
    assert demo_client.get("/api/review").status_code == 401
    assert demo_client.get("/api/review", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_review_queue_and_decision(demo_client) -> None:
    items = demo_client.get("/api/review", headers=auth()).json()["items"]
    ids = {i["session_id"] for i in items}
    assert ids == {"demo-uncertain", "demo-refer", "demo-invalid-hearing"}
    assert all(i["transcript"] for i in items)
    r = demo_client.post("/api/review/demo-refer", headers=auth(),
                         json={"reviewer": "Dr Rao", "decision": "agree", "note": "consistent"})
    assert r.status_code == 201
    pending = {i["session_id"] for i in demo_client.get("/api/review", headers=auth()).json()["items"]}
    assert "demo-refer" not in pending
    everything = demo_client.get("/api/review?status=all", headers=auth()).json()["items"]
    refer = next(i for i in everything if i["session_id"] == "demo-refer")
    assert refer["reviews"][0]["decision"] == "agree"


def test_review_rejects_unknown_decision(demo_client) -> None:
    r = demo_client.post("/api/review/demo-refer", headers=auth(), json={"reviewer": "x", "decision": "diagnose"})
    assert r.status_code == 422


def test_demo_score_endpoint_accepts_turns_and_bolna_string(demo_client) -> None:
    fx = load_fixture("uncertain")
    body = {"transcript": fx["transcript"], "word_form": "B", "call_time": fx["call_started_at"]}
    assert demo_client.post("/api/demo/score", json=body).json()["report"]["outcome"] == "UNCERTAIN"
    body["transcript"] = turns_to_bolna_transcript(turns_from_json(fx["transcript"]))
    assert demo_client.post("/api/demo/score", json=body).json()["result"]["outcome"] == "UNCERTAIN"


def test_production_refuses_default_review_token(tmp_path, monkeypatch) -> None:
    app = _make_app(tmp_path, monkeypatch, APP_ENV="production", ADMIN_REVIEW_TOKEN="change-me")
    with TestClient(app) as c:
        assert c.get("/api/review", headers={"Authorization": "Bearer change-me"}).status_code == 503
    get_settings.cache_clear()
    get_engine.cache_clear()


# ---------------------------------------------------------------- live mode (Bolna mocked)

def test_live_mode_fails_fast_without_keys(tmp_path, monkeypatch) -> None:
    app = _make_app(tmp_path, monkeypatch, DEMO_MODE="0")
    with pytest.raises(LiveConfigError, match="BOLNA_API_KEY"), TestClient(app):
        pass
    get_settings.cache_clear()
    get_engine.cache_clear()


def _execution(fx_name: str, status: str = "completed", **extra) -> dict:
    fx = load_fixture(fx_name)
    return {
        "id": "ex-1", "agent_id": "ag-1", "status": status,
        "transcript": turns_to_bolna_transcript(turns_from_json(fx["transcript"])),
        "created_at": fx["call_started_at"],
        "telephony_data": {"recording_url": "https://api.bolna.ai/recordings/call/ex-1",
                           "to_number": PHONE, "duration": "300"},
        **extra,
    }


def _start_live_call(client, form_fixture: str = "normal") -> str:
    client.bolna.post("/call").respond(200, json={"message": "done", "status": "queued", "execution_id": "ex-1"})
    r = client.post("/api/sessions", json={"consent": True, "language": "hi", "mode": "phone", "phone": PHONE})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    # Fixtures are tied to a word form; align the session with the fixture we will return.
    with new_db() as db:
        s = db.get(Session, sid)
        s.word_form = load_fixture(form_fixture)["word_form"]
        db.add(s)
        db.commit()
    return sid


@pytest.mark.parametrize("fx_name", ["normal", "uncertain", "refer", "invalid_hearing"])
def test_live_phone_call_end_to_end_via_webhook(live_client, fx_name) -> None:
    sid = _start_live_call(live_client, fx_name)
    sent = live_client.bolna.routes  # the /call route
    call_req = next(r for r in sent if r.called).calls.last.request
    assert b'"recipient_phone_number":"+919876543210"' in call_req.content.replace(b" ", b"")
    assert live_client.get(f"/api/sessions/{sid}").json()["status"] == "calling"

    live_client.bolna.get("/executions/ex-1").respond(200, json=_execution(fx_name))
    # Webhook body is ignored except for the id: we always re-fetch.
    r = live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1", "status": "completed"})
    assert r.status_code == 204
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["outcome"] == load_fixture(fx_name)["expected"]["outcome"]
    with new_db() as db:
        artifact = db.exec(select(CallArtifact).where(CallArtifact.session_id == sid)).one()
        assert artifact.recording_url.endswith("/ex-1")
        assert PHONE not in str(artifact.execution_json_redacted)


def test_webhook_rejects_bad_token(live_client) -> None:
    assert live_client.post("/api/bolna/webhook?token=nope", json={"id": "ex-1"}).status_code == 401
    assert live_client.post("/api/bolna/webhook", json={"id": "ex-1"}).status_code == 401


def test_webhook_unknown_execution_is_ignored(live_client) -> None:
    assert live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "nope"}).status_code == 204


def test_in_flight_statuses_then_no_answer(live_client) -> None:
    sid = _start_live_call(live_client)
    route = live_client.bolna.get("/executions/ex-1")
    for bolna_status, ours in [("ringing", "calling"), ("in-progress", "in_progress"), ("no-answer", "no_answer")]:
        route.respond(200, json={"id": "ex-1", "status": bolna_status})
        live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1"})
        assert live_client.get(f"/api/sessions/{sid}").json()["status"] == ours


def test_poller_picks_up_completed_call(live_client) -> None:
    import asyncio

    from app.services.bolna_client import BolnaClient
    from app.services.poller import poll_once

    sid = _start_live_call(live_client, "uncertain")
    live_client.bolna.get("/executions/ex-1").respond(200, json=_execution("uncertain"))
    settings = get_settings()

    async def sweep() -> int:
        async with BolnaClient.from_settings(settings) as c:
            return await poll_once(settings, c)

    assert asyncio.run(sweep()) == 1
    assert live_client.get(f"/api/sessions/{sid}").json()["outcome"] == "UNCERTAIN"


def test_bolna_failure_on_call_marks_session_failed(live_client) -> None:
    live_client.bolna.post("/call").respond(500, json={"message": "down"})
    r = live_client.post("/api/sessions", json={"consent": True, "mode": "phone", "phone": PHONE})
    assert r.status_code == 502
    with new_db() as db:
        assert db.exec(select(Session)).one().status == "failed"


def test_live_requires_valid_phone(live_client) -> None:
    r = live_client.post("/api/sessions", json={"consent": True, "mode": "phone"})
    assert r.status_code == 422


def test_rate_limit_per_ip(live_client) -> None:
    live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-1"})
    codes = [live_client.post("/api/sessions", json={"consent": True, "mode": "phone", "phone": PHONE}).status_code
             for _ in range(4)]
    assert codes == [201, 201, 201, 429]


def test_declined_call(live_client) -> None:
    sid = _start_live_call(live_client)
    execution = {"id": "ex-1", "status": "completed", "transcript": (
        "assistant: क्या हम लगभग पाँच मिनट बात कर सकते हैं? क्या यह ठीक है?\n"
        "user: नहीं, अभी नहीं।\n"
        "assistant: कोई बात नहीं, आज जाँच नहीं करेंगे। आपका समय देने के लिए धन्यवाद। नमस्ते।")}
    live_client.bolna.get("/executions/ex-1").respond(200, json=execution)
    live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1"})
    body = live_client.get(f"/api/sessions/{sid}").json()
    assert body["status"] == "declined" and body["outcome"] is None


def test_logs_never_contain_phone_or_transcript(live_client) -> None:
    stream = io.StringIO()
    handler = logging.getLogger("smriti").handlers[0]
    old = handler.setStream(stream)
    try:
        sid = _start_live_call(live_client)
        live_client.bolna.get("/executions/ex-1").respond(200, json=_execution("normal"))
        live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-1"})
    finally:
        handler.setStream(old)
    out = stream.getvalue()
    assert sid in out
    assert PHONE not in out and "9876543210" not in out
    assert "घर" not in out and "बुधवार" not in out

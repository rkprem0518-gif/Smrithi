"""The family product: flag rules, seeded history, the family API, check-in and family calls, care desk."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import respx
from fastapi.testclient import TestClient

from app.config_loader import agent_prompt, agent_template
from app.db import get_engine
from app.family.flags import analyze, message_for_family
from app.scoring.types import Turn
from app.services.agent_builder import build_agent_payload
from app.settings import Settings, get_settings
from tests.test_api import BASE, PHONE, _make_app, auth, wait_for


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    with TestClient(_make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1")) as c:
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, SEED_FAMILY_DEMO="1", DEMO_MODE="0", BOLNA_API_KEY="k",
                    BOLNA_AGENT_ID="ag-1", BOLNA_AGENT_ID_CHECKIN="ag-checkin")
    with respx.mock(base_url=BASE, assert_all_called=False) as mock, TestClient(app) as c:
        c.bolna = mock  # type: ignore[attr-defined]
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()

NOW = datetime(2026, 11, 5, 12, 0)


def said(*lines: str) -> list[Turn]:
    return [Turn("agent", "How have you been?")] + [Turn("user", line) for line in lines]


def levels(result) -> dict[str, str]:
    return {f.category: f.level for f in result.flags}


# ---------------------------------------------------------------- flag rules

def test_single_pain_mention_is_noted_and_twice_is_yellow() -> None:
    assert levels(analyze(said("ಮಂಡಿ ನೋವು ಇದೆ."), now=NOW)) == {"pain": "green"}
    history = [("pain", NOW - timedelta(days=10))]
    assert levels(analyze(said("घुटने में दर्द है"), history, now=NOW)) == {"pain": "yellow"}
    old = [("pain", NOW - timedelta(days=45))]  # outside the 30-day window
    assert levels(analyze(said("My knee hurts."), old, now=NOW)) == {"pain": "green"}


@pytest.mark.parametrize(("text", "category"), [
    ("I had chest pain last night", "chest"), ("सीने में दर्द हो रहा है", "chest"), ("ಎದೆ ನೋವು", "chest"),
    ("I fell down in the bathroom", "fall"), ("मैं गिर गया था", "fall"), ("ನಾನು ಬಿದ್ದೆ", "fall"),
    ("I can't breathe properly", "breath"), ("I don't want to live any more", "self_harm"),
])
def test_red_flags_in_three_languages(text: str, category: str) -> None:
    result = analyze(said(text), now=NOW)
    assert levels(result)[category] == "red"
    assert "pain" not in levels(result) or category != "chest"  # chest pain is not also counted as plain pain


def test_negation_and_getting_better() -> None:
    assert analyze(said("No pain at all, I didn't fall."), now=NOW).flags == []
    better = analyze(said("My knee pain is better now."), now=NOW)
    assert better.flags == [] and better.cleared == ["pain"]


def test_lonely_and_missed_medicines_are_yellow_at_once() -> None:
    assert levels(analyze(said("I feel so lonely these days"), now=NOW)) == {"loneliness": "yellow"}
    assert levels(analyze(said("दवाई नहीं ली आज"), now=NOW)) == {"medicines": "yellow"}


def test_safety_concern_never_reaches_the_family() -> None:
    result = analyze(said("He takes my money and hits me"), now=NOW)
    flag = next(f for f in result.flags if f.category == "safety")
    assert flag.level == "red" and flag.family_visible is False
    assert not any("money" in n for n in result.notes)


def test_message_for_family_and_mood() -> None:
    turns = said("I am very happy, Pinky called.") + [
        Turn("agent", "Is there anything you'd like me to tell Ravi?"), Turn("user", "Tell him to bring sweets."),
    ]
    result = analyze(turns, now=NOW)
    assert result.mood == "cheerful" and result.message_for_family == "Tell him to bring sweets."
    nothing = [Turn("agent", "ರವಿ ಅವರಿಗೆ ಏನಾದರೂ ಹೇಳಬೇಕಾ?"), Turn("user", "ಏನಿಲ್ಲ")]
    assert message_for_family(nothing) is None
    assert analyze(said("I feel low and sad"), now=NOW).mood == "low"


# ---------------------------------------------------------------- agents

@pytest.mark.parametrize("kind", ["checkin", "family"])
def test_checkin_and_family_agents_are_multilingual(kind: str) -> None:
    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(kind), kind=kind)
    tools = payload["agent_config"]["tasks"][0]["tools_config"]
    assert set(tools["multilingual_config"]["languages"]) == {"hi", "kn", "en"}
    tc = payload["agent_config"]["tasks"][0]["task_config"]
    assert tc["hangup_after_LLMCall"] is True and "goodbye" in tc["call_cancellation_prompt"]
    assert payload["agent_config"]["agent_welcome_message"].rstrip().endswith("?")


def test_checkin_prompt_keeps_the_promises() -> None:
    prompt = agent_prompt("checkin")
    assert "never ask you for money, bank details or an OTP" in prompt
    assert "112" in prompt and "14567" in prompt
    assert "Is there anything you'd like me to tell {{family_name}}?" in prompt  # flags.yaml close_question


# ---------------------------------------------------------------- API (demo mode)

def test_family_api_needs_the_access_key(demo_client) -> None:
    assert demo_client.get("/api/family/home").status_code == 401
    assert demo_client.get("/api/care/queue").status_code == 401
    assert demo_client.get("/api/family/home", headers=auth()).status_code == 200


def test_seeded_appa_has_weeks_flags_and_a_memory_check_to_review(demo_client) -> None:
    home = demo_client.get("/api/family/home", headers=auth()).json()
    assert home["parent"]["call_name"] == "Appa"
    timeline = demo_client.get("/api/family/timeline", headers=auth()).json()["items"]
    assert sum(1 for c in timeline if c["kind"] == "checkin") == 8
    queue = demo_client.get("/api/care/queue", headers=auth()).json()["items"]
    assert queue[0]["type"] == "memory" and queue[0]["outcome"] == "REFER"
    assert {i["category"] for i in queue if i["type"] == "flag"} == {"pain", "sleep"}
    report = demo_client.get("/api/family/report", headers=auth()).json()
    assert report["calls_completed"] == 7 and len(report["weeks"]) == 8
    assert demo_client.get("/api/family/doctor-summary", headers=auth()).json()["memory"]["outcome"] == "REFER"


def _wait_checkin(client, checkin_id: str, status: str = "done") -> dict:
    import time

    for _ in range(300):
        body = client.get(f"/api/family/checkins/{checkin_id}", headers=auth()).json()
        if body["status"] == status:
            return body
        time.sleep(0.02)
    raise AssertionError(f"check-in stuck in {body['status']}")


def test_demo_checkin_call_writes_flags_notes_and_message(demo_client) -> None:
    r = demo_client.post("/api/family/call", json={"name": "Raghunath ji"}, headers=auth())
    assert r.status_code == 201, r.text
    assert r.json()["remembered"].startswith("Knee hurt")
    c = _wait_checkin(demo_client, r.json()["checkin_id"])
    cats = {f["category"]: f["level"] for f in c["flags"]}
    assert cats["pain"] == "yellow"  # knee pain again, after earlier mentions this month
    assert cats["sleep"] == "yellow"
    assert c["message_for_family"].startswith("Tell Ravi")
    assert c["call_ops"]["simulated"] is True


def test_care_desk_approval_calls_family_and_books_visit(demo_client) -> None:
    queue = demo_client.get("/api/care/queue", headers=auth()).json()["items"]
    memory = next(i for i in queue if i["type"] == "memory")
    r = demo_client.post(f"/api/care/memory/{memory['id']}/approve", json={}, headers=auth())
    assert r.status_code == 200, r.text
    _wait_checkin(demo_client, r.json()["family_call"]["checkin_id"])
    visits = demo_client.get("/api/family/visits", headers=auth()).json()["items"]
    assert len(visits) == 1 and "Memory clinic" in visits[0]["title"]
    assert visits[0]["google_calendar_url"].startswith("https://calendar.google.com/calendar/render?action=TEMPLATE")
    queue = demo_client.get("/api/care/queue", headers=auth()).json()["items"]
    assert not any(i["type"] == "memory" for i in queue)


def test_calendar_ics_and_contact_card(demo_client) -> None:
    ics = demo_client.get("/api/family/calendar.ics?token=review-secret")
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text and "Weekly chat with Appa" in ics.text
    vcf = demo_client.get("/api/family/smriti.vcf", headers=auth())
    assert "never asks for money" in vcf.text


def test_okay_only_sharing_hides_words_from_the_family(demo_client) -> None:
    demo_client.patch("/api/family/settings", json={"share_level": "okay_only"}, headers=auth())
    timeline = demo_client.get("/api/family/timeline", headers=auth()).json()["items"]
    assert all(c["quotes"] == [] for c in timeline)
    assert all(f["level"] == "red" for c in timeline for f in c["flags"])
    assert demo_client.get("/api/family/doctor-summary", headers=auth()).status_code == 403


# ---------------------------------------------------------------- live mode (Bolna mocked)

def test_live_checkin_sends_notes_and_topics_and_reads_the_transcript(live_client) -> None:
    route = live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-ci-1", "status": "queued"})
    r = live_client.post("/api/family/call", json={"phone": PHONE, "name": "Raghunath ji"}, headers=auth())
    assert r.status_code == 201, r.text
    sent = json.loads(route.calls.last.request.content)
    assert sent["agent_id"] == "ag-checkin"
    assert sent["user_data"]["parent_name"] == "Raghunath ji" and "temple" in sent["user_data"]["notes"]
    assert sent["user_data"]["agent_language"] == "kn"
    transcript = (
        "assistant: Is this a good time?\nuser: Yes. I fell in the bathroom yesterday.\n"
        "assistant: Is there anything you'd like me to tell Ravi?\nuser: No, nothing."
    )
    live_client.bolna.get("/executions/ex-ci-1").respond(200, json={
        "id": "ex-ci-1", "status": "completed", "transcript": transcript, "total_cost": 12.0,
        "telephony_data": {"duration": "95"},
    })
    hook = live_client.post("/api/bolna/webhook?token=hook-secret", json={"id": "ex-ci-1", "status": "completed"})
    assert hook.status_code == 204
    wait_for(live_client, r.json()["session_id"], {"scored"})
    c = _wait_checkin(live_client, r.json()["checkin_id"])
    assert {f["category"]: f["level"] for f in c["flags"]} == {"fall": "red"}
    assert c["message_for_family"] is None
    queue = live_client.get("/api/care/queue", headers=auth()).json()["items"]
    assert queue[0]["level"] == "red" and queue[0]["category"] == "fall"

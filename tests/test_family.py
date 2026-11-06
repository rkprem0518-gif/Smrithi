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
    langs = set(tools["multilingual_config"]["languages"])
    if kind == "checkin":  # every language Sarvam STT + TTS support on Bolna
        assert langs == {"en", "hi", "kn", "ta", "te", "ml", "mr", "bn", "gu", "pa", "od"}
        assert tools["multilingual_config"]["language_switch_trigger"] == "requested_or_auto_detected"
    else:
        assert langs == {"hi", "kn", "en"}
    tc = payload["agent_config"]["tasks"][0]["task_config"]
    assert tc["hangup_after_LLMCall"] is True and "goodbye" in tc["call_cancellation_prompt"]
    assert payload["agent_config"]["agent_welcome_message"].rstrip().endswith("?")


def test_interruption_and_language_lock_settings() -> None:
    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), multilingual=True)
    task = payload["agent_config"]["tasks"][0]
    assert task["task_config"]["number_of_words_for_interruption"] == 2  # stops sooner when the person talks
    assert task["tools_config"]["transcriber"]["endpointing"] == 500
    # The memory check only switches language when the person asks: word lists and scoring depend on it.
    assert task["tools_config"]["multilingual_config"]["language_switch_trigger"] == "caller_requested"


def test_checkin_prompt_keeps_the_promises() -> None:
    prompt = agent_prompt("checkin")
    assert "never ask you for money, bank details or an OTP" in prompt
    assert "112" in prompt and "14567" in prompt
    assert "Is there anything you'd like me to tell {{family_name}}?" in prompt  # flags.yaml close_question
    assert "Listen first" in prompt and "One or two short sentences" in prompt
    assert "How are you feeling today?" in prompt and "{{share_sentence}}" in prompt


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
    assert "sleeping" in r.json()["remembered"]
    c = _wait_checkin(demo_client, r.json()["checkin_id"])
    cats = {f["category"]: f["level"] for f in c["flags"]}
    assert cats == {"sleep": "yellow"}  # poor sleep again, after earlier mentions this month
    assert c["message_for_family"].startswith("Tell him")
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


def login(client, user_id: str) -> None:
    client.cookies.clear()
    assert client.post("/api/auth/demo-login", json={"user_id": user_id}).status_code == 200


def test_okay_only_sharing_hides_words_from_the_family(demo_client) -> None:
    login(demo_client, "u-appa")
    assert demo_client.patch("/api/family/settings", json={"share_level": "okay_only"}).status_code == 200
    login(demo_client, "u-ravi")
    timeline = demo_client.get("/api/family/timeline").json()["items"]
    assert all(c["quotes"] == [] for c in timeline)
    assert all(f["level"] == "red" for c in timeline for f in c["flags"])
    assert demo_client.get("/api/family/doctor-summary").status_code == 403
    login(demo_client, "u-meera")  # the care team still sees what it needs to
    assert demo_client.get("/api/family/doctor-summary").status_code == 200


# ---------------------------------------------------------------- logins, circle, roles

def test_demo_login_logout_and_who_sees_what(demo_client) -> None:
    assert demo_client.get("/api/auth/me").json()["user"] is None
    login(demo_client, "u-ravi")
    me = demo_client.get("/api/auth/me").json()
    assert me["user"]["name"] == "Ravi Rao" and me["parents"][0]["call_name"] == "Appa"
    assert demo_client.get("/api/care/queue").status_code == 403  # family is not the care team
    assert demo_client.patch("/api/family/settings", json={"share_level": "all"}).status_code == 403  # only Appa
    assert demo_client.patch("/api/family/settings", json={"language": "ta"}).status_code == 403
    login(demo_client, "u-priya")  # pending: Appa hasn't said yes yet
    assert demo_client.get("/api/family/home").status_code == 404
    demo_client.post("/api/auth/logout")
    assert demo_client.get("/api/family/home").status_code == 401


def test_elder_approves_a_new_member_and_controls_language_and_calls(demo_client) -> None:
    login(demo_client, "u-appa")
    circle = demo_client.get("/api/people/me").json()["circles"][0]
    pending = next(m for m in circle["members"] if m["status"] == "pending")
    assert pending["name"] == "Priya Rao"
    r = demo_client.post(f"/api/people/members/{pending['member_id']}/decide", json={"accept": True})
    assert r.status_code == 200
    assert demo_client.patch("/api/family/settings", json={"language": "ta", "calls_paused": True}).status_code == 200
    login(demo_client, "u-priya")
    home = demo_client.get("/api/family/home").json()
    assert home["parent"]["language"] == "ta" and home["parent"]["calls_paused"] is True
    assert demo_client.post("/api/family/call", json={}).status_code == 409  # paused: only Appa can call now
    history = demo_client.get("/api/family/history").json()["items"]
    assert any("Priya Rao is now in the circle" in h["text"] for h in history)


def test_contacts_by_smriti_id_become_mutual(demo_client) -> None:
    login(demo_client, "u-meera")
    c = demo_client.post("/api/people/contacts", json={"query": "SM-RAVI42"}).json()
    assert c["name"] == "Ravi Rao" and c["mutual"] is True  # Ravi had already added Dr. Meera
    assert demo_client.post("/api/people/contacts", json={"query": "SM-NOBODY1"}).status_code == 404


def test_schedule_with_family_questions_runs_a_checkin(demo_client) -> None:
    login(demo_client, "u-ravi")
    s = demo_client.post("/api/family/schedules", json={
        "label": "Morning", "time": "08:30", "days": [0, 2, 4], "questions": ["Did you take your thyroid tablet?"],
    }).json()
    assert s["days"] == [0, 2, 4] and s["next_run_at"]
    r = demo_client.post(f"/api/family/schedules/{s['id']}/run", json={})
    assert r.status_code == 201, r.text
    assert any("thyroid" in t for t in r.json()["topics"])
    _wait_checkin(demo_client, r.json()["checkin_id"])


def test_checkin_user_data_retires_notes_and_sends_exact_share_sentence(demo_client) -> None:
    from app.db import new_db
    from app.family import service

    with new_db() as db:
        parent = service.get_parent(db, "appa")
        data, _, _ = service.checkin_user_data(db, parent, questions=["Did you eat?"])
        assert "sleeping" in data["notes"] and "Did you eat?" in data["family_questions"]
        assert data["share_sentence"].startswith("I'll let Ravi know how you are, including")
        again, _, _ = service.checkin_user_data(db, parent)
        assert "nothing to follow up" in again["notes"]  # never asks about the same thing twice


# ---------------------------------------------------------------- live mode (Bolna mocked)

def test_calls_are_simulated_until_real_calls_are_switched_on(live_client) -> None:
    route = live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-sim", "status": "queued"})
    live_client.bolna.get("/user/me").respond(200, json={"wallet": 377})
    login(live_client, "u-ravi")
    mode = live_client.get("/api/auth/call-mode").json()
    assert mode == {"live": False, "available": True, "wallet": 377}
    r = live_client.post("/api/family/call", json={"phone": PHONE})
    assert r.status_code == 201, r.text
    c = _wait_checkin(live_client, r.json()["checkin_id"])
    assert c["call_ops"]["simulated"] is True and not route.called  # no Bolna call, no credits
    assert live_client.put("/api/auth/call-mode", json={"live": True}).json()["live"] is True
    login(live_client, "u-meera")  # the switch is shared by all three apps
    assert live_client.get("/api/auth/call-mode").json()["live"] is True
    login(live_client, "u-ravi")
    assert live_client.post("/api/family/call", json={"phone": PHONE}).status_code == 201
    assert route.called  # now a real Bolna call


def test_offline_server_cannot_switch_to_real_calls(demo_client) -> None:
    login(demo_client, "u-ravi")
    assert demo_client.get("/api/auth/call-mode").json()["available"] is False
    assert demo_client.put("/api/auth/call-mode", json={"live": True}).status_code == 409


def test_live_checkin_sends_notes_and_topics_and_reads_the_transcript(live_client) -> None:
    live_client.put("/api/auth/call-mode", json={"live": True}, headers=auth())
    route = live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-ci-1", "status": "queued"})
    r = live_client.post("/api/family/call", json={"phone": PHONE, "name": "Raghunath ji"}, headers=auth())
    assert r.status_code == 201, r.text
    sent = json.loads(route.calls.last.request.content)
    assert sent["agent_id"] == "ag-checkin"
    assert sent["user_data"]["parent_name"] == "Raghunath ji" and "sleeping" in sent["user_data"]["notes"]
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


# ---------------------------------------------------------------- add a parent, call language, reset

def test_family_adds_a_parent_with_a_preferred_language(demo_client) -> None:
    login(demo_client, "u-appa")
    assert demo_client.post("/api/people/parents", json={"full_name": "X Y"}).status_code == 403  # family only
    login(demo_client, "u-ravi")
    r = demo_client.post("/api/people/parents", json={
        "full_name": "Kamala Sharma", "call_name": "Amma", "age": 68, "city": "Pune", "language": "hi",
        "relation": "son", "share_level": "health",
    })
    assert r.status_code == 201, r.text
    amma = r.json()
    assert amma["language"] == "hi" and amma["call_name"] == "Amma"
    me = demo_client.get("/api/auth/me").json()
    assert {p["call_name"] for p in me["parents"]} == {"Appa", "Amma"}
    assert demo_client.get(f"/api/family/home?parent_id={amma['id']}").json()["recent"] == []  # a fresh timeline
    elders = demo_client.get("/api/auth/me?app=elder").json()["demo_users"]
    assert any(u["name"] == "Kamala Sharma" for u in elders)  # she can open her own elder page


def test_call_language_preferred_chosen_or_ask_first(live_client) -> None:
    route = live_client.bolna.post("/call").respond(200, json={"execution_id": "ex-lang", "status": "queued"})
    live_client.bolna.get("/user/me").respond(200, json={"wallet": 300})
    login(live_client, "u-ravi")
    live_client.put("/api/auth/call-mode", json={"live": True})
    amma = live_client.post("/api/people/parents", json={"full_name": "Kamala Sharma", "call_name": "Amma",
                                                        "language": "hi"}).json()

    def sent(**body):
        assert live_client.post("/api/family/call", json={"phone": PHONE, "parent_id": amma["id"], **body}).status_code == 201
        return json.loads(route.calls.last.request.content)["user_data"]

    assert sent()["agent_language"] == "hi"  # her preferred language
    assert sent(language="en")["agent_language"] == "en"  # chosen for this call only
    ask = sent(language="ask")
    assert ask["agent_language"] == "en" and ask["language_note"].startswith("Start by asking")
    assert live_client.get(f"/api/family/home?parent_id={amma['id']}").json()["parent"]["language"] == "hi"  # unchanged


def test_reset_removes_added_parents_and_keeps_the_sample_family(demo_client) -> None:
    login(demo_client, "u-ravi")
    demo_client.post("/api/people/parents", json={"full_name": "Kamala Sharma", "call_name": "Amma"})
    assert demo_client.post("/api/people/reset-demo").json()["removed"] == 1
    me = demo_client.get("/api/auth/me").json()
    assert [p["call_name"] for p in me["parents"]] == ["Appa"]
    assert not any(u["name"] == "Kamala Sharma" for u in demo_client.get("/api/auth/me?app=elder").json()["demo_users"])

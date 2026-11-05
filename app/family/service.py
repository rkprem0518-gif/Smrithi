"""Family product logic: start calls, finish calls (flags, notes), care desk, timeline, calendar, reports."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.config_loader import scoring_config
from app.db import new_db
from app.family.flags import analyze
from app.family.models import Appointment, CheckIn, Flag, Note, Parent, ShareLevel
from app.logs import log
from app.models import CallArtifact, Review, ReviewStatus, Score, Session, Status, utcnow
from app.scoring import tasks
from app.scoring.types import Turn
from app.services import events
from app.services.bolna_client import BolnaClient, BolnaError
from app.services.orchestrator import (
    E164,
    SessionError,
    _touch,
    apply_execution,
    claim_for_scoring,
    hash_value,
    store_call_ops,
)
from app.settings import Settings

IST = timezone(timedelta(hours=5, minutes=30), "IST")  # India has no DST
PLAYBOOK = Path(__file__).resolve().parent.parent.parent / "config" / "playbook.yaml"
KINDS = ("checkin", "family")
MISSED = (Status.NO_ANSWER, Status.BUSY, Status.FAILED)
VISIT_QUESTION = ("add a visit to your calendar", "कैलेंडर में", "ಕ್ಯಾಲೆಂಡರ್")
DEMO_CLINIC = "Memory clinic, Jayanagar, Bengaluru (demo)"
DEMO_GP = "Family doctor, Mysuru (demo)"


class FamilyError(SessionError):
    pass


def aware(dt: datetime) -> datetime:
    """SQLite gives naive datetimes back; they were stored in UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------- parent, notes, topics


def get_parent(db: DBSession, parent_id: str | None = None) -> Parent:
    parent = db.get(Parent, parent_id) if parent_id else db.exec(select(Parent).order_by(Parent.created_at)).first()
    if not parent:
        raise FamilyError("No parent is set up yet. Run scripts/seed_family.py.", 404)
    return parent


@lru_cache
def playbook() -> dict[str, Any]:
    with open(PLAYBOOK, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pick_topics(parent: Parent, now: datetime | None = None, grandchild: str = "Pinky") -> list[str]:
    """Two topic cards: an upcoming festival first, then the parent's interests, then defaults."""
    now = (now or utcnow()).astimezone(IST)
    pb = playbook()
    picked: list[str] = []
    for fest in pb["festivals"]:
        days = (datetime.fromisoformat(fest["date"]).date() - now.date()).days
        if 0 <= days <= int(fest["lead_days"]):
            picked.append(fest["opener"])
            break
    wanted = [c for c in parent.interests if c in pb["cards"]] + pb["default_cards"]
    for name in wanted:
        if len(picked) >= 2:
            break
        opener = pb["cards"][name]["opener"].replace("{grandchild}", grandchild)
        if opener not in picked:
            picked.append(opener)
    return picked


def recent_notes(db: DBSession, parent: Parent, limit: int = 3) -> list[Note]:
    q = select(Note).where(Note.parent_id == parent.id, Note.used == False).order_by(Note.created_at.desc())  # noqa: E712
    return list(db.exec(q.limit(limit)).all())


def next_call_at(parent: Parent, now: datetime | None = None) -> datetime:
    now = (now or utcnow()).astimezone(IST)
    hh, mm = (int(x) for x in parent.call_time.split(":"))
    days = (parent.call_weekday - now.weekday()) % 7
    at = (now + timedelta(days=days)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=7)
    return at


def last_memory_check(db: DBSession, parent: Parent) -> CheckIn | None:
    q = select(CheckIn).where(CheckIn.parent_id == parent.id, CheckIn.kind == "memory").order_by(CheckIn.at.desc())
    return db.exec(q).first()


def memory_check_due(db: DBSession, parent: Parent) -> datetime:
    last = last_memory_check(db, parent)
    base = aware(last.at) if last else utcnow()
    return base + timedelta(days=parent.memory_check_every_days)


# ---------------------------------------------------------------- user_data for the agents


SHARE_SENTENCE = {
    ShareLevel.OKAY_ONLY: "I'll just let {f} know you're doing well.",
    ShareLevel.HEALTH: "I'll let {f} know how you are, including anything you told me about your health.",
    ShareLevel.ALL: "I'll let {f} know how you are and what we talked about.",
}


def checkin_user_data(
    db: DBSession, parent: Parent, name: str | None = None, questions: list[str] | None = None
) -> tuple[dict[str, Any], list[str], str]:
    """What the check-in agent gets for this call. Notes from last time are used once, then retired, so Smriti
    never keeps asking about the same thing."""
    notes = [n for n in recent_notes(db, parent, limit=2) if aware(n.created_at) >= utcnow() - timedelta(days=21)]
    topics = pick_topics(parent)
    for n in notes:
        n.used = True
        db.add(n)
    db.commit()
    questions = [q.strip() for q in (questions or []) if q.strip()]
    data = {
        "parent_name": name or parent.honorific or parent.call_name,
        "family_name": parent.family_name,
        "relation": parent.relation,
        "notes": "\n".join(f"   - {n.text}" for n in notes) or "   - (nothing to follow up)",
        "topics": "\n".join(f"   - {t}" for t in topics),
        "family_questions": "\n".join(f"   - {q}" for q in questions) or "   - (none today)",
        "share_sentence": SHARE_SENTENCE.get(parent.share_level, SHARE_SENTENCE[ShareLevel.HEALTH]).format(
            f=parent.family_name
        ),
        "language": parent.language,
        "agent_language": parent.language,
        "call_type": "checkin",
    }
    remembered = notes[0].text if notes else ""
    if questions:
        topics = [f"{parent.family_name} asked: {q}" for q in questions] + topics
    return data, topics, remembered


def family_reason(db: DBSession, case_type: str, case_id: str, parent: Parent) -> tuple[str, str, str]:
    """(reason lines Smriti says, visit place, short title) for the call to the family."""
    who = parent.call_name
    if case_type == "memory":
        return (
            f"A few days ago, {who} did a short memory check with me on the phone. Some answers suggest it "
            f"would be good to see a doctor for a proper check. This is not a diagnosis: hearing, sleep, mood, "
            f"medicines and vitamin levels can all affect memory, and many causes are treatable.",
            DEMO_CLINIC,
            "Memory clinic visit",
        )
    flag = db.get(Flag, case_id)
    if not flag:
        raise FamilyError("Flag not found", 404)
    words = flag.quote_en or flag.quote
    if flag.level == "red":
        return (
            f'{who} told me: "{words}". I asked {who} to call 112 at the time. Our care team thinks someone '
            f"should check on {who} today.",
            DEMO_GP,
            "Check on " + who,
        )
    return (
        f'In our weekly chats, {who} has mentioned this more than once this month. In {who}\'s words: "{words}". '
        f"It may be worth a visit to the family doctor.",
        DEMO_GP,
        "Doctor visit",
    )


def suggested_visit(now: datetime | None = None) -> datetime:
    """Next Saturday, 10:30 am IST (at least 3 days away)."""
    now = (now or utcnow()).astimezone(IST)
    days = (5 - now.weekday()) % 7
    if days < 3:
        days += 7
    return (now + timedelta(days=days)).replace(hour=10, minute=30, second=0, microsecond=0)


def _fmt_visit(at: datetime, place: str) -> str:
    local = at.astimezone(IST)
    ampm = "am" if local.hour < 12 else "pm"
    return f"{local:%A} {local.day} {local:%B} at {local.hour % 12 or 12}:{local:%M} {ampm}, {place}"


# ---------------------------------------------------------------- starting calls


async def start_call(
    db: DBSession,
    *,
    kind: str,
    parent: Parent,
    phone: str | None,
    settings: Settings,
    user_data: dict[str, Any],
    topics: list[str] | None = None,
    remembered: str = "",
    summary: str = "",
    language: str | None = None,
    actor: Any = None,
    allow_paused: bool = False,
) -> tuple[Session, CheckIn]:
    from app.family import people

    if kind not in KINDS:
        raise FamilyError(f"Unknown call kind {kind!r}", 400)
    if kind == "checkin" and parent.calls_paused and not allow_paused:
        raise FamilyError(f"{parent.call_name} has paused calls. Only {parent.call_name} can turn them back on.", 409)
    if phone and not E164.match(phone):
        raise FamilyError("Enter the phone number in international format, e.g. +919876543210.", 422)
    if not settings.demo_mode and not phone:
        raise FamilyError("A phone number is needed for a live call.", 422)
    language = language or parent.language
    session = Session(
        mode="phone",
        language=language,
        consent_ui=True,
        kind=kind,
        parent_id=parent.id,
        phone_hash=hash_value(phone, settings.secret_salt) if phone else None,
        phone_last4=phone[-4:] if phone else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    checkin = CheckIn(
        parent_id=parent.id,
        session_id=session.id,
        kind=kind,
        status="calling",
        language=language,
        topics=topics or [],
        remembered=remembered,
        summary=summary,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    events.publish_status(session)
    log("family_call_created", session_id=session.id, kind=kind, demo=settings.demo_mode)
    who = parent.family_name if kind == "family" else parent.call_name
    what = "update for the family" if kind == "family" else "check-in"
    people.log(db, parent.id, f"Smriti is calling {who} ({what}).", kind="call", actor=actor, ref=checkin.id)

    if settings.demo_mode:
        _touch(db, session, Status.CALLING)
        asyncio.get_running_loop().create_task(simulate_call(session.id, kind, settings))
        return session, checkin

    settings.require_live()
    agent_id = settings.bolna_agent_id_checkin if kind == "checkin" else settings.bolna_agent_id_family
    if not agent_id:
        _touch(db, session, Status.FAILED, error=f"No Bolna agent is set up for {kind} calls.")
        raise FamilyError(f"The {kind} agent is not set up yet (BOLNA_AGENT_ID_{kind.upper()} in .env).", 503)
    user_data = {**user_data, "session_id": session.id}
    async with BolnaClient.from_settings(settings) as client:
        try:
            execution_id = await client.make_call(agent_id, phone or "", user_data, settings.bolna_from_number or None)
        except BolnaError as exc:
            _touch(db, session, Status.FAILED, error=f"Could not start the call ({exc.status_code or 'network'}).")
            log("family_call_start_failed", session_id=session.id, status_code=exc.status_code)
            detail = str(exc) if exc.status_code in (400, 403, 422) else "Please try again."
            raise FamilyError(f"The call could not be started. {detail}", 502) from exc
    _touch(db, session, Status.CALLING, execution_id=execution_id)
    log("family_call_started", session_id=session.id, execution_id=execution_id, kind=kind)
    return session, checkin


# ---------------------------------------------------------------- finishing calls


def finish_call(
    db: DBSession,
    session: Session,
    turns: list[Turn],
    *,
    recording_url: str | None = None,
    execution_redacted: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Session:
    """Called from apply_execution when a check-in or family call has completed. Runs exactly once."""
    if not claim_for_scoring(db, session):
        return session
    try:
        db.add(
            CallArtifact(
                session_id=session.id,
                recording_url=recording_url,
                execution_json_redacted=execution_redacted,
                transcript_json=[{"role": t.role, "text": t.text, "t": t.t} for t in turns],
            )
        )
        checkin = db.exec(select(CheckIn).where(CheckIn.session_id == session.id)).first()
        if checkin is None:
            raise FamilyError("No timeline entry for this call", 500)
        parent = db.get(Parent, checkin.parent_id)
        if session.kind == "family":
            _finish_family(db, checkin, parent, turns)
        else:
            _finish_checkin(db, checkin, parent, turns, now=now)
        db.add(checkin)
        db.commit()
        _touch(db, session, Status.SCORED)
        log("family_call_finished", session_id=session.id, kind=session.kind, status=checkin.status)
        _log_finished(db, checkin, parent)
    except Exception as exc:
        db.rollback()
        db.refresh(session)
        _touch(db, session, Status.FAILED, error="Could not read the call; please review it by hand.")
        log("family_call_finish_failed", session_id=session.id, error=type(exc).__name__)
        raise
    return session


def _log_finished(db: DBSession, checkin: CheckIn, parent: Parent) -> None:
    from app.family import people

    if checkin.kind == "family":
        people.log(db, parent.id, checkin.summary or "Call to the family finished.", kind="call", ref=checkin.id)
        return
    if checkin.status == "missed":
        people.log(db, parent.id, f"No answer from {parent.call_name}.", kind="call", ref=checkin.id)
        return
    people.log(db, parent.id, f"Chat with {parent.call_name} finished. {checkin.summary}", kind="call", ref=checkin.id)
    for f in db.exec(select(Flag).where(Flag.checkin_id == checkin.id)).all():
        if f.level == "red":
            safety = f.review_note.startswith("safety")
            people.log(
                db,
                parent.id,
                f"Red flag for the care team: {_flag_title(f)}.",
                kind="flag",
                ref=f.id,
                audience="clinic" if safety else "all",
            )


def flag_history(db: DBSession, parent_id: str, before: datetime | None = None) -> list[tuple[str, datetime]]:
    q = select(Flag).where(Flag.parent_id == parent_id)
    rows = db.exec(q).all()
    return [(f.category, aware(f.created_at)) for f in rows if before is None or aware(f.created_at) < before]


def _finish_checkin(db: DBSession, checkin: CheckIn, parent: Parent, turns: list[Turn], now: datetime | None) -> None:
    now = now or utcnow()
    user_turns = [t for t in turns if t.role == "user" and t.text.strip()]
    if not user_turns:
        checkin.status = "missed"
        checkin.summary = "Smriti called, but nobody spoke."
        return
    result = analyze(turns, flag_history(db, parent.id, before=now), now=now)
    checkin.status = "done"
    checkin.mood = result.mood
    checkin.message_for_family = result.message_for_family
    for f in result.flags:
        db.add(
            Flag(
                parent_id=parent.id,
                checkin_id=checkin.id,
                created_at=now,
                category=f.category,
                level=f.level,
                quote=f.quote,
                rule=f.rule,
                status="noted" if f.level == "green" else "open",
                review_note="" if f.family_visible else "safety: care desk only",
            )
        )
    for text in result.notes:
        db.add(Note(parent_id=parent.id, created_at=now, text=text))
    for note in recent_notes(db, parent):
        if checkin.remembered and note.text == checkin.remembered:
            note.used = True
            db.add(note)
    quotes = [{"text": f.quote, "en": None} for f in result.flags if f.family_visible][:3]
    if not quotes:
        longest = max(user_turns, key=lambda t: len(t.text))
        quotes = [{"text": longest.text[:180], "en": None}]
    checkin.quotes = quotes
    checkin.summary = summarize(checkin, result.flags, result.cleared)


def summarize(checkin: CheckIn, flags: list[Any], cleared: list[str]) -> str:
    from app.family.flags import flag_config

    labels = flag_config()["categories"]
    parts = []
    mood_word = {"cheerful": "Sounded cheerful", "okay": "A calm chat", "low": "Sounded low"}.get(
        checkin.mood or "", ""
    )
    if mood_word:
        parts.append(mood_word)
    visible = [f for f in flags if getattr(f, "family_visible", True)]
    if visible:
        parts.append("mentioned " + ", ".join(labels[f.category]["label"].lower() for f in visible))
    if cleared:
        parts.append(", ".join(labels[c]["label"].lower() for c in cleared) + " is better")
    return ". ".join(p[0].upper() + p[1:] for p in parts) + ("." if parts else "")


def _finish_family(db: DBSession, checkin: CheckIn, parent: Parent, turns: list[Turn]) -> None:
    said_yes = None
    for i, turn in enumerate(turns):
        if turn.role == "agent" and any(q in turn.text.lower() for q in VISIT_QUESTION):
            reply = next((t for t in turns[i + 1 :] if t.role == "user"), None)
            if reply:
                said_yes = tasks.parse_yes_no(reply.text, scoring_config())
    spoke = any(t.role == "user" and t.text.strip() for t in turns)
    checkin.status = "done" if spoke else "missed"
    if said_yes:
        at = suggested_visit()
        place = DEMO_CLINIC if "memory" in (checkin.summary or "").lower() else DEMO_GP
        title = "Memory clinic visit" if place == DEMO_CLINIC else "Doctor visit"
        db.add(
            Appointment(
                parent_id=parent.id,
                title=f"{title} · {parent.call_name}",
                starts_at=at,
                place=place,
                status="requested",
                source=f"{parent.family_name} said yes on Smriti's call",
            )
        )
        checkin.summary = (checkin.summary or "") + f" {parent.family_name} asked for a visit; it is on the calendar."
    elif spoke:
        checkin.summary = (checkin.summary or "") + f" {parent.family_name} was told."
    else:
        checkin.summary = (checkin.summary or "") + f" Could not reach {parent.family_name}."


# ---------------------------------------------------------------- demo mode

DEMO_TRANSCRIPTS: dict[str, list[tuple[str, str]]] = {
    "checkin": [
        (
            "agent",
            "Hello! This is Smriti, your family's AI companion, calling to check in on you. Is this a good time?",
        ),
        ("user", "Yes, go ahead."),
        (
            "agent",
            "Lovely. As always, I will never ask you for money, bank details or an OTP. How are you feeling today?",
        ),
        ("user", "I'm okay, a bit tired. I couldn't sleep well, I keep waking up at 3."),
        ("agent", "I'm sorry to hear that. Since when has that been happening?"),
        ("user", "About a week now."),
        ("agent", "Thank you, I'll note that. Ravi asked me to check: did you take your BP tablet today?"),
        ("user", "Yes, I took it after breakfast."),
        ("agent", "Good. How has your appetite been?"),
        ("user", "Fine, I had dosa today."),
        ("agent", "Lovely. Is there anything you'd like me to tell Ravi?"),
        ("user", "Tell him to bring sweets from the Mysuru shop for Deepavali."),
        (
            "agent",
            "I'll let Ravi know how you are, including what you told me about your health. "
            "Talk to you soon. Take care!",
        ),
    ],
    "family": [
        ("agent", "Hello, this is Smriti, calling with an update about your family. Is this a good time?"),
        ("user", "Yes, tell me."),
        (
            "agent",
            "A few days ago, Appa did a short memory check with me. Some answers suggest it would be good to "
            "see a doctor. This is not a diagnosis. Would you like me to add a visit to your calendar for "
            "Saturday at 10:30 am?",
        ),
        ("user", "Yes, please do that."),
        ("agent", "Done. You will see it in the Smriti app. Take care."),
    ],
}


async def simulate_call(session_id: str, kind: str, settings: Settings) -> None:
    step = settings.demo_call_step_seconds
    for status in ("ringing", "in-progress", "call-disconnected"):
        await asyncio.sleep(step)
        with new_db() as db:
            session = db.get(Session, session_id)
            if not session or session.deleted_at:
                return
            await apply_execution(db, session, {"status": status}, settings)
    await asyncio.sleep(step)
    with new_db() as db:
        session = db.get(Session, session_id)
        if not session or session.deleted_at:
            return
        turns = [Turn(r, t) for r, t in DEMO_TRANSCRIPTS[kind]]
        store_call_ops(
            db,
            session,
            {
                "total_cost": 4.1,
                "call_duration": 96.0,
                "time_to_first_audio": 1.1,
                "latency_data": {"time_to_first_audio": 1.1},
                "cost_breakdown": {"simulated": True},
                "hangup_reason": "simulated",
                "hangup_by": "agent",
            },
            simulated=True,
        )
        finish_call(db, session, turns)


# ---------------------------------------------------------------- care desk


def care_queue(db: DBSession, parent: Parent) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    flags = db.exec(select(Flag).where(Flag.parent_id == parent.id, Flag.status == "open")).all()
    for f in flags:
        checkin = db.get(CheckIn, f.checkin_id)
        items.append(
            {
                "type": "flag",
                "id": f.id,
                "level": f.level,
                "category": f.category,
                "title": _flag_title(f),
                "quote": f.quote,
                "quote_en": f.quote_en,
                "rule": f.rule,
                "at": aware(f.created_at).isoformat(),
                "checkin_id": f.checkin_id,
                "session_id": checkin.session_id if checkin else None,
                "safety_only": f.review_note.startswith("safety"),
            }
        )
    memory = db.exec(select(CheckIn).where(CheckIn.parent_id == parent.id, CheckIn.kind == "memory")).all()
    for c in memory:
        session = db.get(Session, c.session_id) if c.session_id else None
        if not session or session.review_status != ReviewStatus.PENDING:
            continue
        score = db.exec(select(Score).where(Score.session_id == session.id)).first()
        items.append(
            {
                "type": "memory",
                "id": c.id,
                "level": "memory",
                "category": "memory_check",
                "title": f"Memory check: {score.outcome if score else 'needs review'}",
                "quote": None,
                "quote_en": None,
                "rule": score.rule_fired if score else "",
                "at": aware(c.at).isoformat(),
                "checkin_id": c.id,
                "session_id": session.id,
                "outcome": score.outcome if score else None,
            }
        )
    rank = {"red": 0, "memory": 1, "yellow": 2, "green": 3}
    items.sort(key=lambda i: (rank.get(i["level"], 9), i["at"]))
    return items


def _flag_title(f: Flag) -> str:
    from app.family.flags import flag_config

    label = flag_config()["categories"].get(f.category, {}).get("label", f.category)
    return label


async def approve_case(
    db: DBSession,
    parent: Parent,
    case_type: str,
    case_id: str,
    family_phone: str | None,
    settings: Settings,
    reviewer: str = "care desk",
    note: str = "",
    actor: Any = None,
) -> dict[str, Any]:
    from app.family import people

    reviewer = getattr(actor, "name", None) or reviewer
    reason, place, title = family_reason(db, case_type, case_id, parent)
    if case_type == "flag":
        flag = db.get(Flag, case_id)
        flag.status, flag.reviewed_at, flag.review_note = "approved", utcnow(), note or flag.review_note
        if flag.review_note.startswith("safety"):
            db.add(flag)
            db.commit()
            people.log(
                db,
                parent.id,
                f"{reviewer} reviewed a safety concern. Handled by the care team only.",
                kind="review",
                actor=actor,
                audience="clinic",
            )
            return {"approved": True, "family_call": None, "note": "Safety concerns are not shared with the family."}
        db.add(flag)
    else:
        checkin = db.get(CheckIn, case_id)
        session = db.get(Session, checkin.session_id) if checkin and checkin.session_id else None
        if not session:
            raise FamilyError("Memory check not found", 404)
        db.add(Review(session_id=session.id, reviewer=reviewer, decision="agree", note=note))
        session.review_status = ReviewStatus.REVIEWED
        db.add(session)
        checkin.summary = (checkin.summary or "").split(" Waiting")[0] + " Reviewed by the care team."
        db.add(checkin)
    db.commit()
    people.log(
        db,
        parent.id,
        f"{reviewer} reviewed the {title.lower()} and approved a call to {parent.family_name}.",
        kind="review",
        actor=actor,
    )
    visit_at = suggested_visit()
    user_data = {
        "family_name": parent.family_name,
        "parent_name": parent.call_name,
        "relation": parent.relation,
        "reason": reason,
        "suggested_visit": _fmt_visit(visit_at, place),
        "language": "en",
        "agent_language": "en",
        "call_type": "family",
    }
    summary = f"Smriti called {parent.family_name} about: {title.lower()}."
    if case_type == "memory":
        summary = f"Smriti called {parent.family_name} about the memory check."
    session, checkin = await start_call(
        db,
        kind="family",
        parent=parent,
        phone=family_phone,
        settings=settings,
        user_data=user_data,
        summary=summary,
        language="en",
        actor=actor,
    )
    return {"approved": True, "family_call": {"session_id": session.id, "checkin_id": checkin.id}}


def dismiss_case(db: DBSession, case_type: str, case_id: str, note: str = "", actor: Any = None) -> None:
    from app.family import people

    if case_type == "flag":
        flag = db.get(Flag, case_id)
        if not flag:
            raise FamilyError("Flag not found", 404)
        flag.status, flag.reviewed_at, flag.review_note = "dismissed", utcnow(), note
        db.add(flag)
    else:
        checkin = db.get(CheckIn, case_id)
        session = db.get(Session, checkin.session_id) if checkin and checkin.session_id else None
        if not session:
            raise FamilyError("Memory check not found", 404)
        db.add(
            Review(session_id=session.id, reviewer=getattr(actor, "name", "care desk"), decision="retest", note=note)
        )
        session.review_status = ReviewStatus.REVIEWED
        db.add(session)
    db.commit()
    parent_id = flag.parent_id if case_type == "flag" else checkin.parent_id
    who = getattr(actor, "name", "The care team")
    people.log(
        db,
        parent_id,
        f"{who} reviewed and closed a {case_type} with no call needed.",
        kind="review",
        actor=actor,
        audience="clinic",
    )


# ---------------------------------------------------------------- what the family sees


def _visible_flags(flags: list[Flag], parent: Parent) -> list[Flag]:
    out = [f for f in flags if not f.review_note.startswith("safety")]
    if parent.share_level == ShareLevel.OKAY_ONLY:
        return [f for f in out if f.level == "red"]
    return out


def checkin_out(db: DBSession, c: CheckIn, parent: Parent, for_family: bool = True) -> dict[str, Any]:
    session = db.get(Session, c.session_id) if c.session_id else None
    status = c.status
    if session and status == "calling":
        if session.status in Status.FINAL and session.status not in MISSED:
            status = "invalid" if session.status in (Status.INVALID, Status.STOPPED, Status.DECLINED) else "done"
        elif session.status in MISSED:
            status = "missed"
        elif session.status in (Status.IN_PROGRESS,):
            status = "talking"
        elif session.status in (Status.CALL_ENDED, Status.SCORING):
            status = "writing"
    flags = list(db.exec(select(Flag).where(Flag.checkin_id == c.id)).all())
    flags = _visible_flags(flags, parent) if for_family else flags
    okay_only = for_family and parent.share_level == ShareLevel.OKAY_ONLY
    score = db.exec(select(Score).where(Score.session_id == c.session_id)).first() if c.kind == "memory" else None
    return {
        "id": c.id,
        "kind": c.kind,
        "at": aware(c.at).isoformat(),
        "status": status,
        "language": c.language,
        "duration_s": (session.call_duration if session and session.call_duration else c.duration_s),
        "mood": c.mood,
        "summary": c.summary if not okay_only else _okay_summary(c, parent),
        "topics": c.topics,
        "remembered": "" if okay_only else c.remembered,
        "quotes": [] if okay_only else c.quotes,
        "message_for_family": c.message_for_family,
        "outcome": score.outcome if score else c.outcome,
        "session_id": c.session_id,
        "review_status": session.review_status if session else None,
        "flags": [flag_out(f) for f in flags],
        "call_ops": _ops(session) if session else None,
    }


def _okay_summary(c: CheckIn, parent: Parent) -> str:
    if c.status == "missed":
        return "Smriti could not reach " + parent.call_name + "."
    return f"{parent.call_name} chatted with Smriti."


def _ops(session: Session) -> dict[str, Any]:
    return {
        "total_cost": session.total_cost,
        "call_duration": session.call_duration,
        "time_to_first_audio": session.time_to_first_audio,
        "simulated": session.ops_simulated,
        "status": session.status,
    }


def flag_out(f: Flag) -> dict[str, Any]:
    from app.family.flags import flag_config

    label = flag_config()["categories"].get(f.category, {}).get("label", f.category)
    return {
        "id": f.id,
        "category": f.category,
        "label": label,
        "level": f.level,
        "quote": f.quote,
        "quote_en": f.quote_en,
        "rule": f.rule,
        "status": f.status,
        "at": aware(f.created_at).isoformat(),
    }


def parent_out(db: DBSession, parent: Parent) -> dict[str, Any]:
    last = last_memory_check(db, parent)
    return {
        "id": parent.id,
        "full_name": parent.full_name,
        "call_name": parent.call_name,
        "honorific": parent.honorific,
        "city": parent.city,
        "language": parent.language,
        "family_name": parent.family_name,
        "relation": parent.relation,
        "share_level": parent.share_level,
        "consent_at": aware(parent.consent_at).isoformat() if parent.consent_at else None,
        "next_call_at": next_call_at(parent).isoformat(),
        "call_weekday": parent.call_weekday,
        "call_time": parent.call_time,
        "interests": parent.interests,
        "memory_check_due": memory_check_due(db, parent).isoformat(),
        "age": parent.age,
        "calls_paused": parent.calls_paused,
        "user_id": parent.user_id,
        "last_memory_check": aware(last.at).isoformat() if last else None,
    }


def timeline(db: DBSession, parent: Parent, limit: int = 40) -> list[dict[str, Any]]:
    rows = db.exec(select(CheckIn).where(CheckIn.parent_id == parent.id).order_by(CheckIn.at.desc()).limit(limit)).all()
    return [checkin_out(db, c, parent) for c in rows]


def this_week(db: DBSession, parent: Parent) -> dict[str, Any]:
    since = utcnow() - timedelta(days=7)
    flags = [f for f in db.exec(select(Flag).where(Flag.parent_id == parent.id)).all() if aware(f.created_at) >= since]
    flags = [f for f in _visible_flags(flags, parent) if f.level in ("yellow", "red")]
    messages = db.exec(
        select(CheckIn)
        .where(CheckIn.parent_id == parent.id, CheckIn.message_for_family.is_not(None))  # type: ignore[union-attr]
        .order_by(CheckIn.at.desc())
        .limit(3)
    ).all()
    return {
        "flags": [flag_out(f) for f in flags],
        "messages": [
            {"text": c.message_for_family, "at": aware(c.at).isoformat(), "checkin_id": c.id} for c in messages
        ],
    }


def appointments(db: DBSession, parent: Parent) -> list[Appointment]:
    return list(
        db.exec(select(Appointment).where(Appointment.parent_id == parent.id).order_by(Appointment.starts_at)).all()
    )


def calendar(db: DBSession, parent: Parent, weeks_back: int = 9, weeks_ahead: int = 6) -> list[dict[str, Any]]:
    """Everything with a date: past calls, the next weekly calls, the memory check due date, visits."""
    out: list[dict[str, Any]] = []
    for c in db.exec(select(CheckIn).where(CheckIn.parent_id == parent.id)).all():
        if aware(c.at) < utcnow() - timedelta(weeks=weeks_back):
            continue
        item = checkin_out(db, c, parent)
        out.append(
            {
                "type": c.kind,
                "at": item["at"],
                "title": _cal_title(c, parent),
                "status": item["status"],
                "level": _worst(item["flags"]),
                "checkin_id": c.id,
            }
        )
    nxt = next_call_at(parent)
    for i in range(weeks_ahead):
        at = nxt + timedelta(weeks=i)
        out.append(
            {
                "type": "planned",
                "at": at.isoformat(),
                "title": f"Weekly chat with {parent.call_name}",
                "status": "planned",
                "minutes": 10,
            }
        )
    due = memory_check_due(db, parent)
    out.append(
        {"type": "memory_due", "at": due.isoformat(), "title": "Memory check due", "status": "planned", "minutes": 15}
    )
    for a in appointments(db, parent):
        out.append(
            {
                "type": "visit",
                "at": aware(a.starts_at).isoformat(),
                "title": a.title,
                "status": a.status,
                "place": a.place,
                "minutes": a.minutes,
                "id": a.id,
            }
        )
    out.sort(key=lambda e: e["at"])
    return out


def _cal_title(c: CheckIn, parent: Parent) -> str:
    return {
        "checkin": f"Chat with {parent.call_name}",
        "memory": "Memory check",
        "family": f"Smriti called {parent.family_name}",
    }.get(c.kind, c.kind)


def _worst(flags: list[dict[str, Any]]) -> str:
    levels = {f["level"] for f in flags}
    return "red" if "red" in levels else "yellow" if "yellow" in levels else "green"


def report(db: DBSession, parent: Parent, weeks: int = 8) -> dict[str, Any]:
    now = utcnow()
    checkins = [c for c in db.exec(select(CheckIn).where(CheckIn.parent_id == parent.id)).all()]
    flags = _visible_flags(list(db.exec(select(Flag).where(Flag.parent_id == parent.id)).all()), parent)
    mood_score = {"cheerful": 3, "okay": 2, "low": 1}
    rows = []
    for i in range(weeks - 1, -1, -1):
        start, end = now - timedelta(weeks=i + 1), now - timedelta(weeks=i)
        week = [c for c in checkins if start <= aware(c.at) < end and c.kind == "checkin"]
        done = [c for c in week if c.status == "done"]
        moods = [mood_score[c.mood] for c in done if c.mood in mood_score]
        wf = [f for f in flags if start <= aware(f.created_at) < end]
        rows.append(
            {
                "week_start": start.astimezone(IST).date().isoformat(),
                "calls": len(done),
                "missed": len(week) - len(done),
                "mood": round(sum(moods) / len(moods), 2) if moods else None,
                "flags": {lvl: sum(1 for f in wf if f.level == lvl) for lvl in ("green", "yellow", "red")},
            }
        )
    by_category: dict[str, int] = {}
    for f in flags:
        if aware(f.created_at) >= now - timedelta(weeks=weeks):
            by_category[f.category] = by_category.get(f.category, 0) + 1
    memory = []
    for c in sorted((c for c in checkins if c.kind == "memory"), key=lambda c: c.at):
        out = checkin_out(db, c, parent)
        memory.append(
            {
                "at": out["at"],
                "outcome": out["outcome"],
                "review_status": out["review_status"],
                "session_id": c.session_id,
            }
        )
    done_total = sum(r["calls"] for r in rows)
    planned_total = done_total + sum(r["missed"] for r in rows)
    return {
        "weeks": rows,
        "flags_by_category": by_category,
        "memory": memory,
        "calls_completed": done_total,
        "calls_planned": planned_total,
        "streak": _streak(checkins),
    }


def _streak(checkins: list[CheckIn]) -> int:
    weekly = sorted((c for c in checkins if c.kind == "checkin"), key=lambda c: c.at, reverse=True)
    n = 0
    for c in weekly:
        if c.status != "done":
            break
        n += 1
    return n


def doctor_summary(db: DBSession, parent: Parent) -> dict[str, Any]:
    """One page for a doctor. Only what the parent agreed to share; never a diagnosis."""
    rep = report(db, parent)
    rows = db.exec(select(Flag).where(Flag.parent_id == parent.id).order_by(Flag.created_at.desc())).all()  # type: ignore[attr-defined]
    flags = [flag_out(f) for f in _visible_flags(list(rows), parent)]
    memory_detail = None
    last = last_memory_check(db, parent)
    if last and last.session_id:
        score = db.exec(select(Score).where(Score.session_id == last.session_id)).first()
        if score:
            memory_detail = {
                "at": aware(last.at).isoformat(),
                "outcome": score.outcome,
                "learning_total": score.learning_total,
                "delayed_recall": score.delayed_recall,
                "fluency_count": score.fluency_count,
                "orientation_total": score.orientation_total,
                "schooling_band": score.band,
                "session_id": last.session_id,
            }
    return {
        "parent": parent_out(db, parent),
        "generated_at": utcnow().isoformat(),
        "consent": parent.share_level != ShareLevel.OKAY_ONLY,
        "flags": flags[:12] if parent.share_level != ShareLevel.OKAY_ONLY else [],
        "memory": memory_detail,
        "weeks": rep["weeks"],
        "flags_by_category": rep["flags_by_category"],
        "calls_completed": rep["calls_completed"],
        "calls_planned": rep["calls_planned"],
        "note": "Prepared by Smriti from weekly phone check-ins and a short phone memory check (10/66-based tasks). "
        "This is not a diagnosis. The parent agreed to share this summary.",
    }

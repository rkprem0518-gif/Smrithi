"""Session lifecycle: create -> call -> execution updates -> segment -> score -> report."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlmodel import Session as DBSession
from sqlmodel import func, select

from app.config_loader import FIXTURE_NAMES, load_fixture, markers, scoring_config
from app.db import new_db
from app.logs import log
from app.models import CallArtifact, Review, ReviewStatus, Score, Session, Status, utcnow
from app.scoring.engine import score_session
from app.scoring.outcome import INVALID, needs_review
from app.scoring.types import ScoringContext, Turn
from app.services import asr_fallback
from app.services.bolna_client import BolnaClient, BolnaError
from app.services.report import build_report
from app.services.segmenter import parse_bolna_transcript, segment, turns_from_json
from app.settings import Settings

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
FORMS = ("A", "B", "C")
DEMO_DAILY_LIMIT = 50

# Bolna execution status -> our session status (calls still in flight).
_IN_FLIGHT = {
    "scheduled": Status.CALLING, "queued": Status.CALLING, "rescheduled": Status.CALLING,
    "prepared": Status.CALLING, "initiated": Status.CALLING, "ringing": Status.CALLING,
    "in-progress": Status.IN_PROGRESS, "call-disconnected": Status.CALL_ENDED,
}
_FAILED_EXITS = {
    "no-answer": Status.NO_ANSWER, "busy": Status.BUSY, "failed": Status.FAILED,
    "error": Status.FAILED, "canceled": Status.FAILED, "balance-low": Status.FAILED,
    "stopped": Status.FAILED,
}


class SessionError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- helpers

def hash_value(value: str, salt: str) -> str:
    """Keyed hash (HMAC-SHA256). Without SECRET_SALT a phone hash cannot be brute-forced back."""
    return hmac.new(salt.encode(), value.encode(), hashlib.sha256).hexdigest()


# Order of in-flight statuses: updates never move a session backwards.
_RANK = {Status.CREATED: 0, Status.CALLING: 1, Status.IN_PROGRESS: 2, Status.CALL_ENDED: 3}
_CLAIMABLE = (Status.CREATED, Status.CALLING, Status.IN_PROGRESS, Status.CALL_ENDED)


def next_word_form(db: DBSession) -> str:
    """Rotate A/B/C across real (non-demo) sessions."""
    count = db.exec(select(func.count()).select_from(Session).where(Session.is_demo == False)).one()  # noqa: E712
    return FORMS[count % len(FORMS)]


def word_list_for(form: str, language: str) -> str:
    words = scoring_config().forms[form]
    pick = {"en": lambda w: w.en, "kn": lambda w: w.kn or w.en}.get(language, lambda w: w.hi)
    return ", ".join(pick(w) for w in words)


def build_user_data(session: Session) -> dict[str, Any]:
    """Filled into the prompt's {{placeholders}} by Bolna."""
    return {
        "session_id": session.id,
        "word_form": session.word_form,
        "language": session.language,
        "word_list": word_list_for(session.word_form, session.language),
    }


def _touch(db: DBSession, session: Session, status: str | None = None, **fields: Any) -> None:
    if status:
        session.status = status
    for k, v in fields.items():
        setattr(session, k, v)
    session.updated_at = utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)


def _count_since(db: DBSession, *where: Any) -> int:
    since = utcnow() - timedelta(days=1)
    return db.exec(
        select(func.count()).select_from(Session)
        .where(Session.created_at >= since, Session.is_demo == False, *where)  # noqa: E712
    ).one()


def check_rate_limit(db: DBSession, ip_hash: str, phone_hash: str | None, settings: Settings) -> None:
    """Per-IP, per-number and (live) global daily caps, so nobody can run up the Bolna bill."""
    ip_limit = DEMO_DAILY_LIMIT if settings.demo_mode else settings.max_calls_per_ip_per_day
    if _count_since(db, Session.ip_hash == ip_hash) >= ip_limit:
        raise SessionError(f"Daily limit reached ({ip_limit} calls per day). Please try again tomorrow.", 429)
    if settings.demo_mode:
        return
    if phone_hash and _count_since(db, Session.phone_hash == phone_hash) >= settings.max_calls_per_number_per_day:
        raise SessionError("This number has already been called today. Please try again tomorrow.", 429)
    if _count_since(db) >= settings.max_calls_per_day:
        raise SessionError("The demo has reached today's call limit. Please try again tomorrow.", 429)


# ---------------------------------------------------------------- create

async def create_session(
    db: DBSession,
    *,
    consent: bool,
    language: str,
    mode: str,
    schooling_years: int | None,
    phone: str | None,
    client_ip: str,
    settings: Settings,
    demo_fixture: str | None = None,
    enforce_rate_limit: bool = True,
) -> tuple[Session, dict[str, Any] | None]:
    """Returns (session, web_call_session or None)."""
    if not consent:
        raise SessionError("Consent is required before starting a memory check.", 400)
    if mode == "phone" and not settings.demo_mode and not (phone and E164.match(phone)):
        raise SessionError("Enter the phone number in international format, e.g. +919876543210.", 422)
    if phone and not E164.match(phone):
        raise SessionError("Enter the phone number in international format, e.g. +919876543210.", 422)
    ip_hash = hash_value(client_ip, settings.secret_salt)
    phone_hash = hash_value(phone, settings.secret_salt) if phone else None
    if enforce_rate_limit:
        check_rate_limit(db, ip_hash, phone_hash, settings)
    if settings.demo_mode:
        # A simulated call replays a fixture: its own language and schooling answer apply.
        schooling_years = None

    session = Session(
        mode=mode, language=language, schooling_years=schooling_years, consent_ui=True,
        word_form=next_word_form(db), ip_hash=ip_hash,
        phone_hash=phone_hash,
        phone_last4=phone[-4:] if phone else None,
    )
    if schooling_years is not None:
        session.schooling_band = "LOW" if schooling_years <= 10 else "HIGH"
    db.add(session)
    db.commit()
    db.refresh(session)
    log("session_created", session_id=session.id, mode=mode, language=language, demo=settings.demo_mode)

    if settings.demo_mode:
        fixture = demo_fixture if demo_fixture in FIXTURE_NAMES else "normal"
        fx = load_fixture(fixture)
        # The simulated transcript was spoken with the fixture's word list and language.
        _touch(db, session, Status.CALLING, word_form=fx["word_form"], language=fx["language"])
        asyncio.get_running_loop().create_task(simulate_demo_call(session.id, fixture, settings))
        return session, None

    settings.require_live()
    agent_id = settings.agent_id_for(language)
    if not agent_id:
        _touch(db, session, Status.FAILED, error="No Bolna agent is configured for this language.")
        raise SessionError("Kannada calls are not set up yet (BOLNA_AGENT_ID_KN is missing).", 503)
    async with BolnaClient.from_settings(settings) as client:
        try:
            if mode == "web":
                web = await client.create_web_call_session(agent_id, build_user_data(session))
                # TODO(bolna): confirm the web-call session's run_id is the execution id
                # used by GET /executions/{id}. If not, the webhook still links it via user_data.
                _touch(db, session, Status.CALLING, execution_id=web.get("run_id"))
                return session, web
            execution_id = await client.make_call(
                agent_id, phone or "", build_user_data(session),
                settings.bolna_from_number or None,
            )
        except BolnaError as exc:
            _touch(db, session, Status.FAILED, error=f"Could not start the call ({exc.status_code or 'network'}).")
            log("call_start_failed", session_id=session.id, status_code=exc.status_code)
            raise SessionError("The call could not be started. Please try again later.", 502) from exc
    _touch(db, session, Status.CALLING, execution_id=execution_id)
    log("call_started", session_id=session.id, execution_id=execution_id)
    return session, None


# ---------------------------------------------------------------- scoring

def score_and_save(
    db: DBSession,
    session: Session,
    turns: list[Turn],
    *,
    call_time: datetime,
    settings: Settings,
    recording_url: str | None = None,
    execution_redacted: dict[str, Any] | None = None,
    fluency_timestamps: list[tuple[str, float]] | None = None,
) -> Session:
    if not claim_for_scoring(db, session):
        return session  # another worker (webhook vs poller) already scored it, or it was deleted
    try:
        return _score_claimed(db, session, turns, call_time=call_time, settings=settings,
                              recording_url=recording_url, execution_redacted=execution_redacted,
                              fluency_timestamps=fluency_timestamps)
    except Exception as exc:
        db.rollback()
        db.refresh(session)
        _touch(db, session, Status.FAILED, error="Scoring failed; the call needs manual review.",
               review_status=ReviewStatus.PENDING)
        log("scoring_failed", session_id=session.id, error=type(exc).__name__)
        raise


def claim_for_scoring(db: DBSession, session: Session) -> bool:
    """Atomically move an open session to `scoring`. Exactly one caller wins."""
    result = db.execute(
        update(Session)
        .where(Session.id == session.id, Session.status.in_(_CLAIMABLE), Session.deleted_at.is_(None))  # type: ignore[attr-defined,union-attr]
        .values(status=Status.SCORING, updated_at=utcnow())
    )
    db.commit()
    db.refresh(session)
    return result.rowcount == 1


def _score_claimed(
    db: DBSession,
    session: Session,
    turns: list[Turn],
    *,
    call_time: datetime,
    settings: Settings,
    recording_url: str | None,
    execution_redacted: dict[str, Any] | None,
    fluency_timestamps: list[tuple[str, float]] | None,
) -> Session:
    cfg = scoring_config()
    db.add(CallArtifact(
        session_id=session.id,
        transcript_json=[{"role": t.role, "text": t.text, "t": t.t} for t in turns],
        recording_url=recording_url,
        execution_json_redacted=execution_redacted,
    ))
    segments = segment(turns, markers())
    if segments.declined and not segments.tasks:
        _touch(db, session, Status.DECLINED, consent_call=False)
        log("session_declined", session_id=session.id)
        return session

    ctx = ScoringContext(
        call_time=call_time, language=session.language, word_form=session.word_form,
        schooling_years=session.schooling_years, fluency_timestamps=fluency_timestamps,
    )
    result = score_session(segments, ctx, cfg).to_dict()
    report = build_report(result, cfg, word_form=session.word_form, language=session.language,
                          helpline_text=settings.helpline_text, call_time=call_time.isoformat())
    db.add(Score(
        session_id=session.id,
        scorer_version=result["scorer_version"],
        hearing=result["hearing"],
        learning_trials=result["learning"]["trials"],
        learning_total=result["learning"]["total"],
        fluency_count=result["fluency"]["count"],
        fluency_words=result["fluency"]["words"],
        orientation=result["orientation"],
        orientation_total=result["orientation"]["score"],
        delayed_recall=result["delayed_recall"]["score"],
        delayed_words=result["delayed_recall"]["words"],
        invalid_reasons=result["invalid_reasons"],
        outcome=result["outcome"],
        rule_fired=result["rule_fired"],
        band=result["band"],
        speech_markers=result["speech_markers"],
        report_json=report,
    ))
    if segments.stopped:
        status = Status.STOPPED
    elif result["outcome"] == INVALID:
        status = Status.INVALID
    else:
        status = Status.SCORED
    _touch(
        db, session, status,
        consent_call=result["consent_call"],
        schooling_band=result["band"],
        review_status=ReviewStatus.PENDING if needs_review(result["outcome"]) else ReviewStatus.NOT_NEEDED,
    )
    log("session_scored", session_id=session.id, outcome=result["outcome"], status=status)
    if session.deleted_at:  # "Delete this data" arrived while we were scoring
        delete_session_data(db, session)
    return session


def redact_execution(execution: dict[str, Any]) -> dict[str, Any]:
    """Keep what helps debugging; drop the transcript, numbers and user data."""
    keep = ("id", "agent_id", "status", "termination_reason", "error_message", "answered_by_voice_mail",
            "created_at", "updated_at", "conversation_duration", "total_cost")
    out = {k: execution.get(k) for k in keep if k in execution}
    tel = execution.get("telephony_data") or {}
    out["telephony_data"] = {k: tel.get(k) for k in ("duration", "call_type", "provider", "hangup_by",
                                                     "hangup_reason", "ring_duration") if k in tel}
    return out


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def apply_execution(db: DBSession, session: Session, execution: dict[str, Any], settings: Settings) -> Session:
    """Move the session along the state machine from a fresh GET /executions/{id} body."""
    db.refresh(session)  # the poller may hold a stale copy while the webhook already scored it
    if session.status in Status.FINAL or session.status == Status.SCORING or session.deleted_at:
        return session
    status = str(execution.get("status") or "").lower()
    if status in _IN_FLIGHT:
        if _RANK[_IN_FLIGHT[status]] > _RANK.get(session.status, 99):
            _touch(db, session, _IN_FLIGHT[status])
        return session
    if execution.get("answered_by_voice_mail"):
        _touch(db, session, Status.NO_ANSWER, error="Voicemail answered.")
        return session
    if status in _FAILED_EXITS:
        _touch(db, session, _FAILED_EXITS[status], error=f"Call ended with status '{status}'.")
        log("call_failed", session_id=session.id, execution_id=session.execution_id, bolna_status=status)
        return session
    if status != "completed":
        log("unknown_execution_status", session_id=session.id, bolna_status=status)
        return session

    turns = parse_bolna_transcript(execution.get("transcript"))
    recording_url = (execution.get("telephony_data") or {}).get("recording_url")
    call_time = _parse_time(execution.get("created_at")) or session.created_at.replace(tzinfo=UTC)
    cfg = scoring_config()
    stamps = await asr_fallback.fluency_timestamps(
        recording_url, settings, markers(), cfg.animal_lexicon, cfg.threshold
    )
    return score_and_save(
        db, session, turns, call_time=call_time, settings=settings, recording_url=recording_url,
        execution_redacted=redact_execution(execution), fluency_timestamps=stamps,
    )


async def refresh_from_bolna(session_id: str, settings: Settings) -> None:
    """Re-fetch the execution (never trust a webhook body alone) and apply it."""
    with new_db() as db:
        session = db.get(Session, session_id)
        if not session or not session.execution_id:
            return
        async with BolnaClient.from_settings(settings) as client:
            execution = await client.get_execution(session.execution_id)
        await apply_execution(db, session, execution, settings)


# ---------------------------------------------------------------- delete

def delete_session_data(db: DBSession, session: Session) -> None:
    """Soft-delete the session and wipe transcript, recording URL, scores and phone data."""
    for artifact in db.exec(select(CallArtifact).where(CallArtifact.session_id == session.id)).all():
        db.delete(artifact)
    for score in db.exec(select(Score).where(Score.session_id == session.id)).all():
        db.delete(score)
    for review in db.exec(select(Review).where(Review.session_id == session.id)).all():
        db.delete(review)
    session.phone_hash = None
    session.phone_last4 = None
    session.ip_hash = None
    session.deleted_at = utcnow()
    _touch(db, session)
    log("session_deleted", session_id=session.id)


# ---------------------------------------------------------------- demo mode

DEMO_IDS = {name: f"demo-{name.replace('_', '-')}" for name in FIXTURE_NAMES}


def seed_demo_sessions(settings: Settings) -> list[str]:
    """(Re)create the 4 fixture sessions, scored by the real engine. Idempotent."""
    ids = []
    with new_db() as db:
        for name, sid in DEMO_IDS.items():
            existing = db.get(Session, sid)
            if existing:
                delete_session_data(db, existing)
                db.delete(existing)
                db.commit()
            fx = load_fixture(name)
            session = Session(
                id=sid, mode="phone", language=fx["language"], schooling_years=fx["schooling_years"],
                word_form=fx["word_form"], consent_ui=True, is_demo=True, status=Status.CALL_ENDED,
                created_at=datetime.fromisoformat(fx["call_started_at"]).astimezone(UTC),
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            score_and_save(db, session, turns_from_json(fx["transcript"]),
                           call_time=datetime.fromisoformat(fx["call_started_at"]), settings=settings)
            ids.append(sid)
    log("demo_seeded", sessions=ids)
    return ids


async def simulate_demo_call(session_id: str, fixture: str, settings: Settings) -> None:
    """DEMO_MODE: walk a session through the real state machine using a fixture transcript."""
    step = settings.demo_call_step_seconds
    fx = load_fixture(fixture)
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
        # Fixture answers (day, month, time) refer to the fixture's own call time.
        score_and_save(db, session, turns_from_json(fx["transcript"]),
                       call_time=datetime.fromisoformat(fx["call_started_at"]), settings=settings)

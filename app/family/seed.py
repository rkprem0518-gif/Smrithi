"""Eight weeks of believable history for one parent ("Appa"), so no screen is ever empty in a demo.

Every weekly chat goes through the real flag rules (app/family/flags.py) with the parent's own words, so the
seeded flags are exactly what the engine would produce. The two memory checks are scored by the real engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.config_loader import load_fixture
from app.family.flags import analyze
from app.family.models import Appointment, CheckIn, Flag, Note, Parent, ShareLevel
from app.family.service import IST, flag_history, summarize
from app.models import CallArtifact, Review, Score, Session, Status, utcnow
from app.scoring.types import Turn
from app.services.orchestrator import score_and_save
from app.services.segmenter import turns_from_json
from app.settings import Settings

PARENT_ID = "appa"

# (weeks ago, status, topics, remembered, [(Kannada words, English)], message for family, duration s)
WEEKS: list[tuple[int, str, list[str], str, list[tuple[str, str]], tuple[str, str] | None, int]] = [
    (
        8,
        "done",
        ["Garden", "Cricket"],
        "",
        [("ಮಲ್ಲಿಗೆ ಗಿಡದಲ್ಲಿ ಹೂವು ಬಂದಿದೆ, ತುಂಬಾ ಖುಷಿ ಆಯ್ತು.", "The jasmine plant has flowered, I'm very happy.")],
        None,
        212,
    ),
    (
        7,
        "done",
        ["Pinky", "Temple"],
        "Asked about the jasmine plant",
        [("ಪಿಂಕಿ ಫೋನ್ ಮಾಡಿದ್ಲು, ಚೆನ್ನಾಗಿ ಮಾತಾಡಿದ್ವಿ.", "Pinky called, we had a good talk.")],
        None,
        188,
    ),
    (6, "missed", [], "", [], None, 0),
    (
        5,
        "done",
        ["Morning walk", "Cooking"],
        "",
        [("ಬೆಳಿಗ್ಗೆ ವಾಕ್ ಆದಮೇಲೆ ಮಂಡಿ ನೋವು ಬರುತ್ತೆ.", "My knee has pain after the morning walk.")],
        None,
        241,
    ),
    (
        4,
        "done",
        ["Cricket", "Visitors"],
        "Asked about his knee after the walk",
        [("ನಿನ್ನೆ ಮ್ಯಾಚ್ ನೋಡಿದೆ, ಚೆನ್ನಾಗಿತ್ತು.", "I watched the match yesterday, it was good.")],
        None,
        176,
    ),
    (
        3,
        "done",
        ["Deepavali plans", "Pinky"],
        "",
        [
            ("ದೀಪಾವಳಿಗೆ ರವಿ ಬರ್ತಾನೆ ಅಂತ ಕಾಯ್ತಿದ್ದೀನಿ.", "I'm waiting for Ravi to come for Deepavali."),
            ("ರಾತ್ರಿ ನಿದ್ದೆ ಬರ್ತಿಲ್ಲ.", "I'm not sleeping at night."),
        ],
        ("ರವಿಗೆ ಹೇಳು, ಹೊಸ ಕನ್ನಡಕ ಬೇಕು.", "Tell Ravi I need new glasses."),
        263,
    ),
    (
        2,
        "done",
        ["Temple", "Garden"],
        "Asked about the new glasses",
        [("ದೇವಸ್ಥಾನಕ್ಕೆ ನಡೆದು ಹೋದಾಗ ಮಂಡಿ ನೋವು ಜಾಸ್ತಿ ಆಯ್ತು.", "My knee hurt more after walking to the temple.")],
        None,
        225,
    ),
    (
        1,
        "done",
        ["Kannada Rajyotsava", "Morning walk"],
        "Asked about his knee after the temple walk",
        [
            ("ಎರಡು ಮೂರು ದಿನದಿಂದ ನಿದ್ದೆ ಬರ್ತಿಲ್ಲ.", "For two or three days I haven't been sleeping."),
            ("ಕನ್ನಡಕ ಎಲ್ಲಿಟ್ಟೆ ಅಂತ ಮರೆತುಬಿಟ್ಟೆ.", "I forgot where I kept my glasses."),
        ],
        None,
        254,
    ),
]

NEXT_NOTES = [
    "Knee hurt more after walking to the temple (said twice this month).",
    "Hasn't been sleeping well for a few nights.",
    "Ravi and Pinky are coming home for Deepavali.",
]


def _sunday(weeks_ago: int, now: datetime) -> datetime:
    local = now.astimezone(IST)
    last_sunday = local - timedelta(days=(local.weekday() - 6) % 7)
    return (last_sunday - timedelta(weeks=weeks_ago - 1)).replace(hour=10, minute=30, second=0, microsecond=0)


def clear(db: DBSession) -> None:
    for model in (Flag, Note, Appointment):
        for row in db.exec(select(model).where(model.parent_id == PARENT_ID)).all():
            db.delete(row)
    db.commit()
    for c in db.exec(select(CheckIn).where(CheckIn.parent_id == PARENT_ID)).all():
        if c.session_id:
            for model in (Score, CallArtifact, Review):
                for row in db.exec(select(model).where(model.session_id == c.session_id)).all():
                    db.delete(row)
            session = db.get(Session, c.session_id)
            if session:
                db.delete(session)
        db.delete(c)
    db.commit()
    parent = db.get(Parent, PARENT_ID)
    if parent:
        db.delete(parent)
        db.commit()


def seed(db: DBSession, settings: Settings, now: datetime | None = None, reset: bool = False) -> Parent:
    now = now or utcnow()
    if reset:
        clear(db)
    existing = db.get(Parent, PARENT_ID)
    if existing:
        return existing
    parent = Parent(
        id=PARENT_ID,
        full_name="Raghunath Rao",
        call_name="Appa",
        honorific="Raghunath ji",
        city="Mysuru",
        language="kn",
        family_name="Ravi",
        relation="son",
        share_level=ShareLevel.HEALTH,
        consent_at=_sunday(9, now),
        call_weekday=6,
        call_time="10:30",
        interests=["grandchild", "morning_walk", "temple", "cricket", "garden"],
        is_demo=True,
    )
    db.add(parent)
    db.commit()

    for weeks_ago, status, topics, remembered, quotes, message, duration in WEEKS:
        at = _sunday(weeks_ago, now)
        c = CheckIn(
            parent_id=PARENT_ID,
            kind="checkin",
            at=at,
            status=status,
            language="kn",
            topics=topics,
            remembered=remembered,
            duration_s=duration or None,
            is_seed=True,
        )
        db.add(c)
        db.commit()
        if status == "missed":
            c.summary = "Smriti called twice, no answer. Tried again the next day."
            db.add(c)
            db.commit()
            continue
        turns = [Turn("agent", "ನಮಸ್ಕಾರ! ಹೇಗಿದ್ದೀರಿ?")] + [Turn("user", kn) for kn, _ in quotes]
        if message:
            turns += [Turn("agent", "ರವಿ ಅವರಿಗೆ ಏನಾದರೂ ಹೇಳಬೇಕಾ?"), Turn("user", message[0])]
        result = analyze(turns, flag_history(db, PARENT_ID, before=at), now=at)
        english = dict(quotes)
        for f in result.flags:
            db.add(
                Flag(
                    parent_id=PARENT_ID,
                    checkin_id=c.id,
                    created_at=at,
                    category=f.category,
                    level=f.level,
                    quote=f.quote,
                    quote_en=english.get(f.quote),
                    rule=f.rule,
                    status="noted" if f.level == "green" else ("open" if weeks_ago <= 2 else "approved"),
                )
            )
        c.mood = result.mood
        c.quotes = [{"text": kn, "en": en} for kn, en in quotes]
        c.message_for_family = message[1] if message else None
        c.summary = summarize(c, result.flags, result.cleared)
        db.add(c)
        db.commit()

    for text in NEXT_NOTES:
        db.add(Note(parent_id=PARENT_ID, text=text, created_at=now - timedelta(days=4)))
    db.commit()

    _memory_check(db, settings, "kannada", at=_sunday(17, now) + timedelta(days=2), note="")
    # Appa chose Hindi for this check (the memory agent asks which language to use).
    two_days = (now - timedelta(days=2)).astimezone(IST).replace(hour=11, minute=0, second=0, microsecond=0)
    _memory_check(db, settings, "refer", at=two_days, note=" Waiting for the care team.")
    return parent


def _memory_check(db: DBSession, settings: Settings, fixture: str, at: datetime, note: str) -> None:
    fx = load_fixture(fixture)
    session = Session(
        mode="phone",
        language=fx["language"],
        schooling_years=fx["schooling_years"],
        word_form=fx["word_form"],
        consent_ui=True,
        is_demo=True,
        status=Status.CALL_ENDED,
        kind="memory",
        parent_id=PARENT_ID,
        created_at=at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    score_and_save(
        db,
        session,
        turns_from_json(fx["transcript"]),
        call_time=datetime.fromisoformat(fx["call_started_at"]),
        settings=settings,
    )
    score = db.exec(select(Score).where(Score.session_id == session.id)).first()
    outcome = score.outcome if score else None
    words = {
        "NORMAL": "No memory concerns showed up.",
        "REFER": "Worth seeing a doctor for a proper check.",
        "UNCERTAIN": "Unclear; a recheck is suggested.",
        "INVALID": "Could not get a reliable result.",
    }
    c = CheckIn(
        parent_id=PARENT_ID,
        session_id=session.id,
        kind="memory",
        at=at,
        status="done",
        language=fx["language"],
        outcome=outcome,
        duration_s=290,
        is_seed=True,
        summary=f"Memory check. {words.get(outcome or '', '')}{note}",
    )
    db.add(c)
    db.commit()

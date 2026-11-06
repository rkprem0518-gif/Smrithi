"""Family, elder and clinic apps: one API, three kinds of users.

Who can call what:
- anyone logged in sees only the circles they are an active member of (staff with ADMIN_REVIEW_TOKEN see all);
- only the elder (or staff) can change what is shared, pause calls, choose the language and approve who joins;
- only the care team (clinic users, or staff) can open the review queue and approve calls to the family.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.api.events import SSE_HEADERS, format_sse
from app.db import get_db
from app.family import callmode, people, service
from app.family.auth import (
    APPS,
    Principal,
    app_for_port,
    cookie_name,
    optional_principal,
    require_clinic,
    require_principal,
    sign,
)
from app.family.models import Appointment, CheckIn, Parent, Schedule, ShareLevel, User
from app.models import CallArtifact, utcnow
from app.services.events import bus
from app.services.orchestrator import hash_value
from app.settings import get_settings

LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "od": "Odia",
}
MEMORY_CHECK_LANGUAGES = ("hi", "kn", "en")  # word lists and scoring exist only for these

router = APIRouter(prefix="/api/family", tags=["family"])
care = APIRouter(prefix="/api/care", tags=["care team"])
auth = APIRouter(prefix="/api/auth", tags=["login"])
circle = APIRouter(prefix="/api/people", tags=["people"])


def _parent(db: DBSession, who: Principal, parent_id: str | None) -> Parent:
    allowed = who.parent_ids
    pid = parent_id or (allowed[0] if allowed else None)
    if not pid:
        raise HTTPException(404, "You are not in a family circle yet. Add your parent or ask them to add you.")
    if pid not in allowed:
        raise HTTPException(403, "You are not in this family circle.")
    parent = db.get(Parent, pid)
    if not parent:
        raise HTTPException(404, "Not found")
    return parent


def _elder_or_staff(who: Principal, parent: Parent) -> None:
    if not who.staff and who.role_for(parent.id) != "elder":
        raise HTTPException(403, f"Only {parent.call_name} can change this.")


def _clinic_view(who: Principal, parent_id: str) -> bool:
    return who.staff or who.role_for(parent_id) == "clinic"


# ---------------------------------------------------------------- login (demo)


class DemoLogin(BaseModel):
    user_id: str


@auth.get("/me")
def me(request: Request, who: Principal | None = Depends(optional_principal), db: DBSession = Depends(get_db)) -> dict:
    app = request.query_params.get("app") or app_for_port(request.url.port)
    app = app if app in APPS else "family"
    demo = [people.user_out(u) for u in db.exec(select(User).where(User.role == app, User.is_demo == True)).all()]  # noqa: E712
    s = get_settings()
    host = request.url.hostname or "localhost"
    out: dict[str, Any] = {
        "app": app,
        "demo_users": demo,
        "user": None,
        "staff": False,
        "parents": [],
        "languages": LANGUAGES,
        "demo_mode": s.demo_mode,
        "ports": {
            "family": f"http://{host}:{s.family_port}/smriti.html",
            "elder": f"http://{host}:{s.elder_port}/smriti.html",
            "clinic": f"http://{host}:{s.clinic_port}/smriti.html",
        },
    }
    if who:
        out["staff"] = who.staff
        out["user"] = people.user_out(who.user) if who.user else None
        out["parents"] = [
            {**service.parent_out(db, p), "my_role": who.role_for(p.id)}
            for p in (db.get(Parent, pid) for pid in who.parent_ids)
            if p
        ]
    return out


@auth.post("/demo-login")
def demo_login(body: DemoLogin, request: Request, response: Response, db: DBSession = Depends(get_db)) -> dict:
    user = db.get(User, body.user_id)
    if not user or not user.is_demo:
        raise HTTPException(404, "Unknown demo user")
    response.set_cookie(cookie_name(request), sign(user.id), httponly=True, samesite="lax", max_age=7 * 86400)
    return {"user": people.user_out(user)}


@auth.post("/logout")
def logout(request: Request, response: Response) -> dict:
    response.delete_cookie(cookie_name(request))
    return {"ok": True}


# ---------------------------------------------------------------- real calls or simulated (Bolna credits)


class CallMode(BaseModel):
    live: bool


@auth.get("/call-mode")
async def get_call_mode(who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    from app.services import ops

    s = get_settings()
    out = {"live": callmode.live(db, s), "available": callmode.available(s), "wallet": None}
    if out["available"]:
        account = await ops.bolna_account(s)  # cached for a minute; no call is placed
        out["wallet"] = account.get("wallet")
    return out


@auth.put("/call-mode")
async def put_call_mode(
    body: CallMode, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict:
    s = get_settings()
    if body.live and not callmode.available(s):
        raise HTTPException(409, "Real calls need the live server (DEMO_MODE=0 with Bolna keys). Calls stay simulated.")
    now = callmode.set_live(db, s, body.live, who.name)
    for pid in who.parent_ids:
        what = "Real calls on: calls now use Bolna credits." if now else "Real calls off: calls are simulated."
        people.log(db, pid, f"{who.name} switched {what[0].lower() + what[1:]}", kind="settings", actor=who.user)
    return {"live": now, "available": callmode.available(s)}


# ---------------------------------------------------------------- live updates for all three apps


@auth.get("/live")
async def live(request: Request, who: Principal = Depends(require_principal)) -> StreamingResponse:
    """Every change in this user's circles (calls, reviews, joins, schedules), as Server-Sent Events."""
    allowed = set(who.parent_ids)
    clinic_ok = {pid for pid in allowed if _clinic_view(who, pid)}
    sub = bus.subscribe(None)
    keepalive = get_settings().sse_keepalive_seconds

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=keepalive)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event.get("type") == "call_mode":  # the shared credits switch: every app shows it
                    yield format_sse(event)
                    continue
                pid = event.get("parent_id")
                if pid not in allowed:
                    continue
                if event.get("audience") == "clinic" and pid not in clinic_ok:
                    continue
                yield format_sse(event)
        finally:
            bus.unsubscribe(sub)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


# ---------------------------------------------------------------- family app


class CallRequest(BaseModel):
    phone: str | None = None
    name: str | None = Field(default=None, max_length=60)  # who will pick up (the judge, in a demo)
    parent_id: str | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
    language: str | None = Field(default=None, max_length=4)  # None = their preferred language; "ask" = let them choose


class ApproveRequest(BaseModel):
    family_phone: str | None = None
    note: str = Field(default="", max_length=500)
    parent_id: str | None = None
    language: str | None = Field(default=None, max_length=4)


class SettingsUpdate(BaseModel):
    share_level: str | None = None
    call_weekday: int | None = Field(default=None, ge=0, le=6)
    call_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    language: str | None = None
    calls_paused: bool | None = None
    parent_id: str | None = None
    # The names Smriti says on calls. Family members and the elder can set these.
    full_name: str | None = Field(default=None, min_length=2, max_length=60)
    call_name: str | None = Field(default=None, min_length=1, max_length=30)  # what the family calls them: "Amma"
    honorific: str | None = Field(default=None, min_length=1, max_length=40)  # how Smriti greets them
    family_name: str | None = Field(default=None, min_length=1, max_length=30)  # who Smriti passes messages to
    relation: str | None = Field(default=None, min_length=1, max_length=20)


class MeUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=60)


class VisitRequest(BaseModel):
    title: str = Field(default="Doctor visit", max_length=80)
    parent_id: str | None = None


@router.get("/home")
def home(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    tl = service.timeline(db, parent, limit=12)
    return {
        "parent": service.parent_out(db, parent),
        "week": service.this_week(db, parent),
        "latest": tl[0] if tl else None,
        "recent": tl,
        "visits": [_visit_out(a) for a in service.appointments(db, parent) if service.aware(a.starts_at) >= utcnow()],
        "schedules": [people.schedule_out(s, db) for s in _schedules(db, parent)],
        "demo_mode": get_settings().demo_mode,
    }


@router.get("/timeline")
def timeline(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"parent": service.parent_out(db, parent), "items": service.timeline(db, parent)}


@router.get("/checkins/{checkin_id}")
def checkin(checkin_id: str, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    c = db.get(CheckIn, checkin_id)
    if not c or c.parent_id not in who.parent_ids:
        raise HTTPException(404, "Not found")
    return service.checkin_out(db, c, db.get(Parent, c.parent_id), for_family=not _clinic_view(who, c.parent_id))


@router.post("/call", status_code=201)
async def call_now(
    body: CallRequest, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, body.parent_id)
    data, topics, remembered = service.checkin_user_data(
        db, parent, name=body.name, questions=body.questions, language=body.language
    )
    try:
        session, c = await service.start_call(
            db,
            kind="checkin",
            parent=parent,
            phone=body.phone,
            settings=get_settings(),
            user_data=data,
            topics=topics,
            remembered=remembered,
            language=data["agent_language"],
            actor=who.user,
            allow_paused=who.role_for(parent.id) == "elder",  # "call me now" from the elder always works
        )
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {
        "session_id": session.id,
        "checkin_id": c.id,
        "status": session.status,
        "topics": topics,
        "remembered": remembered,
    }


@router.post("/memory-check", status_code=201)
async def memory_check(
    body: CallRequest, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    """Run the real memory-check call (the original Smriti agent) and put it on the parent's timeline."""
    from app.services import orchestrator

    parent = _parent(db, who, body.parent_id)
    if parent.calls_paused and who.role_for(parent.id) != "elder":
        raise HTTPException(409, f"{parent.call_name} has paused calls.")
    language = parent.language if parent.language in MEMORY_CHECK_LANGUAGES else "en"
    try:
        session, _ = await orchestrator.create_session(
            db,
            consent=True,
            language=language,
            mode="phone",
            schooling_years=None,
            phone=body.phone,
            client_ip="family-app",
            settings=callmode.effective(db, get_settings()),
            enforce_rate_limit=False,
        )
    except orchestrator.SessionError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    session.kind, session.parent_id = "memory", parent.id
    db.add(session)
    c = CheckIn(
        parent_id=parent.id,
        session_id=session.id,
        kind="memory",
        status="calling",
        language=language,
        summary="Memory check.",
    )
    db.add(c)
    db.commit()
    people.log(
        db,
        parent.id,
        f"{who.name} started a memory check for {parent.call_name}.",
        kind="call",
        actor=who.user,
        ref=c.id,
    )
    return {"session_id": session.id, "checkin_id": c.id, "status": session.status}


@router.get("/calendar")
def calendar(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"parent": service.parent_out(db, parent), "events": service.calendar(db, parent)}


@router.post("/visits", status_code=201)
def request_visit(
    body: VisitRequest, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, body.parent_id)
    a = Appointment(
        parent_id=parent.id,
        title=f"{body.title} · {parent.call_name}",
        starts_at=service.suggested_visit(),
        place=service.DEMO_GP,
        source=f"requested by {who.name}",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    people.log(
        db,
        parent.id,
        f"{who.name} requested a doctor's visit for {parent.call_name}.",
        kind="visit",
        actor=who.user,
        ref=a.id,
    )
    return _visit_out(a)


def _visit_out(a: Appointment) -> dict[str, Any]:
    start = service.aware(a.starts_at)
    end = start + timedelta(minutes=a.minutes)
    fmt = "%Y%m%dT%H%M%SZ"
    google = (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={quote(a.title)}&dates={start:{fmt}}/{end:{fmt}}"
        f"&details={quote('Added by Smriti. ' + a.source)}&location={quote(a.place)}"
    )
    return {
        "id": a.id,
        "title": a.title,
        "at": start.isoformat(),
        "minutes": a.minutes,
        "place": a.place,
        "status": a.status,
        "source": a.source,
        "google_calendar_url": google,
    }


@router.get("/visits")
def visits(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"items": [_visit_out(a) for a in service.appointments(db, parent)]}


@router.get("/calendar.ics")
def calendar_ics(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> Response:
    parent = _parent(db, who, parent_id)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Smriti//Family calendar//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:Smriti · {parent.call_name}",
    ]
    fmt = "%Y%m%dT%H%M%SZ"
    for e in service.calendar(db, parent):
        if e["type"] not in ("planned", "visit", "memory_due"):
            continue
        start = datetime.fromisoformat(e["at"]).astimezone(UTC)
        end = start + timedelta(minutes=int(e.get("minutes") or 30))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['type']}-{start:{fmt}}@smriti",
            f"DTSTAMP:{utcnow():{fmt}}",
            f"DTSTART:{start:{fmt}}",
            f"DTEND:{end:{fmt}}",
            f"SUMMARY:{e['title']}",
            f"LOCATION:{e.get('place', '')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return Response(
        "\r\n".join(lines) + "\r\n",
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="smriti-calendar.ics"'},
    )


@router.get("/smriti.vcf")
def contact_card(who: Principal = Depends(require_principal)) -> Response:
    number = get_settings().bolna_from_number or ""
    card = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "FN:Smriti (family check-in)",
        "ORG:Smriti",
        "NOTE:Smriti calls to check in. Smriti never asks for money\\, bank details or an OTP.",
    ]
    if number:
        card.append(f"TEL;TYPE=CELL:{number}")
    card.append("END:VCARD")
    return Response(
        "\r\n".join(card) + "\r\n",
        media_type="text/vcard",
        headers={"Content-Disposition": 'attachment; filename="Smriti.vcf"'},
    )


@router.get("/report")
def report(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"parent": service.parent_out(db, parent), **service.report(db, parent)}


@router.get("/doctor-summary")
def doctor_summary(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    if parent.share_level == ShareLevel.OKAY_ONLY and not _clinic_view(who, parent.id):
        raise HTTPException(403, f"{parent.call_name} chose to share only that they are doing well.")
    return service.doctor_summary(db, parent)


@router.patch("/settings")
def update_settings(
    body: SettingsUpdate, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    """The elder decides what is shared, their language and whether calls are paused. Family can suggest call
    times (the elder can change them back)."""
    parent = _parent(db, who, body.parent_id)
    changes = []
    if body.share_level is not None or body.language is not None or body.calls_paused is not None:
        _elder_or_staff(who, parent)
    if body.share_level is not None:
        if body.share_level not in ShareLevel.ALL_LEVELS:
            raise HTTPException(422, "Unknown sharing level")
        parent.share_level = body.share_level
        changes.append(
            {
                "okay_only": "share only that they are okay",
                "health": "share health worries",
                "all": "share everything we talk about",
            }[body.share_level]
        )
    if body.language is not None:
        if body.language not in LANGUAGES:
            raise HTTPException(422, "Unknown language")
        parent.language = body.language
        changes.append(f"speak {LANGUAGES[body.language]}")
    if body.calls_paused is not None:
        parent.calls_paused = body.calls_paused
        changes.append("pause calls" if body.calls_paused else "turn calls back on")
    for name in ("call_weekday", "call_time"):
        value = getattr(body, name)
        if value is not None:
            setattr(parent, name, value)
            changes.append("change the weekly call time")
    names = {k: getattr(body, k) for k in ("full_name", "call_name", "honorific", "family_name", "relation")}
    names = {k: v.strip() for k, v in names.items() if v is not None and v.strip()}
    if names:
        if not who.staff and who.role_for(parent.id) not in ("family", "elder"):
            raise HTTPException(403, "Only the family can change these names.")
        for k, v in names.items():
            setattr(parent, k, v)
        changes.append("update the names Smriti uses")
    db.add(parent)
    db.commit()
    if changes:
        people.log(
            db, parent.id, f"{who.name} chose to {', '.join(dict.fromkeys(changes))}.", kind="settings", actor=who.user
        )
    return service.parent_out(db, parent)


@router.get("/history")
def history(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"items": people.history(db, parent.id, clinic_view=_clinic_view(who, parent.id))}


# ---------------------------------------------------------------- schedules


class ScheduleIn(BaseModel):
    label: str = Field(default="Check-in", max_length=60)
    kind: str = Field(default="checkin", pattern=r"^(checkin|memory)$")
    days: list[int] = Field(default_factory=list)
    time: str = Field(default="20:00", pattern=r"^\d{2}:\d{2}$")
    questions: list[str] = Field(default_factory=list, max_length=5)
    active: bool = True
    parent_id: str | None = None


class RunRequest(BaseModel):
    phone: str | None = None
    name: str | None = None
    language: str | None = Field(default=None, max_length=4)


def _schedules(db: DBSession, parent: Parent) -> list[Schedule]:
    return list(db.exec(select(Schedule).where(Schedule.parent_id == parent.id).order_by(Schedule.time)).all())


@router.get("/schedules")
def schedules(
    parent_id: str | None = None, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, parent_id)
    return {"items": [people.schedule_out(s, db) for s in _schedules(db, parent)]}


@router.post("/schedules", status_code=201)
def add_schedule(
    body: ScheduleIn, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parent = _parent(db, who, body.parent_id)
    if any(d < 0 or d > 6 for d in body.days):
        raise HTTPException(422, "Days are 0 (Monday) to 6 (Sunday)")
    s = Schedule(
        parent_id=parent.id,
        created_by=who.id,
        label=body.label,
        kind=body.kind,
        days=sorted(set(body.days)),
        time=body.time,
        questions=[q.strip() for q in body.questions if q.strip()],
        active=body.active,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    when = (
        "every day" if not s.days else ", ".join(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d] for d in s.days)
    )
    people.log(
        db,
        parent.id,
        f"{who.name} scheduled “{s.label}” {when} at {s.time}.",
        kind="schedule",
        actor=who.user,
        ref=s.id,
    )
    return people.schedule_out(s, db)


@router.patch("/schedules/{schedule_id}")
def edit_schedule(
    schedule_id: str, body: ScheduleIn, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    s = db.get(Schedule, schedule_id)
    if not s or s.parent_id not in who.parent_ids:
        raise HTTPException(404, "Not found")
    s.label, s.kind, s.days, s.time = body.label, body.kind, sorted(set(body.days)), body.time
    s.questions, s.active = [q.strip() for q in body.questions if q.strip()], body.active
    db.add(s)
    db.commit()
    people.log(
        db,
        s.parent_id,
        f"{who.name} {'updated' if s.active else 'paused'} “{s.label}”.",
        kind="schedule",
        actor=who.user,
        ref=s.id,
    )
    return people.schedule_out(s, db)


@router.post("/schedules/{schedule_id}/run", status_code=201)
async def run_schedule(
    schedule_id: str, body: RunRequest, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    s = db.get(Schedule, schedule_id)
    if not s or s.parent_id not in who.parent_ids:
        raise HTTPException(404, "Not found")
    s.last_run_at = utcnow()
    db.add(s)
    db.commit()
    req = CallRequest(
        phone=body.phone, name=body.name, parent_id=s.parent_id, questions=s.questions, language=body.language
    )
    if s.kind == "memory":
        return await memory_check(req, who, db)
    return await call_now(req, who, db)


# ---------------------------------------------------------------- contacts and the family circle


class AddContact(BaseModel):
    query: str = Field(min_length=3, max_length=40)  # a phone number (+91...) or a Smriti ID (SM-...)


class InviteIn(BaseModel):
    query: str = Field(min_length=3, max_length=40)
    role: str = Field(default="family", pattern=r"^(family|clinic)$")
    parent_id: str | None = None


class Decision(BaseModel):
    accept: bool


def _lookup(db: DBSession, query: str) -> User:
    q = query.replace(" ", "").replace("-", "") if query.strip().startswith("+") else query.strip()
    phone_hash = hash_value(q, get_settings().secret_salt) if q.startswith("+") else None
    user = people.find_user(db, q, phone_hash)
    if not user:
        raise HTTPException(404, "Nobody on Smriti with that number or ID yet. Ask them to join, then try again.")
    return user


@circle.patch("/me")
def update_me(body: MeUpdate, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    """Change your own display name (shown in the apps and the history)."""
    if not who.user:
        raise HTTPException(400, "Log in as a person to change your name")
    who.user.name = body.name.strip()
    db.add(who.user)
    db.commit()
    return people.user_out(who.user)


@circle.get("/me")
def my_people(who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict[str, Any]:
    if not who.user:
        return {"me": None, "contacts": [], "circles": []}
    circles = []
    for pid in who.parent_ids:
        c = people.circle_for(db, pid)
        if c:
            circles.append(people.circle_out(db, c))
    return {"me": people.user_out(who.user), "contacts": people.contacts(db, who.user), "circles": circles}


@circle.post("/contacts", status_code=201)
def add_contact(
    body: AddContact, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    if not who.user:
        raise HTTPException(400, "Log in as a person to add contacts")
    try:
        return people.add_contact(db, who.user, _lookup(db, body.query))
    except people.PeopleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@circle.post("/invite", status_code=201)
def invite(body: InviteIn, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    parent = _parent(db, who, body.parent_id)
    c = people.circle_for(db, parent.id)
    if not c:
        raise HTTPException(404, "No circle")
    try:
        m = people.invite(db, c, who.user, _lookup(db, body.query), body.role)
    except people.PeopleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"member_id": m.id, "status": m.status, "circle": people.circle_out(db, c)}


@circle.post("/members/{member_id}/decide")
def decide(
    member_id: int, body: Decision, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    from app.family.models import Circle, CircleMember

    m = db.get(CircleMember, member_id)
    c = db.get(Circle, m.circle_id) if m else None
    if not c or c.parent_id not in who.parent_ids:
        raise HTTPException(404, "Not found")
    _elder_or_staff(who, db.get(Parent, c.parent_id))
    try:
        people.decide(db, member_id, who.user, body.accept)
    except people.PeopleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return people.circle_out(db, c)


# ---------------------------------------------------------------- care team (clinic app)


@care.get("/ops")
async def care_ops(who: Principal = Depends(require_clinic), db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """Cost and duration of recent calls plus the Bolna wallet, for the care team's "behind the call" view."""
    from app.services import ops

    s = get_settings()
    return {
        "mode": "demo" if s.demo_mode else "live",
        "simulated": s.demo_mode,
        "bolna": await ops.bolna_account(s),
        "sessions": ops.session_stats(db, s, 50),
        "units_note": ops.UNITS_NOTE,
    }


@care.get("/patients")
def patients(who: Principal = Depends(require_clinic), db: DBSession = Depends(get_db)) -> dict[str, Any]:
    out = []
    for pid in who.parent_ids:
        p = db.get(Parent, pid)
        if not p:
            continue
        q = service.care_queue(db, p)
        last = service.last_memory_check(db, p)
        tl = service.timeline(db, p, limit=1)
        out.append(
            {
                **service.parent_out(db, p),
                "open_cases": len(q),
                "worst": q[0]["level"] if q else None,
                "last_memory_outcome": service.checkin_out(db, last, p, for_family=False)["outcome"] if last else None,
                "last_contact": tl[0]["at"] if tl else None,
            }
        )
    return {"items": out}


@care.get("/queue")
def care_queue(
    parent_id: str | None = None, who: Principal = Depends(require_clinic), db: DBSession = Depends(get_db)
) -> dict[str, Any]:
    parents = [_parent(db, who, parent_id)] if parent_id else [db.get(Parent, pid) for pid in who.parent_ids]
    items = []
    for parent in (p for p in parents if p):
        for item in service.care_queue(db, parent):
            art = (
                db.exec(select(CallArtifact).where(CallArtifact.session_id == item["session_id"])).first()
                if item.get("session_id")
                else None
            )
            item["transcript"] = art.transcript_json if art else []
            item["recording_url"] = art.recording_url if art else None
            item["parent"] = {
                "id": parent.id,
                "call_name": parent.call_name,
                "full_name": parent.full_name,
                "family_name": parent.family_name,
                "age": parent.age,
            }
            items.append(item)
    rank = {"red": 0, "memory": 1, "yellow": 2, "green": 3}
    items.sort(key=lambda i: (rank.get(i["level"], 9), i["at"]))
    first = parents[0] if parents and parents[0] else None
    return {"parent": service.parent_out(db, first) if first else None, "items": items}


@care.post("/{case_type}/{case_id}/approve")
async def approve(
    case_type: str,
    case_id: str,
    body: ApproveRequest,
    who: Principal = Depends(require_clinic),
    db: DBSession = Depends(get_db),
) -> dict:
    if case_type not in ("flag", "memory"):
        raise HTTPException(404, "Unknown case type")
    parent = _parent(db, who, body.parent_id or _case_parent(db, case_type, case_id))
    try:
        return await service.approve_case(
            db,
            parent,
            case_type,
            case_id,
            body.family_phone,
            get_settings(),
            note=body.note,
            actor=who.user,
            language=body.language,
        )
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@care.post("/{case_type}/{case_id}/dismiss")
def dismiss(
    case_type: str,
    case_id: str,
    body: ApproveRequest,
    who: Principal = Depends(require_clinic),
    db: DBSession = Depends(get_db),
) -> dict:
    if case_type not in ("flag", "memory"):
        raise HTTPException(404, "Unknown case type")
    _parent(db, who, body.parent_id or _case_parent(db, case_type, case_id))
    try:
        service.dismiss_case(db, case_type, case_id, body.note, actor=who.user)
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"dismissed": True}


def _case_parent(db: DBSession, case_type: str, case_id: str) -> str | None:
    from app.family.models import Flag

    row = db.get(Flag, case_id) if case_type == "flag" else db.get(CheckIn, case_id)
    return row.parent_id if row else None


# ---------------------------------------------------------------- add a parent / reset demo profiles


class NewParent(BaseModel):
    full_name: str = Field(min_length=2, max_length=60)
    call_name: str = Field(default="", max_length=30)  # what the family calls them: "Amma"
    age: int | None = Field(default=None, ge=40, le=120)
    city: str = Field(default="", max_length=40)
    language: str = Field(default="en")
    relation: str = Field(default="son", max_length=20)  # the family member's relation to them
    share_level: str = Field(default="health")


@circle.post("/parents", status_code=201)
def add_parent(body: NewParent, who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    if not who.user or who.user.role != "family":
        raise HTTPException(403, "Only a family member can add a parent")
    if body.language not in LANGUAGES:
        raise HTTPException(422, "Unknown language")
    parent = people.create_parent(
        db,
        who.user,
        full_name=body.full_name.strip(),
        call_name=body.call_name.strip(),
        age=body.age,
        city=body.city.strip(),
        language=body.language,
        relation=body.relation.strip() or "family",
        share_level=body.share_level,
    )
    return service.parent_out(db, parent)


@circle.post("/reset-demo")
def reset_demo(who: Principal = Depends(require_principal), db: DBSession = Depends(get_db)) -> dict:
    if not who.staff and not (who.user and who.user.is_demo):
        raise HTTPException(403, "Only demo accounts can reset demo data")
    removed = people.reset_created(db)
    return {"removed": removed}

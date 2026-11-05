"""Family app + care desk API. Everything here is personal, so every route needs the access token
(ADMIN_REVIEW_TOKEN, as a Bearer header or ?token= for downloads and links)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.api.review import check_reviewer_token
from app.db import get_db
from app.family import service
from app.family.models import Appointment, Parent, ShareLevel
from app.models import CallArtifact, utcnow
from app.settings import get_settings


def require_access(authorization: str = Header(default=""), token: str = Query(default="")) -> None:
    check_reviewer_token(authorization.removeprefix("Bearer ").strip() or token)


router = APIRouter(prefix="/api/family", tags=["family"], dependencies=[Depends(require_access)])


def _parent(db: DBSession, parent_id: str | None) -> Parent:
    try:
        return service.get_parent(db, parent_id)
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


class CallRequest(BaseModel):
    phone: str | None = None
    name: str | None = Field(default=None, max_length=60)  # who will pick up (the judge, in a demo)
    parent_id: str | None = None


class ApproveRequest(BaseModel):
    family_phone: str | None = None
    note: str = Field(default="", max_length=500)
    parent_id: str | None = None


class SettingsUpdate(BaseModel):
    share_level: str | None = None
    call_weekday: int | None = Field(default=None, ge=0, le=6)
    call_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    language: str | None = Field(default=None, pattern=r"^(hi|kn|en)$")
    parent_id: str | None = None


class VisitRequest(BaseModel):
    title: str = Field(default="Doctor visit", max_length=80)
    parent_id: str | None = None


@router.get("/home")
def home(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    tl = service.timeline(db, parent, limit=12)
    return {
        "parent": service.parent_out(db, parent),
        "week": service.this_week(db, parent),
        "latest": tl[0] if tl else None,
        "recent": tl,
        "visits": [_visit_out(a) for a in service.appointments(db, parent) if service.aware(a.starts_at) >= utcnow()],
        "demo_mode": get_settings().demo_mode,
    }


@router.get("/timeline")
def timeline(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    return {"parent": service.parent_out(db, parent), "items": service.timeline(db, parent)}


@router.get("/checkins/{checkin_id}")
def checkin(checkin_id: str, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    from app.family.models import CheckIn

    c = db.get(CheckIn, checkin_id)
    if not c:
        raise HTTPException(404, "Not found")
    return service.checkin_out(db, c, _parent(db, c.parent_id))


@router.post("/call", status_code=201)
async def call_now(body: CallRequest, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, body.parent_id)
    data, topics, remembered = service.checkin_user_data(db, parent, name=body.name)
    try:
        session, checkin = await service.start_call(
            db,
            kind="checkin",
            parent=parent,
            phone=body.phone,
            settings=get_settings(),
            user_data=data,
            topics=topics,
            remembered=remembered,
        )
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {
        "session_id": session.id,
        "checkin_id": checkin.id,
        "status": session.status,
        "topics": topics,
        "remembered": remembered,
    }


@router.post("/memory-check", status_code=201)
async def memory_check(body: CallRequest, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """Run the real memory-check call (the original Smriti agent) and put it on the parent's timeline."""
    from app.family.models import CheckIn
    from app.services import orchestrator

    parent = _parent(db, body.parent_id)
    settings = get_settings()
    try:
        session, _ = await orchestrator.create_session(
            db,
            consent=True,
            language=parent.language,
            mode="phone",
            schooling_years=None,
            phone=body.phone,
            client_ip="family-app",
            settings=settings,
            enforce_rate_limit=False,
        )
    except orchestrator.SessionError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    session.kind, session.parent_id = "memory", parent.id
    db.add(session)
    checkin = CheckIn(
        parent_id=parent.id,
        session_id=session.id,
        kind="memory",
        status="calling",
        language=parent.language,
        summary="Memory check.",
    )
    db.add(checkin)
    db.commit()
    return {"session_id": session.id, "checkin_id": checkin.id, "status": session.status}


@router.get("/calendar")
def calendar(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    return {"parent": service.parent_out(db, parent), "events": service.calendar(db, parent)}


@router.post("/visits", status_code=201)
def request_visit(body: VisitRequest, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, body.parent_id)
    a = Appointment(
        parent_id=parent.id,
        title=f"{body.title} · {parent.call_name}",
        starts_at=service.suggested_visit(),
        place=service.DEMO_GP,
        source="family app",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
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
def visits(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    return {"items": [_visit_out(a) for a in service.appointments(db, parent)]}


@router.get("/calendar.ics")
def calendar_ics(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> Response:
    parent = _parent(db, parent_id)
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
def contact_card() -> Response:
    number = get_settings().bolna_from_number or ""
    card = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "FN:Smriti (family check-in)",
        "ORG:Smriti",
        "NOTE:Smriti calls every week for a short chat. Smriti never asks for money\\, bank details or an OTP.",
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
def report(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    return {"parent": service.parent_out(db, parent), **service.report(db, parent)}


@router.get("/doctor-summary")
def doctor_summary(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    if parent.share_level == ShareLevel.OKAY_ONLY:
        raise HTTPException(403, f"{parent.call_name} chose to share only that they are doing well.")
    return service.doctor_summary(db, parent)


@router.patch("/settings")
def update_settings(body: SettingsUpdate, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    """Call time and language are suggestions the parent confirms on the next call. The sharing level is
    the parent's choice: in the real product only the parent can change it (by voice)."""
    parent = _parent(db, body.parent_id)
    if body.share_level is not None:
        if body.share_level not in ShareLevel.ALL_LEVELS:
            raise HTTPException(422, "Unknown sharing level")
        parent.share_level = body.share_level
    for name in ("call_weekday", "call_time", "language"):
        value = getattr(body, name)
        if value is not None:
            setattr(parent, name, value)
    db.add(parent)
    db.commit()
    return service.parent_out(db, parent)


# ---------------------------------------------------------------- care desk

care = APIRouter(prefix="/api/care", tags=["care desk"], dependencies=[Depends(require_access)])


@care.get("/queue")
def care_queue(parent_id: str | None = None, db: DBSession = Depends(get_db)) -> dict[str, Any]:
    parent = _parent(db, parent_id)
    items = service.care_queue(db, parent)
    for item in items:
        art = (
            db.exec(select(CallArtifact).where(CallArtifact.session_id == item["session_id"])).first()
            if item.get("session_id")
            else None
        )
        item["transcript"] = art.transcript_json if art else []
        item["recording_url"] = art.recording_url if art else None
    return {"parent": service.parent_out(db, parent), "items": items}


@care.post("/{case_type}/{case_id}/approve")
async def approve(case_type: str, case_id: str, body: ApproveRequest, db: DBSession = Depends(get_db)) -> dict:
    if case_type not in ("flag", "memory"):
        raise HTTPException(404, "Unknown case type")
    parent = _parent(db, body.parent_id)
    try:
        return await service.approve_case(
            db, parent, case_type, case_id, body.family_phone, get_settings(), note=body.note
        )
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@care.post("/{case_type}/{case_id}/dismiss")
def dismiss(case_type: str, case_id: str, body: ApproveRequest, db: DBSession = Depends(get_db)) -> dict:
    if case_type not in ("flag", "memory"):
        raise HTTPException(404, "Unknown case type")
    try:
        service.dismiss_case(db, case_type, case_id, body.note)
    except service.FamilyError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"dismissed": True}

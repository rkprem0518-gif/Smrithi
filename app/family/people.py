"""People around the elder: logins, contacts (by phone or Smriti ID), the family circle, schedules, history."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.family.models import Activity, Circle, CircleMember, Contact, Parent, Schedule, User
from app.models import utcnow
from app.services import events

_LANG_NAMES = {
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
ROLE_LABEL = {"elder": "Elder", "family": "Family", "clinic": "Care team"}


class PeopleError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def new_smriti_id(db: DBSession, name: str) -> str:
    stem = "".join(ch for ch in name.upper() if ch.isalpha())[:5] or "SMRITI"
    while True:
        sid = f"SM-{stem}{''.join(secrets.choice(string.digits) for _ in range(2))}"
        if not db.exec(select(User).where(User.smriti_id == sid)).first():
            return sid


def user_out(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "name": u.name,
        "role": u.role,
        "role_label": ROLE_LABEL.get(u.role, u.role),
        "smriti_id": u.smriti_id,
        "phone_last4": u.phone_last4,
        "age": u.age,
        "org": u.org,
        "title": u.title,
        "language": u.language,
    }


# ---------------------------------------------------------------- history


def log(
    db: DBSession,
    parent_id: str,
    text: str,
    *,
    kind: str = "info",
    actor: Any = None,
    ref: str | None = None,
    audience: str = "all",
    commit: bool = True,
) -> Activity:
    actor_id = getattr(actor, "id", None)
    actor_name = getattr(actor, "name", None) or "Smriti"
    a = Activity(
        parent_id=parent_id, text=text, kind=kind, actor_id=actor_id, actor_name=actor_name, ref=ref, audience=audience
    )
    db.add(a)
    if commit:
        db.commit()
    events.publish_activity(parent_id, kind, text, audience=audience, ref=ref)
    return a


def history(db: DBSession, parent_id: str, clinic_view: bool, limit: int = 60) -> list[dict[str, Any]]:
    q = select(Activity).where(Activity.parent_id == parent_id).order_by(Activity.at.desc()).limit(limit)  # type: ignore[attr-defined]
    out = []
    for a in db.exec(q).all():
        if a.audience == "clinic" and not clinic_view:
            continue
        at = a.at if a.at.tzinfo else a.at.replace(tzinfo=__import__("datetime").UTC)
        out.append(
            {"id": a.id, "at": at.isoformat(), "actor": a.actor_name, "kind": a.kind, "text": a.text, "ref": a.ref}
        )
    return out


# ---------------------------------------------------------------- contacts


def find_user(db: DBSession, query: str, phone_hash: str | None) -> User | None:
    q = query.strip().upper()
    if q.startswith("SM-"):
        return db.exec(select(User).where(User.smriti_id == q)).first()
    if phone_hash:
        return db.exec(select(User).where(User.phone_hash == phone_hash)).first()
    return None


def add_contact(db: DBSession, owner: User, other: User, label: str = "") -> dict[str, Any]:
    if other.id == owner.id:
        raise PeopleError("That's you.")
    existing = db.exec(select(Contact).where(Contact.owner_id == owner.id, Contact.contact_user_id == other.id)).first()
    if not existing:
        db.add(Contact(owner_id=owner.id, contact_user_id=other.id, label=label or other.name))
        db.commit()
    return contact_out(db, owner, other)


def contact_out(db: DBSession, owner: User, other: User) -> dict[str, Any]:
    back = db.exec(select(Contact).where(Contact.owner_id == other.id, Contact.contact_user_id == owner.id)).first()
    return {**user_out(other), "mutual": bool(back)}


def contacts(db: DBSession, owner: User) -> list[dict[str, Any]]:
    rows = db.exec(select(Contact).where(Contact.owner_id == owner.id)).all()
    out = []
    for c in rows:
        other = db.get(User, c.contact_user_id) if c.contact_user_id else None
        if other:
            out.append(contact_out(db, owner, other))
    # People who added me but I haven't added back yet
    for c in db.exec(select(Contact).where(Contact.contact_user_id == owner.id)).all():
        other = db.get(User, c.owner_id)
        if other and not any(x["id"] == other.id for x in out):
            out.append({**user_out(other), "mutual": False, "added_you": True})
    return out


# ---------------------------------------------------------------- the family circle


def circle_for(db: DBSession, parent_id: str) -> Circle | None:
    return db.exec(select(Circle).where(Circle.parent_id == parent_id)).first()


def circle_out(db: DBSession, circle: Circle) -> dict[str, Any]:
    members = []
    for m in db.exec(select(CircleMember).where(CircleMember.circle_id == circle.id)).all():
        u = db.get(User, m.user_id)
        if u and m.status != "removed":
            inviter = db.get(User, m.invited_by) if m.invited_by else None
            members.append(
                {
                    **user_out(u),
                    "member_role": m.role,
                    "status": m.status,
                    "member_id": m.id,
                    "invited_by": inviter.name if inviter else None,
                }
            )
    order = {"elder": 0, "family": 1, "clinic": 2}
    members.sort(key=lambda m: (m["status"] != "active", order.get(m["member_role"], 9)))
    return {"id": circle.id, "name": circle.name, "parent_id": circle.parent_id, "members": members}


def invite(db: DBSession, circle: Circle, inviter: User | None, user: User, role: str) -> CircleMember:
    """Family and clinics join only when the elder agrees (on their page or on a call)."""
    if role not in ("family", "clinic"):
        raise PeopleError("Only family members or a care team can be invited.")
    m = db.exec(
        select(CircleMember).where(CircleMember.circle_id == circle.id, CircleMember.user_id == user.id)
    ).first()
    if m and m.status == "active":
        raise PeopleError(f"{user.name} is already in the circle.")
    if m:
        m.status, m.role, m.invited_by, m.decided_at = "pending", role, inviter.id if inviter else None, None
    else:
        m = CircleMember(circle_id=circle.id, user_id=user.id, role=role, invited_by=inviter.id if inviter else None)
    db.add(m)
    db.commit()
    db.refresh(m)
    parent = db.get(Parent, circle.parent_id)
    what = "see results and order checks" if role == "clinic" else "join the family circle"
    log(
        db,
        circle.parent_id,
        f"{inviter.name if inviter else 'Someone'} asked for {user.name} to {what}. "
        f"Waiting for {parent.call_name if parent else 'the elder'} to agree.",
        kind="circle",
        actor=inviter,
    )
    return m


def decide(db: DBSession, member_id: int, elder: Any, accept: bool) -> CircleMember:
    m = db.get(CircleMember, member_id)
    if not m or m.status != "pending":
        raise PeopleError("Nothing to decide here.", 404)
    m.status, m.decided_at = ("active" if accept else "declined"), utcnow()
    db.add(m)
    db.commit()
    circle = db.get(Circle, m.circle_id)
    u = db.get(User, m.user_id)
    who = getattr(elder, "name", "The elder")
    text = f"{who} {'agreed: ' + u.name + ' is now in the circle' if accept else 'said no to ' + u.name}."
    log(db, circle.parent_id, text, kind="circle", actor=elder)
    return m


# ---------------------------------------------------------------- schedules

IST_OFFSET = timedelta(hours=5, minutes=30)


def schedule_out(s: Schedule, db: DBSession) -> dict[str, Any]:
    who = db.get(User, s.created_by) if s.created_by else None
    return {
        "id": s.id,
        "kind": s.kind,
        "label": s.label,
        "days": s.days,
        "time": s.time,
        "questions": s.questions,
        "active": s.active,
        "created_by": who.name if who else None,
        "next_run_at": next_run(s).isoformat() if s.active else None,
        "last_run_at": _aware(s.last_run_at).isoformat() if s.last_run_at else None,
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=__import__("datetime").UTC)


def next_run(s: Schedule, now: datetime | None = None) -> datetime:
    from app.family.service import IST

    now = (now or utcnow()).astimezone(IST)
    hh, mm = (int(x) for x in s.time.split(":"))
    for d in range(0, 8):
        day = now + timedelta(days=d)
        at = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at > now and (not s.days or at.weekday() in s.days):
            return at
    return now + timedelta(days=1)


def due(s: Schedule, now: datetime | None = None) -> bool:
    """Due if today's slot has passed within the last 10 minutes and it hasn't run since that slot."""
    from app.family.service import IST

    now = (now or utcnow()).astimezone(IST)
    hh, mm = (int(x) for x in s.time.split(":"))
    slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if not s.active or (s.days and slot.weekday() not in s.days) or not (slot <= now < slot + timedelta(minutes=10)):
        return False
    return s.last_run_at is None or _aware(s.last_run_at) < slot


# ---------------------------------------------------------------- new parents (live demo) and reset


def create_parent(
    db: DBSession,
    creator: User,
    *,
    full_name: str,
    call_name: str,
    age: int | None,
    city: str,
    language: str,
    relation: str,
    share_level: str,
) -> Parent:
    """A family member adds their parent. The parent gets their own login (elder app) and owns the new circle;
    the creator joins it. In the real product the parent agrees on Smriti's first call; here it is a demo."""
    from app.family.models import ShareLevel

    elder = User(
        name=full_name,
        role="elder",
        smriti_id=new_smriti_id(db, call_name or full_name),
        age=age,
        language=language,
        title=call_name,
        is_demo=True,
    )
    db.add(elder)
    db.commit()
    db.refresh(elder)
    first = creator.name.split()[0]
    parent = Parent(
        full_name=full_name,
        call_name=call_name or full_name.split()[0],
        honorific=full_name.split()[0] + " ji",
        city=city,
        language=language,
        family_name=first,
        relation=relation,
        share_level=share_level if share_level in ShareLevel.ALL_LEVELS else ShareLevel.HEALTH,
        consent_at=utcnow(),
        user_id=elder.id,
        age=age,
        interests=[],
        is_demo=False,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)
    circle = Circle(name=f"{call_name or full_name}'s circle", parent_id=parent.id)
    db.add(circle)
    db.commit()
    db.add(CircleMember(circle_id=circle.id, user_id=elder.id, role="elder", status="active", decided_at=utcnow()))
    db.add(
        CircleMember(
            circle_id=circle.id,
            user_id=creator.id,
            role="family",
            status="active",
            invited_by=elder.id,
            decided_at=utcnow(),
        )
    )
    db.add(Contact(owner_id=creator.id, contact_user_id=elder.id))
    db.add(Contact(owner_id=elder.id, contact_user_id=creator.id))
    db.commit()
    log(
        db,
        parent.id,
        f"{creator.name} added {full_name}. Smriti will speak {_LANG_NAMES.get(language, language)} on calls.",
        kind="circle",
        actor=creator,
    )
    return parent


def create_account(db: DBSession, *, name: str, role: str, relation: str = "", org: str = "") -> User:
    """A new family member or care-team member signs up (no password: this is a demo login)."""
    if role not in ("family", "clinic"):
        raise PeopleError("Only family members and the care team sign up here; elders are added by their family.")
    user = User(name=name, role=role, smriti_id=new_smriti_id(db, name), title=relation, org=org, is_demo=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_parent(db: DBSession, parent: Parent) -> None:
    """Remove one parent's profile with everything about them: calls, flags, notes, visits, schedules, circle,
    history and their elder login."""
    from app.family.models import Appointment, CheckIn, Flag, Note
    from app.models import CallArtifact, Review, Score, Session

    for model in (Flag, Note, Appointment, Schedule, Activity):
        for row in db.exec(select(model).where(model.parent_id == parent.id)).all():
            db.delete(row)
    for c in db.exec(select(CheckIn).where(CheckIn.parent_id == parent.id)).all():
        if c.session_id:
            for model in (Score, CallArtifact, Review):
                for row in db.exec(select(model).where(model.session_id == c.session_id)).all():
                    db.delete(row)
            s = db.get(Session, c.session_id)
            if s:
                db.delete(s)
        db.delete(c)
    for circle in db.exec(select(Circle).where(Circle.parent_id == parent.id)).all():
        for m in db.exec(select(CircleMember).where(CircleMember.circle_id == circle.id)).all():
            db.delete(m)
        db.delete(circle)
    db.commit()
    elder = db.get(User, parent.user_id) if parent.user_id else None
    if elder:
        for c in db.exec(select(Contact)).all():
            if elder.id in (c.owner_id, c.contact_user_id):
                db.delete(c)
        db.commit()
        db.delete(elder)
    db.delete(parent)
    db.commit()


def start_over(db: DBSession) -> int:
    """Delete every profile and every account: the next visitor sees the welcome screens.
    The Bolna connection (if any) is server setup and stays."""
    parents = db.exec(select(Parent)).all()
    for parent in parents:
        delete_parent(db, parent)
    for model in (CircleMember, Circle, Contact, Activity, Schedule, User):
        for row in db.exec(select(model)).all():
            db.delete(row)
    db.commit()
    return len(parents)

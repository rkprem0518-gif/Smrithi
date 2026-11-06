"""Who is asking: a logged-in demo user (signed cookie) or staff (the ADMIN_REVIEW_TOKEN).

Three apps run on three ports of one server (family :8000, elder :8001, clinic :8002 by default), or on one
address under three paths (/ family, /elder/ elder, /care/ care team; see PREFIXES). Browsers share cookies across
ports and paths of the same host, so each app gets its own cookie name: logging in as Ravi in the family app does
not log you in anywhere else.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.api.review import is_reviewer
from app.db import get_db
from app.family.models import Circle, CircleMember, Parent, User
from app.settings import get_settings

APPS = ("family", "elder", "clinic")
PREFIXES = {"family": "family", "elder": "elder", "care": "clinic"}  # /elder/... is the elder app on any port


def app_for_port(port: int | None) -> str:
    s = get_settings()
    if s.one_address:
        return "family"
    return {s.elder_port: "elder", s.clinic_port: "clinic"}.get(port or 0, "family")


def app_for(request: Request) -> str:
    """Which app a request belongs to: its path prefix (set by AppPrefix in main.py), else its port."""
    return request.scope.get("smriti_app") or app_for_port(request.url.port)


def cookie_name(request: Request) -> str:
    return f"smriti_{app_for(request)}_{request.url.port or 0}"


def sign(user_id: str) -> str:
    mac = hmac.new(get_settings().secret_salt.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{mac}"


def unsign(value: str) -> str | None:
    user_id, _, mac = value.rpartition(".")
    return user_id if user_id and hmac.compare_digest(sign(user_id), value) else None


@dataclass
class Principal:
    user: User | None = None
    staff: bool = False
    parent_ids: list[str] = field(default_factory=list)  # parents whose circle this user is active in
    roles: dict[str, str] = field(default_factory=dict)  # parent_id -> role in that circle

    @property
    def name(self) -> str:
        return self.user.name if self.user else "Smriti team"

    @property
    def id(self) -> str | None:
        return self.user.id if self.user else None

    def role_for(self, parent_id: str) -> str:
        return "staff" if self.staff else self.roles.get(parent_id, "")


def load_principal(db: DBSession, user: User | None, staff: bool) -> Principal:
    p = Principal(user=user, staff=staff)
    if staff:
        p.parent_ids = [x.id for x in db.exec(select(Parent)).all()]
        return p
    if user and user.role == "clinic":
        # Smriti's own care team reviews every family's flags: no invitation needed.
        for x in db.exec(select(Parent)).all():
            p.parent_ids.append(x.id)
            p.roles[x.id] = "clinic"
        return p
    if user:
        rows = db.exec(
            select(CircleMember, Circle).where(
                CircleMember.user_id == user.id, CircleMember.status == "active", CircleMember.circle_id == Circle.id
            )
        ).all()
        for member, circle in rows:
            p.parent_ids.append(circle.parent_id)
            p.roles[circle.parent_id] = member.role
    return p


def optional_principal(
    request: Request,
    authorization: str = Header(default=""),
    token: str = Query(default=""),
    db: DBSession = Depends(get_db),
) -> Principal | None:
    if is_reviewer(authorization) or (token and is_reviewer(f"Bearer {token}")):
        return load_principal(db, None, staff=True)
    raw = request.cookies.get(cookie_name(request))
    user_id = unsign(raw) if raw else None
    user = db.get(User, user_id) if user_id else None
    return load_principal(db, user, staff=False) if user else None


def require_principal(principal: Principal | None = Depends(optional_principal)) -> Principal:
    if principal is None:
        raise HTTPException(401, "Please log in")
    return principal


def require_clinic(principal: Principal = Depends(require_principal)) -> Principal:
    if not principal.staff and not (principal.user and principal.user.role == "clinic"):
        raise HTTPException(403, "Only the care team can do this")
    return principal

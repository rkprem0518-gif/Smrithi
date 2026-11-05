"""Tables for the family product. Phone numbers are never stored here either.

Parent      the person Smriti calls (the owner of the account: consent and sharing are theirs)
CheckIn     one knot on the timeline: a weekly chat, a memory check or a call to the family
Flag        something the parent said that a fixed rule picked up, with their own words
Note        what Smriti should remember next time
Appointment a doctor's visit on the family calendar
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models import utcnow


def _id() -> str:
    return uuid.uuid4().hex[:12]


class ShareLevel:
    OKAY_ONLY = "okay_only"  # family only hears "Appa is doing well" (red flags still reach the care desk)
    HEALTH = "health"  # health worries are shared, with the parent's own words
    ALL = "all"  # everything except safety concerns (those only go to the care desk)

    ALL_LEVELS = (OKAY_ONLY, HEALTH, ALL)


class Parent(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    full_name: str
    call_name: str  # what the family calls them: "Appa"
    honorific: str = ""  # how Smriti addresses them: "Raghunath ji"
    city: str = ""
    language: str = "kn"
    family_name: str = "Ravi"  # the family contact's name
    relation: str = "son"  # family contact's relation to the parent
    share_level: str = ShareLevel.HEALTH
    consent_at: datetime | None = None  # the parent agreed on a call
    call_weekday: int = 6  # 0 = Monday ... 6 = Sunday
    call_time: str = "10:30"  # local time, HH:MM
    interests: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    memory_check_every_days: int = 120
    is_demo: bool = False


class CheckIn(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    parent_id: str = Field(foreign_key="parent.id", index=True)
    session_id: str | None = Field(default=None, index=True)  # the Bolna-backed Session, if any
    kind: str = "checkin"  # checkin | memory | family
    at: datetime = Field(default_factory=utcnow, index=True)
    status: str = "done"  # calling | done | missed | invalid
    language: str = "kn"
    duration_s: float | None = None
    mood: str | None = None  # cheerful | okay | low
    summary: str = ""
    topics: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    remembered: str = ""  # the note Smriti brought up from last time
    quotes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))  # [{text, en}]
    message_for_family: str | None = None
    outcome: str | None = None  # memory checks: NORMAL | UNCERTAIN | REFER | INVALID
    is_seed: bool = False


class Flag(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    parent_id: str = Field(foreign_key="parent.id", index=True)
    checkin_id: str = Field(foreign_key="checkin.id", index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    category: str  # pain | sleep | appetite | mood | loneliness | medicines | memory | fall | chest | ...
    level: str  # green | yellow | red
    quote: str
    quote_en: str | None = None
    rule: str  # which fixed rule fired, in plain words
    status: str = "open"  # open | approved | dismissed | noted
    reviewed_at: datetime | None = None
    review_note: str = ""


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    parent_id: str = Field(foreign_key="parent.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    text: str
    used: bool = False  # Smriti already followed up on it


class Appointment(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    parent_id: str = Field(foreign_key="parent.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    title: str
    starts_at: datetime
    minutes: int = 45
    place: str = ""
    status: str = "requested"  # requested | confirmed
    source: str = ""  # who asked: "family call", "family app"

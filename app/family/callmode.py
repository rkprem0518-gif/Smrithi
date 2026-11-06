"""Real calls (spend Bolna credits) or simulated calls, switchable at runtime from any of the three apps.

Off by default: every call button plays a simulated call through the same pipeline (timeline, flags, care
team, live updates) without contacting Bolna. Turning it on makes the next calls real. A server started with
DEMO_MODE=1 has no Bolna keys loaded, so it can never switch to real calls.
"""

from __future__ import annotations

from sqlmodel import Session as DBSession

from app.family.models import AppSetting
from app.models import utcnow
from app.services import events
from app.settings import Settings

KEY = "live_calls"


def available(settings: Settings) -> bool:
    """Real calls are possible only on a live server with Bolna configured."""
    return not settings.demo_mode and settings.bolna_configured


def live(db: DBSession, settings: Settings) -> bool:
    row = db.get(AppSetting, KEY)
    return available(settings) and bool(row and row.value == "1")


def set_live(db: DBSession, settings: Settings, on: bool, by: str) -> bool:
    row = db.get(AppSetting, KEY) or AppSetting(key=KEY)
    row.value, row.updated_at, row.updated_by = ("1" if on else "0"), utcnow(), by
    db.add(row)
    db.commit()
    now = live(db, settings)
    events.bus.publish({"type": "call_mode", "live": now, "by": by})
    return now


def effective(db: DBSession, settings: Settings) -> Settings:
    """The settings a call should use: a simulated call gets a copy with demo_mode on."""
    return settings if live(db, settings) else settings.model_copy(update={"demo_mode": True})

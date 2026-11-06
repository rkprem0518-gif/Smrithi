"""Real calls (spend Bolna credits) or simulated calls, switchable at runtime from any of the three apps.

Off by default: every call button plays a simulated call through the same pipeline (timeline, flags, care
team, live updates) without contacting Bolna. Turning it on makes the next calls real. It can be turned on once
Bolna is connected: keys in .env (DEMO_MODE=0), or an account added from the app (see bolna_link).
"""

from __future__ import annotations

from sqlmodel import Session as DBSession

from app.family import bolna_link
from app.family.models import AppSetting
from app.models import utcnow
from app.services import events
from app.settings import Settings

KEY = "live_calls"


def available(db: DBSession, settings: Settings) -> bool:
    """Real calls are possible once Bolna is connected: keys in .env, or an account added in the app."""
    s = bolna_link.merged(db, settings)
    return not s.demo_mode and s.bolna_configured


def live(db: DBSession, settings: Settings) -> bool:
    row = db.get(AppSetting, KEY)
    return available(db, settings) and bool(row and row.value == "1")


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
    return bolna_link.merged(db, settings) if live(db, settings) else settings.model_copy(update={"demo_mode": True})

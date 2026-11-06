"""Connect a Bolna account from inside the app: paste an API key, Smriti sets up its three voice agents.

A key added in the app (family or care team) is kept on this server and used for every real call, the poller
and the webhook. It takes priority over a key in `.env`; disconnecting it falls back to the `.env` key.
The key is never sent back to a browser; the apps only see its last four characters. Disconnecting deletes it
and switches real calls off.

Connecting places no phone call and spends no call credits: it reads the account (GET /user/me) and creates the
agents (POST /v2/agent).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session as DBSession

from app.db import new_db
from app.family.models import AppSetting
from app.models import utcnow
from app.services import events
from app.settings import Settings

# AppSetting key -> Settings field
FIELDS = {
    "bolna.api_key": "bolna_api_key",
    "bolna.agent.memory": "bolna_agent_id",
    "bolna.agent.checkin": "bolna_agent_id_checkin",
    "bolna.agent.family": "bolna_agent_id_family",
    "bolna.from_number": "bolna_from_number",
}
AGENT_KINDS = ("checkin", "family", "memory")


class LinkError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def from_env(settings: Settings) -> bool:
    """`.env` alone makes this a live server (an app-added key, if any, still takes priority)."""
    return not settings.demo_mode and settings.bolna_configured


def stored(db: DBSession) -> dict[str, str]:
    out = {}
    for key in FIELDS:
        row = db.get(AppSetting, key)
        if row and row.value:
            out[key] = row.value
    return out


def merged(db: DBSession, settings: Settings) -> Settings:
    """These settings with the app-added Bolna account filled in (live), or unchanged."""
    if not settings.allow_app_keys:
        return settings
    vals = stored(db)
    if not vals.get("bolna.api_key"):
        return settings
    update: dict[str, Any] = {FIELDS[k]: v for k, v in vals.items()}
    update["demo_mode"] = False
    update["bolna_multilingual"] = True  # the memory agent made here speaks Hindi, Kannada and English
    return settings.model_copy(update=update)


def current(settings: Settings) -> Settings:
    """`merged` for code that has no database session of its own (poller, webhook)."""
    with new_db() as db:
        return merged(db, settings)


def status(db: DBSession, settings: Settings) -> dict[str, Any]:
    vals = stored(db) if settings.allow_app_keys else {}
    if vals.get("bolna.api_key"):
        key = vals["bolna.api_key"]
        source = "app"
        agents = {kind: bool(vals.get(f"bolna.agent.{kind}")) for kind in AGENT_KINDS}
        number = vals.get("bolna.from_number", "")
    elif from_env(settings):
        key = settings.bolna_api_key
        source = "env"
        agents = {"memory": bool(settings.bolna_agent_id), "checkin": bool(settings.bolna_agent_id_checkin),
                  "family": bool(settings.bolna_agent_id_family)}
        number = settings.bolna_from_number
    else:
        key, source, number = "", "none", ""
        agents = dict.fromkeys(AGENT_KINDS, False)
    return {
        "source": source,
        "connected": all(agents.values()) if source == "app" else source == "env",
        "can_connect": settings.allow_app_keys,
        "env_key": from_env(settings),
        "key_hint": f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else ""),
        "agents": agents,
        "from_number": number,
        "webhook": settings.webhook_reachable,
    }


def _save(db: DBSession, key: str, value: str, by: str) -> None:
    row = db.get(AppSetting, key) or AppSetting(key=key)
    row.value, row.updated_at, row.updated_by = value, utcnow(), by
    db.add(row)


async def connect(
    db: DBSession,
    settings: Settings,
    api_key: str,
    by: str,
    agent_ids: dict[str, str] | None = None,
    from_number: str = "",
    client: Any = None,
) -> dict[str, Any]:
    """Check the key with Bolna, create whichever of the three agents was not given, and store it all."""
    from app.config_loader import agent_prompt, agent_template, scoring_config
    from app.services.agent_builder import build_agent_payload
    from app.services.bolna_client import BolnaAuthError, BolnaClient, BolnaError

    if not settings.allow_app_keys:
        raise LinkError("This server was started offline-only (--offline). Restart it without --offline.", 409)
    if settings.app_env == "production" and settings.default_secrets():
        raise LinkError("Set SECRET_SALT, ADMIN_REVIEW_TOKEN and BOLNA_WEBHOOK_TOKEN on this server first.", 409)
    api_key = api_key.strip()
    if len(api_key) < 8 or any(c.isspace() for c in api_key):
        raise LinkError("That doesn't look like a Bolna API key. Copy it from Bolna's dashboard (Developers).")
    given = {k: (v or "").strip() for k, v in (agent_ids or {}).items() if k in AGENT_KINDS and (v or "").strip()}
    live = settings.model_copy(update={"bolna_api_key": api_key, "demo_mode": False})
    own = client is None
    client = client or BolnaClient.from_settings(live)
    created: dict[str, str] = {}
    try:
        try:
            me = await client.get_user_me()
        except BolnaAuthError as exc:
            raise LinkError("Bolna didn't accept this API key. Check it and try again.") from exc
        for kind in AGENT_KINDS:
            if kind in given:
                continue
            payload = build_agent_payload(live, agent_template(), agent_prompt(kind), scoring_config(),
                                          multilingual=kind == "memory", kind=kind)
            created[kind] = await client.create_agent(payload)
    except BolnaError as exc:
        raise LinkError(f"Bolna said no ({exc.status_code or 'network error'}): {exc}", 502) from exc
    finally:
        if own:
            await client.aclose()
    _save(db, "bolna.api_key", api_key, by)
    for kind, agent_id in {**given, **created}.items():
        _save(db, f"bolna.agent.{kind}", agent_id, by)
    _save(db, "bolna.from_number", from_number.strip(), by)
    db.commit()
    events.bus.publish({"type": "call_mode", "live": False, "by": by, "connected": True})
    from app.services.ops import _parse_account

    wallet = _parse_account(me if isinstance(me, dict) else {})["wallet"]
    return {**status(db, settings), "created": sorted(created), "wallet": wallet}


def disconnect(db: DBSession, settings: Settings, by: str) -> dict[str, Any]:
    for key in (*FIELDS, "live_calls"):
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
    db.commit()
    events.bus.publish({"type": "call_mode", "live": False, "by": by, "connected": False})
    return status(db, settings)

"""Operational view for the demo: Bolna wallet (cached GET /user/me) and cost/latency stats over recent calls."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.logs import log
from app.models import Session, Status, utcnow
from app.services.bolna_client import BolnaClient, BolnaError
from app.settings import Settings

FAILURE_CACHE_SECONDS = 10.0  # retry a failed wallet read sooner than a good one
COMPLETED = (Status.SCORED, Status.INVALID, Status.STOPPED, Status.DECLINED)  # call connected and finished
NOT_CONNECTED = (Status.NO_ANSWER, Status.BUSY, Status.FAILED)
UNITS_NOTE = "Amounts, durations and latencies are in Bolna's own units (cost believed to be US cents; unverified)."

_wallet_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def reset_wallet_cache() -> None:
    _wallet_cache.clear()


def _empty_account(source: str, error: str | None = None) -> dict[str, Any]:
    return {"source": source, "wallet": None, "concurrency": None, "fetched_at": None, "cached": False,
            "error": error}


def _parse_account(me: dict[str, Any]) -> dict[str, Any]:
    wallet: Any = me.get("wallet")
    try:
        wallet = float(wallet)  # may arrive as a string ("0.00")
    except (TypeError, ValueError):
        wallet = None
    conc = me.get("concurrency") if isinstance(me.get("concurrency"), dict) else {}
    return {
        "source": "bolna",
        "wallet": wallet,
        "concurrency": {"max": conc.get("max"), "current": conc.get("current")} if conc else None,
        "fetched_at": utcnow().isoformat(),
        "cached": False,
        "error": None,
    }


async def bolna_account(settings: Settings, client: BolnaClient | None = None) -> dict[str, Any]:
    """Wallet balance and concurrency from GET /user/me, cached for OPS_CACHE_SECONDS.
    Never raises: on any problem the fields are null and `error` says why."""
    if settings.demo_mode:
        return _empty_account("demo", "DEMO_MODE: Bolna is not contacted.")
    if not settings.bolna_api_key:
        return _empty_account("unavailable", "BOLNA_API_KEY is not set.")
    key = hashlib.sha256(f"{settings.bolna_api_base}|{settings.bolna_api_key}".encode()).hexdigest()
    cached = _wallet_cache.get(key)
    now = time.monotonic()
    if cached and now < cached[0]:
        return {**cached[1], "cached": True}
    try:
        if client is None:
            async with BolnaClient.from_settings(settings) as own:
                me = await own.get_user_me()
        else:
            me = await client.get_user_me()
        account = _parse_account(me if isinstance(me, dict) else {})
        ttl = settings.ops_cache_seconds
    except BolnaError as exc:
        log("ops_wallet_failed", status_code=exc.status_code)
        account = _empty_account("unavailable", f"Bolna /user/me failed ({exc.status_code or 'network'}).")
        ttl = min(FAILURE_CACHE_SECONDS, settings.ops_cache_seconds)
    _wallet_cache[key] = (now + ttl, account)
    return account


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def session_stats(db: DBSession, settings: Settings, limit: int = 50) -> dict[str, Any]:
    """Counts and cost/latency averages over the `limit` most recent real (non-sample) sessions.
    Live mode ignores DEMO_MODE's simulated numbers; demo mode uses them (and says so)."""
    sessions = db.exec(
        select(Session)
        .where(Session.deleted_at.is_(None), Session.is_demo == False)  # type: ignore[union-attr]  # noqa: E712
        .order_by(Session.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    use = [s for s in sessions if settings.demo_mode or not s.ops_simulated]
    by_status: dict[str, int] = {}
    for s in sessions:
        by_status[s.status] = by_status.get(s.status, 0) + 1
    costs = [s.total_cost for s in use if s.total_cost is not None]
    durations = [s.call_duration for s in use if s.call_duration is not None]
    ttfa = [s.time_to_first_audio for s in use if s.time_to_first_audio is not None]
    return {
        "window": limit,
        "count": len(sessions),
        "completed": sum(s.status in COMPLETED for s in sessions),
        "not_connected": sum(s.status in NOT_CONNECTED for s in sessions),
        "in_flight": sum(s.status not in Status.FINAL for s in sessions),
        "by_status": by_status,
        "with_ops_data": sum(s.ops_updated_at is not None for s in use),
        "simulated_ops": sum(bool(s.ops_simulated) for s in sessions),
        "avg_call_duration": _avg(durations),
        "avg_cost": _avg(costs),
        "total_cost": round(sum(costs), 3) if costs else None,
        "avg_time_to_first_audio": _avg(ttfa),
        "recent": [
            {"session_id": s.id, "created_at": s.created_at, "status": s.status, "total_cost": s.total_cost,
             "call_duration": s.call_duration, "time_to_first_audio": s.time_to_first_audio,
             "hangup_by": s.hangup_by, "hangup_reason": s.hangup_reason, "simulated": bool(s.ops_simulated)}
            for s in sessions[:10]
        ],
    }

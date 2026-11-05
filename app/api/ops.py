from fastapi import APIRouter, Depends, Query
from sqlmodel import Session as DBSession

from app.api.review import require_reviewer
from app.db import get_db
from app.services import ops
from app.settings import get_settings

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/summary", dependencies=[Depends(require_reviewer)])
async def ops_summary(limit: int = Query(default=50, ge=1, le=500), db: DBSession = Depends(get_db)) -> dict:
    """Bolna wallet + cost/latency stats for the demo's "behind the call" view (reviewer token)."""
    settings = get_settings()
    return {
        "mode": "demo" if settings.demo_mode else "live",
        "simulated": settings.demo_mode,
        "bolna": await ops.bolna_account(settings),
        "sessions": ops.session_stats(db, settings, limit),
        "units_note": ops.UNITS_NOTE,
    }

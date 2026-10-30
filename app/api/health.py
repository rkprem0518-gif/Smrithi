from fastapi import APIRouter

from app.scoring.engine import SCORER_VERSION
from app.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {
        "ok": True,
        "demo_mode": s.demo_mode,
        "bolna_configured": s.bolna_configured,
        "webhook_reachable": s.webhook_reachable,
        "scorer_version": SCORER_VERSION,
    }

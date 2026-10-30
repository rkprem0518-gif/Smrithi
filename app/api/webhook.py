import hmac
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.db import get_db
from app.logs import log
from app.models import Session
from app.services.bolna_client import BolnaError
from app.services.orchestrator import refresh_from_bolna
from app.settings import get_settings

router = APIRouter(tags=["webhook"])


async def _refresh(session_id: str) -> None:
    try:
        await refresh_from_bolna(session_id, get_settings())
    except BolnaError as exc:
        log("webhook_refresh_failed", session_id=session_id, status_code=exc.status_code)


@router.post("/api/bolna/webhook", status_code=204)
async def bolna_webhook(
    request: Request, background: BackgroundTasks, token: str = "", db: DBSession = Depends(get_db)
) -> Response:
    settings = get_settings()
    if not hmac.compare_digest(token.encode(), settings.bolna_webhook_token.encode()):
        raise HTTPException(401, "bad token")
    try:
        body: Any = await request.json()
    except ValueError:
        body = {}
    execution_id = (body.get("id") or body.get("execution_id")) if isinstance(body, dict) else None
    session = None
    if execution_id:
        session = db.exec(select(Session).where(Session.execution_id == str(execution_id))).first()
    if session is None and isinstance(body, dict):
        # Web calls: our session id travels in user_data (TODO(bolna): confirm where it is echoed back).
        sid = ((body.get("context_details") or {}).get("recipient_data") or {}).get("session_id")
        session = db.get(Session, sid) if sid else None
        if session and execution_id and not session.execution_id:
            session.execution_id = str(execution_id)
            db.add(session)
            db.commit()
    log("webhook_received", execution_id=execution_id, matched=bool(session),
        bolna_status=body.get("status") if isinstance(body, dict) else None)
    if session and not settings.demo_mode:
        # Never trust the webhook body alone: re-fetch the execution from Bolna.
        background.add_task(_refresh, session.id)
    return Response(status_code=204)

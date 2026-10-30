from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.db import get_db
from app.models import Score, Session
from app.schemas import SessionCreate, SessionCreated, SessionOut
from app.services import orchestrator
from app.settings import get_settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_live(db: DBSession, session_id: str) -> Session:
    session = db.get(Session, session_id)
    if not session or session.deleted_at:
        raise HTTPException(404, "Session not found")
    return session


@router.post("", status_code=201, response_model=SessionCreated)
async def create_session(body: SessionCreate, request: Request, db: DBSession = Depends(get_db)) -> SessionCreated:
    settings = get_settings()
    try:
        session, web_call = await orchestrator.create_session(
            db, consent=body.consent, language=body.language, mode=body.mode,
            schooling_years=body.schooling_years, phone=body.phone, client_ip=client_ip(request),
            settings=settings, demo_fixture=body.demo_fixture,
        )
    except orchestrator.SessionError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return SessionCreated(session_id=session.id, status=session.status, demo=settings.demo_mode, web_call=web_call)


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: DBSession = Depends(get_db)) -> SessionOut:
    session = _get_live(db, session_id)
    score = db.exec(select(Score).where(Score.session_id == session.id)).first()
    return SessionOut(
        session_id=session.id, status=session.status, review_status=session.review_status,
        mode=session.mode, language=session.language, created_at=session.created_at, is_demo=session.is_demo,
        outcome=score.outcome if score else None, report=score.report_json if score else None,
        error=session.error,
    )


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: DBSession = Depends(get_db)) -> Response:
    orchestrator.delete_session_data(db, _get_live(db, session_id))
    return Response(status_code=204)

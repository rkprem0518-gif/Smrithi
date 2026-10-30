import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.db import get_db
from app.models import CallArtifact, Review, ReviewStatus, Score, Session
from app.schemas import ReviewDecision
from app.settings import get_settings

router = APIRouter(prefix="/api/review", tags=["review"])


def require_reviewer(authorization: str = Header(default="")) -> None:
    settings = get_settings()
    token = settings.admin_review_token
    if settings.app_env == "production" and token in ("", "change-me"):
        raise HTTPException(503, "Set ADMIN_REVIEW_TOKEN before using the reviewer queue in production.")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "Reviewer token required", headers={"WWW-Authenticate": "Bearer"})


@router.get("", dependencies=[Depends(require_reviewer)])
def review_queue(status: str = "pending", db: DBSession = Depends(get_db)) -> dict:
    query = select(Session).where(Session.deleted_at.is_(None))  # type: ignore[union-attr]
    if status == "pending":
        query = query.where(Session.review_status == ReviewStatus.PENDING)
    else:
        query = query.where(Session.review_status != ReviewStatus.NOT_NEEDED)
    items = []
    for session in db.exec(query.order_by(Session.created_at.desc())).all():  # type: ignore[attr-defined]
        score = db.exec(select(Score).where(Score.session_id == session.id)).first()
        artifact = db.exec(select(CallArtifact).where(CallArtifact.session_id == session.id)).first()
        reviews = db.exec(select(Review).where(Review.session_id == session.id)).all()
        items.append({
            "session_id": session.id,
            "created_at": session.created_at,
            "status": session.status,
            "review_status": session.review_status,
            "is_demo": session.is_demo,
            "language": session.language,
            "outcome": score.outcome if score else None,
            "rule_fired": score.rule_fired if score else None,
            "report": score.report_json if score else None,
            "transcript": artifact.transcript_json if artifact else [],
            "recording_url": artifact.recording_url if artifact else None,
            "reviews": [r.model_dump() for r in reviews],
        })
    return {"items": items, "count": len(items)}


@router.post("/{session_id}", status_code=201, dependencies=[Depends(require_reviewer)])
def submit_review(session_id: str, body: ReviewDecision, db: DBSession = Depends(get_db)) -> dict:
    session = db.get(Session, session_id)
    if not session or session.deleted_at:
        raise HTTPException(404, "Session not found")
    review = Review(session_id=session_id, reviewer=body.reviewer, decision=body.decision, note=body.note)
    session.review_status = ReviewStatus.REVIEWED
    db.add(review)
    db.add(session)
    db.commit()
    db.refresh(review)
    return {"review_id": review.id, "session_id": session_id, "review_status": session.review_status}

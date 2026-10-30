from datetime import UTC, datetime

from fastapi import APIRouter

from app.config_loader import markers, scoring_config
from app.schemas import DemoScoreRequest
from app.scoring.engine import score_session
from app.scoring.types import ScoringContext
from app.services.report import build_report
from app.services.segmenter import parse_bolna_transcript, segment, turns_from_json
from app.settings import get_settings

router = APIRouter(tags=["demo"])


@router.post("/api/demo/score")
def demo_score(body: DemoScoreRequest) -> dict:
    """Score any transcript with the real engine. No database, no external calls, any mode."""
    if isinstance(body.transcript, str):
        turns = parse_bolna_transcript(body.transcript)
    else:
        turns = turns_from_json([t.model_dump() for t in body.transcript])
    call_time = body.call_time or datetime.now(UTC)
    if call_time.tzinfo is None:
        call_time = call_time.replace(tzinfo=UTC)
    cfg = scoring_config()
    seg = segment(turns, markers())
    ctx = ScoringContext(call_time=call_time, language=body.language, word_form=body.word_form,
                         schooling_years=body.schooling_years)
    result = score_session(seg, ctx, cfg).to_dict()
    return {
        "result": result,
        "report": build_report(result, cfg, word_form=body.word_form, language=body.language,
                               helpline_text=get_settings().helpline_text, call_time=call_time.isoformat()),
        "declined": seg.declined,
        "stopped": seg.stopped,
    }

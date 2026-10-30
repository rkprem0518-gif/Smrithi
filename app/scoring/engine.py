"""score_session: segmented transcript + context + config -> ScoreResult. No I/O."""

from __future__ import annotations

from app.scoring import tasks
from app.scoring.outcome import decide_outcome
from app.scoring.types import ScoreResult, ScoringConfig, ScoringContext, Segments

SCORER_VERSION = "0.1.0-pilot"


def _empty_answers(
    hearing: dict, schooling_answered: bool, learning: dict, fluency: dict,
    orientation: dict, recall: dict,
) -> dict:
    """Count expected answers that were empty or unintelligible (14 slots in total)."""
    slots = {
        "hearing": [i["answered"] for i in hearing["items"]],
        "schooling": [schooling_answered],
        "learning": list(learning["answered"]),
        "fluency": [fluency["answered"]],
        "orientation": [i < orientation["answered_turns"] for i in range(orientation["max"])],
        "delayed_recall": [recall["answered"]],
    }
    total = sum(len(v) for v in slots.values())
    empty = sum(not a for v in slots.values() for a in v)
    return {
        "expected": total,
        "empty": empty,
        "fraction": round(empty / total, 3) if total else 1.0,
        "by_task": {k: sum(not a for a in v) for k, v in slots.items()},
    }


def score_session(segments: Segments, ctx: ScoringContext, cfg: ScoringConfig) -> ScoreResult:
    form = ctx.word_form
    if form not in cfg.forms:
        raise ValueError(f"unknown word form {form!r}")

    hearing = tasks.score_hearing(segments.turns("hearing"), cfg)

    spoken_years = tasks.parse_schooling_years(segments.turns("schooling"), cfg)
    if ctx.schooling_years is not None:
        years, source = ctx.schooling_years, "ui"
    elif spoken_years is not None:
        years, source = spoken_years, "call"
    else:
        years, source = None, "assumed"
    band, _ = tasks.schooling_band(years, cfg)
    schooling_answered = any(
        tasks.has_content(t.text) for t in tasks.user_turns(segments.turns("schooling"))
    ) or ctx.schooling_years is not None

    learning = tasks.score_learning(segments.turns("learning"), form, cfg)
    fluency = tasks.score_fluency(segments.turns("fluency"), cfg, ctx.fluency_timestamps)
    orientation = tasks.score_orientation(segments.turns("orientation"), ctx.call_time, cfg)
    recall = tasks.score_recall(segments.turns("recall"), form, cfg)
    helper = tasks.detect_helper(segments.turns("close"), cfg)
    consent = tasks.detect_consent(segments.preamble, cfg)
    empty = _empty_answers(hearing, schooling_answered, learning, fluency, orientation, recall)

    invalid: list[str] = []
    if segments.stopped:
        invalid.append("stopped_distress")
    if not hearing["passed"]:
        invalid.append("hearing_check_failed")
    if "recall" not in segments.tasks or not recall["reached"]:
        invalid.append("ended_before_delayed_recall")
    if empty["fraction"] > float(cfg.raw["invalid"]["max_empty_answer_fraction"]):
        invalid.append("too_many_empty_answers")
    if helper and cfg.raw["invalid"]["helper_present_is_invalid"]:
        invalid.append("helper_present")

    outcome, rule = decide_outcome(
        band, recall["score"], fluency["count"], orientation["score"], invalid, cfg.raw
    )
    all_turns = segments.preamble + [t for name in segments.tasks for t in segments.tasks[name]]
    return ScoreResult(
        scorer_version=SCORER_VERSION,
        outcome=outcome,
        rule_fired=rule,
        band=band,
        band_source=source,
        schooling_years=years,
        consent_call=consent,
        hearing=hearing,
        learning=learning,
        fluency=fluency,
        orientation=orientation,
        delayed_recall=recall,
        helper_present=helper,
        invalid_reasons=invalid,
        empty_answers=empty,
        speech_markers=tasks.speech_markers(all_turns, cfg),
        segments_found=list(segments.tasks),
    )

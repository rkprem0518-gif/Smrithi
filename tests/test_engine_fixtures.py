from dataclasses import replace
from datetime import datetime

import pytest

from app.config_loader import FIXTURE_NAMES, load_fixture, markers
from app.scoring.engine import SCORER_VERSION, score_session
from app.scoring.types import ScoringContext, Segments, Turn
from app.services.segmenter import parse_bolna_transcript, segment, turns_from_json, turns_to_bolna_transcript


def _score(fx: dict, turns: list[Turn] | None = None, **ctx_overrides):
    turns = turns if turns is not None else turns_from_json(fx["transcript"])
    ctx = ScoringContext(
        call_time=datetime.fromisoformat(fx["call_started_at"]),
        language=fx["language"],
        word_form=fx["word_form"],
        schooling_years=fx["schooling_years"],
    )
    return score_session(segment(turns, markers()), replace(ctx, **ctx_overrides), _cfg())


def _cfg():
    from app.config_loader import scoring_config

    return scoring_config()


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_scores_match_expected(name: str) -> None:
    fx = load_fixture(name)
    res = _score(fx)
    exp = fx["expected"]
    assert res.outcome == exp["outcome"], res.rule_fired
    assert res.band == exp["band"]
    assert res.hearing["correct"] == exp["hearing_correct"]
    assert res.learning["trial_scores"] == exp["learning_trial_scores"]
    assert res.learning["total"] == exp["learning_total"]
    assert res.fluency["count"] == exp["fluency_count"]
    assert res.orientation["score"] == exp["orientation_score"]
    assert res.delayed_recall["score"] == exp["delayed_recall"]
    assert res.invalid_reasons == exp["invalid_reasons"]
    assert res.scorer_version == SCORER_VERSION
    assert res.rule_fired


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_round_trips_through_bolna_transcript_string(name: str) -> None:
    fx = load_fixture(name)
    turns = turns_from_json(fx["transcript"])
    reparsed = parse_bolna_transcript(turns_to_bolna_transcript(turns))
    assert reparsed == turns
    assert _score(fx, reparsed).outcome == fx["expected"]["outcome"]


def test_every_fixture_finds_all_task_segments() -> None:
    for name in FIXTURE_NAMES:
        seg = segment(turns_from_json(load_fixture(name)["transcript"]), markers())
        assert list(seg.tasks) == ["hearing", "schooling", "learning", "fluency", "orientation", "recall", "close"]


def test_scoring_is_deterministic() -> None:
    fx = load_fixture("uncertain")
    assert _score(fx).to_dict() == _score(fx).to_dict()


def test_ui_schooling_overrides_spoken_answer() -> None:
    fx = load_fixture("refer")  # spoken: 12 years -> HIGH
    res = _score(fx, schooling_years=4)
    assert res.band == "LOW" and res.band_source == "ui"


# ---------------------------------------------------------------- INVALID rules

def test_invalid_when_call_ends_before_delayed_recall() -> None:
    fx = load_fixture("normal")
    turns = turns_from_json(fx["transcript"])
    cut = next(i for i, t in enumerate(turns) if "छठा काम" in t.text)
    res = _score(fx, turns[:cut])
    assert res.outcome == "INVALID" and "ended_before_delayed_recall" in res.invalid_reasons


def test_invalid_when_recall_marker_said_but_no_answer() -> None:
    fx = load_fixture("normal")
    turns = turns_from_json(fx["transcript"])
    cut = next(i for i, t in enumerate(turns) if "छठा काम" in t.text)
    res = _score(fx, turns[: cut + 1])
    assert "ended_before_delayed_recall" in res.invalid_reasons


def test_invalid_when_too_many_answers_empty() -> None:
    fx = load_fixture("normal")
    turns = [
        Turn(t.role, "[inaudible]") if t.role == "user" and i > 20 else t
        for i, t in enumerate(turns_from_json(fx["transcript"]))
    ]
    res = _score(fx, turns)
    assert "too_many_empty_answers" in res.invalid_reasons
    assert res.empty_answers["fraction"] > 0.30


def test_invalid_when_helper_present() -> None:
    fx = load_fixture("normal")
    turns = turns_from_json(fx["transcript"])
    turns[-2] = Turn("user", "हाँ, मेरा बेटा बता रहा था।")
    res = _score(fx, turns)
    assert res.outcome == "INVALID" and res.invalid_reasons == ["helper_present"]


def test_invalid_hearing_fixture() -> None:
    res = _score(load_fixture("invalid_hearing"))
    assert res.invalid_reasons == ["hearing_check_failed"]
    assert res.delayed_recall["score"] == 5  # evidence still recorded


def test_stopped_call_is_invalid() -> None:
    fx = load_fixture("normal")
    turns = turns_from_json(fx["transcript"])[:12] + [
        Turn("user", "मुझे डर लग रहा है, बंद करो"),
        Turn("agent", "हम यहीं रुकते हैं। कोई बात नहीं, आपने बहुत अच्छा किया।"),
    ]
    res = _score(fx, turns)
    assert res.outcome == "INVALID" and "stopped_distress" in res.invalid_reasons


def test_declined_consent_is_detected_by_segmenter() -> None:
    turns = [Turn("agent", "क्या यह ठीक है?"), Turn("user", "नहीं"),
             Turn("agent", "कोई बात नहीं, आज जाँच नहीं करेंगे। धन्यवाद।")]
    seg = segment(turns, markers())
    assert seg.declined and not seg.tasks


def test_english_markers_and_answers() -> None:
    fx = load_fixture("normal")
    turns = [
        Turn("agent", "Is it okay if we talk for about 5 minutes?"), Turn("user", "yes okay"),
        Turn("agent", "Task one. Please repeat: 4 7 2"), Turn("user", "four seven two"),
        Turn("agent", "3 9 5"), Turn("user", "three nine five"), Turn("agent", "8 1 6"), Turn("user", "8 1 6"),
        Turn("agent", "Task two. How many years did you study in school?"), Turn("user", "twelve years"),
        Turn("agent", "Task three. house water tree bread book key door moon chair flower. Tell me."),
        Turn("user", "house water tree"),
        Turn("agent", "house water tree bread book key door moon chair flower"), Turn("user", "house water tree book"),
        Turn("agent", "house water tree bread book key door moon chair flower"), Turn("user", "house water tree book key"),
        Turn("agent", "Task four. Name animals."), Turn("user", "dog cat cow horse lion tiger elephant monkey parrot crow fish"),
        Turn("agent", "Task five. What day is it?"), Turn("user", "Wednesday"),
        Turn("agent", "Which month?"), Turn("user", "October"), Turn("agent", "Season?"), Turn("user", "winter"),
        Turn("agent", "Morning or evening?"), Turn("user", "morning"),
        Turn("agent", "What is the name of your town or village?"), Turn("user", "Pune"),
        Turn("agent", "Task six. Which words do you remember?"), Turn("user", "house water tree book key"),
        Turn("agent", "Last question: was anyone helping you answer?"), Turn("user", "no"),
    ]
    res = _score(fx, turns, language="en")
    assert res.band == "HIGH"
    assert res.learning["trial_scores"] == [3, 4, 5]
    assert res.fluency["count"] == 11
    assert res.orientation["score"] == 5
    assert res.delayed_recall["score"] == 5
    assert res.outcome == "NORMAL", res.rule_fired


def test_empty_transcript_is_invalid_not_a_crash() -> None:
    res = _score(load_fixture("normal"), [])
    assert res.outcome == "INVALID"
    assert isinstance(Segments(), Segments)

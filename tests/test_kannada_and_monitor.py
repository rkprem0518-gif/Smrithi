"""Kannada support, plus regressions found by the monitor agent (30 Oct 2026)."""

import pytest

from app.config_loader import agent_prompt, agent_template, markers
from app.scoring import tasks
from app.scoring.matching import find_matches
from app.scoring.normalize import normalize_text, tokenize
from app.services.agent_builder import build_agent_payload
from app.services.orchestrator import word_list_for
from app.services.segmenter import segment
from app.settings import Settings
from tests.conftest import agent, user


def words(text, lexicon, cfg):
    return [m.canonical for m in find_matches(tokenize(text), lexicon, cfg.threshold, cfg.stopwords)[0]]


# ---------------------------------------------------------------- Kannada
@pytest.mark.parametrize(("text", "canonical"), [("ಮನೆ", "ghar"), ("ನೀರು", "paani"), ("ಮರಗಳು", "ped"), ("ಹೂವು", "phool")])
def test_kannada_list_words(cfg, text, canonical) -> None:
    assert words(text, cfg.form_lexicons["A"], cfg) == [canonical]


def test_kannada_animals_and_plurals(cfg) -> None:
    assert words("ನಾಯಿ ಬೆಕ್ಕು ಹಸು ನಾಯಿಗಳು ಆನೆ", cfg.animal_lexicon, cfg) == ["dog", "cat", "cow", "dog", "elephant"]


def test_kannada_tokens_do_not_match_devanagari_keys(cfg) -> None:
    # Same Latin key, different script pools: Kannada text only matches Kannada spellings.
    assert normalize_text("ನದಿ") == normalize_text("नदी")
    assert words("ನದಿ", cfg.form_lexicons["B"], cfg) == ["nadi"]


def test_kannada_digits_schooling_yes_no(cfg) -> None:
    assert tasks.digit_sequence("ನಾಲ್ಕು ಏಳು ಎರಡು") == "472"
    assert tasks.parse_schooling_years([user("ಎಸ್ಎಸ್ಎಲ್ಸಿ ತನಕ ಓದಿದ್ದೀನಿ")], cfg) == 10
    assert tasks.parse_schooling_years([user("ಪಿಯುಸಿ")], cfg) == 12
    assert tasks.parse_yes_no("ಇಲ್ಲ, ನಾನೊಬ್ಬಳೇ", cfg) is False
    assert tasks.parse_yes_no("ಹೌದು, ಸರಿ", cfg) is True


def test_kannada_markers_do_not_collide() -> None:
    seg = segment([agent("ಮೊದಲನೇ ಕೆಲಸ"), agent("ಎರಡನೇ ಕೆಲಸ. ಎಷ್ಟು ವರ್ಷ ಓದಿದ್ದೀರಿ?"), user("ಹತ್ತು")], markers())
    assert list(seg.tasks) == ["hearing", "schooling"]


def test_kannada_word_list_and_agent_variant() -> None:
    assert word_list_for("A", "kn").startswith("ಮನೆ, ನೀರು")
    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), language="kn")
    task = payload["agent_config"]["tasks"][0]["tools_config"]
    assert task["transcriber"]["language"] == "kn"
    assert task["synthesizer"]["provider_config"]["language"] == "kn"
    assert "language_variants" not in str(payload)
    assert "ಮೊದಲನೇ ಕೆಲಸ" in agent_prompt()


def test_kannada_needs_its_own_agent_id() -> None:
    s = Settings(_env_file=None, bolna_agent_id="hi-agent", bolna_agent_id_kn="kn-agent")
    assert s.agent_id_for("kn") == "kn-agent" and s.agent_id_for("en") == "hi-agent"


# ---------------------------------------------------------------- monitor regressions
@pytest.mark.parametrize("answer", ["ना जी", "नई जी", "नो जी", "na ji", "नहीं जी"])
def test_polite_no_is_no(cfg, answer) -> None:
    turns = [agent("आख़िरी सवाल: क्या कोई आपको जवाब बताने में मदद कर रहा था?"), user(answer)]
    assert tasks.detect_helper(turns, cfg) is False


def test_english_plurals_in_latin(cfg) -> None:
    assert words("dogs cats", cfg.animal_lexicon, cfg) == ["dog", "cat"]
    assert words("trees books keys", cfg.form_lexicons["A"], cfg) == ["ped", "kitaab", "chaabi"]


def test_silent_recall_then_close_is_reached(cfg) -> None:
    from datetime import datetime

    from app.config_loader import scoring_config
    from app.scoring.engine import score_session
    from app.scoring.types import ScoringContext, Segments, Turn

    seg = Segments(tasks={"recall": [Turn("agent", "छठा काम। कौन से शब्द याद हैं?")],
                          "close": [Turn("agent", "आख़िरी सवाल: ..."), Turn("user", "नहीं")]})
    res = score_session(seg, ScoringContext(call_time=datetime.fromisoformat("2026-10-28T10:00:00+05:30")),
                        scoring_config())
    assert "ended_before_delayed_recall" not in res.invalid_reasons

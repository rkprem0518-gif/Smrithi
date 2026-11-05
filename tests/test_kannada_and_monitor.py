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


def test_ui_languages_have_the_same_keys() -> None:
    import json
    from pathlib import Path

    folder = Path(__file__).resolve().parent.parent / "app" / "web" / "i18n"
    keys = {p.stem: set(json.loads(p.read_text(encoding="utf-8"))) for p in folder.glob("*.json")}
    assert set(keys) == {"en", "hi", "kn"}
    assert keys["en"] == keys["hi"] == keys["kn"]


def test_report_has_kannada_text(cfg) -> None:
    from app.services import report

    for table in (report.OUTCOME_LABEL, report.NEXT_STEP, report.INVALID_REASONS):
        assert all("kn" in v for v in table.values())


# ---------------------------------------------------------------- first live call (5 Nov 2026)
@pytest.mark.parametrize(
    ("answer", "years"),
    [("सेकंड ईयर में पढ़ रहा हूं", 14), ("second year BA", 14), ("फर्स्ट ईयर", 13), ("ಸೆಕೆಂಡ್ ಇಯರ್", 14),
     ("दूसरी कक्षा", 2)],
)
def test_college_year_answers(cfg, answer, years) -> None:
    assert tasks.parse_schooling_years([user(answer)], cfg) == years


def test_hippo_heard_as_happy(cfg) -> None:
    assert words("हैप्पी हिप्पो", cfg.animal_lexicon, cfg) == ["hippopotamus", "hippopotamus"]


def test_kannada_paravagilla_is_yes(cfg) -> None:
    assert tasks.parse_yes_no("ಪರವಾಗಿಲ್ಲ", cfg) is True


def test_online_check_speaks_the_call_language_and_welcome_asks_a_question() -> None:
    messages = set()
    for lang in ("hi", "kn", "en"):
        payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), language=lang)
        tc = payload["agent_config"]["tasks"][0]["task_config"]
        assert tc["check_if_user_online"] is True
        assert "still there" not in tc["check_user_online_message"]
        assert tc["hangup_after_silence"] >= 40
        messages.add(tc["check_user_online_message"])
        assert payload["agent_config"]["agent_welcome_message"].rstrip().endswith("?")
    assert len(messages) == 3  # one per language


def test_english_agent_variant_and_fallback() -> None:
    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), language="en")
    tools = payload["agent_config"]["tasks"][0]["tools_config"]
    assert tools["transcriber"]["language"] == "en" and tools["synthesizer"]["provider_config"]["language"] == "en"
    assert Settings(_env_file=None, bolna_agent_id="hi-1").agent_id_for("en") == "hi-1"
    assert Settings(_env_file=None, bolna_agent_id="hi-1", bolna_agent_id_en="en-1").agent_id_for("en") == "en-1"


def test_prompt_has_every_line_in_all_three_languages() -> None:
    prompt = agent_prompt()
    assert prompt.count("- KN:") >= 9 and prompt.count("- HI:") >= 9 and prompt.count("- EN:") >= 9


# ---------------------------------------------------------------- second live call (Kannada, noisy, 5 Nov 2026)
def test_agent_hangs_up_after_goodbye() -> None:
    for lang in ("hi", "kn", "en"):
        payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), language=lang)
        tc = payload["agent_config"]["tasks"][0]["task_config"]
        assert tc["hangup_after_LLMCall"] is True
        assert "goodbye" in tc["call_cancellation_prompt"]


def test_prompt_keeps_digit_strings_in_separate_messages() -> None:
    prompt = agent_prompt()
    assert "NEVER put two digit strings" in prompt
    assert "say nothing more" in prompt


# ---------------------------------------------------------------- Hinglish / Kanglish and language choice
@pytest.mark.parametrize(
    ("form", "text", "canonical"),
    [("A", "ಹೌಸ್", "ghar"), ("A", "ವಾಟರ್", "paani"), ("C", "ಬಾಕ್ಸ್", "dibba"), ("B", "ಮ್ಯಾಂಗೋ", "aam"), ("A", "हाउस", "ghar")],
)
def test_english_words_in_indic_script(cfg, form, text, canonical) -> None:
    assert words(text, cfg.form_lexicons[form], cfg) == [canonical]


def test_kanglish_and_hinglish_animals_days_digits(cfg) -> None:
    assert words("ಡಾಗ್ ಕ್ಯಾಟ್ ಲಯನ್ ಟೈಗರ್ ನಾಯಿ", cfg.animal_lexicon, cfg) == ["dog", "cat", "lion", "tiger", "dog"]
    assert tasks.digit_sequence("फोर सेवन टू") == "472"
    assert tasks.digit_sequence("ಫೋರ್ ಸೆವೆನ್ ಟೂ") == "472"
    assert words("थर्सडे", cfg.day_lexicon, cfg) == ["3"]
    assert words("ಥರ್ಸ್‌ಡೇ", cfg.day_lexicon, cfg) == ["3"]
    assert tasks.parse_yes_no("ಯೆಸ್", cfg) is True


def test_multilingual_agent_payload() -> None:
    payload = build_agent_payload(Settings(_env_file=None), agent_template(), agent_prompt(), multilingual=True)
    tools = payload["agent_config"]["tasks"][0]["tools_config"]
    ml = tools["multilingual_config"]
    assert ml["enabled"] is True and ml["active_language"] == "en"
    assert payload["agent_config"]["agent_welcome_message"].startswith("Hello!")
    assert set(ml["languages"]) == {"hi", "kn", "en"}
    for lang, entry in ml["languages"].items():
        assert entry["transcriber"]["language"] == lang
        assert entry["synthesizer"]["provider"] == "sarvam"
        assert entry["synthesizer"]["provider_config"]["language"] == lang
        assert entry["welcome_message"].rstrip().endswith("?")
    assert payload["agent_config"]["tasks"][0]["task_config"]["noise_cancellation_level"] == 85


def test_multilingual_user_data_and_agent_choice() -> None:
    from app.models import Session as Sess
    from app.services.orchestrator import build_user_data

    s = Sess(word_form="A", language="kn")
    data = build_user_data(s, multilingual=True)
    assert data["agent_language"] == "en" and data["language"] == "kn"  # opens in English; kn is the hint
    assert data["word_list_kn"].startswith("ಮನೆ") and data["word_list_hi"].startswith("घर")
    assert "agent_language" not in build_user_data(s)
    st = Settings(_env_file=None, bolna_agent_id="multi", bolna_agent_id_kn="kn-1", bolna_multilingual=True)
    assert st.agent_id_for("kn") == "multi"

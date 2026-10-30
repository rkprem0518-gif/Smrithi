"""Regression tests for bugs found by the adversarial scoring review (30 Oct 2026)."""

from datetime import datetime

import pytest

from app.config_loader import markers
from app.scoring import tasks
from app.scoring.matching import find_matches
from app.scoring.normalize import tokenize
from app.services.segmenter import parse_bolna_transcript, segment
from tests.conftest import agent, user

READ_A = "घर... पानी... पेड़... रोटी... किताब... चाबी... दरवाज़ा... चाँद... कुर्सी... फूल।"
READ_C = "दीया... रस्सी... छाता... पत्ता... बाज़ार... कपड़ा... धूप... चम्मच... बोतल... मेज़।"


def words(text, lexicon, cfg):
    return [m.canonical for m in find_matches(tokenize(text), lexicon, cfg.threshold, cfg.stopwords)[0]]


# B1: common words must not fuzzy-match list words or animals
@pytest.mark.parametrize(
    ("form", "text", "expected"),
    [
        ("A", "बस चार ही याद हैं... घर, पानी, फूल।", ["ghar", "paani", "phool"]),  # चार != chair
        ("A", "दूर से आवाज़ आ रही है, हर बार", []),  # दूर != door, हर != ghar
        ("B", "घर", []),  # घर != ghadi
        ("C", "दीया, रस्सी... और याद नहीं आता।", ["diya", "rassi"]),  # आता != patta
        ("C", "रस्सी, छाता... बस इतना ही, बता दिया।", ["rassi", "chhata"]),  # दिया (gave) != दीया (lamp)
        ("A", "three", []),  # three != tree
    ],
)
def test_no_false_positive_list_words(cfg, form, text, expected) -> None:
    assert words(text, cfg.form_lexicons[form], cfg) == expected


@pytest.mark.parametrize("text", ["अरे... भूल गयी, हम्म", "रात", "बात", "सही", "अंदर", "महीना", "बार बार"])
def test_no_false_positive_animals(cfg, text) -> None:
    assert words(text, cfg.animal_lexicon, cfg) == []


# B3: plurals, English said in Devanagari, the candra-o vowel
@pytest.mark.parametrize(
    ("form", "text", "canonical"),
    [("A", "किताबें", "kitaab"), ("C", "पत्ते", "patta"), ("B", "पंखे", "pankha"), ("A", "फूलों", "phool"),
     ("A", "रोटियाँ", "roti"), ("A", "वॉटर", "paani"), ("C", "बॉटल", "botal"), ("A", "हाउस", "ghar")],
)
def test_inflected_and_loanword_list_words(cfg, form, text, canonical) -> None:
    assert words(text, cfg.form_lexicons[form], cfg) == [canonical]


@pytest.mark.parametrize(
    ("text", "canonical"),
    [("घोड़े", "horse"), ("चूहे", "mouse"), ("टाइगर", "tiger"), ("लायन", "lion"), ("मंकी", "monkey"), ("डॉग", "dog")],
)
def test_inflected_and_loanword_animals(cfg, text, canonical) -> None:
    assert words(text, cfg.animal_lexicon, cfg) == [canonical]


def test_cheetah_and_tiger_differ_but_hen_and_rooster_do_not(cfg) -> None:
    assert len(set(words("बाघ चीता", cfg.animal_lexicon, cfg))) == 2
    assert len(set(words("मुर्गा मुर्गी", cfg.animal_lexicon, cfg))) == 1


# B2: helper answers
@pytest.mark.parametrize(
    ("answer", "helping"),
    [("हाँ, बेटी बता रही थी ना", True), ("नहीं, नहीं... हाँ, बेटा था", True), ("बेटा बता रहा था", True),
     ("nahi ji haan", True), ("नहीं जी", False), ("नहीं, कोई नहीं", False), ("जी", True)],
)
def test_helper_answers(cfg, answer, helping) -> None:
    turns = [agent("आख़िरी सवाल: क्या कोई आपको जवाब बताने में मदद कर रहा था?"), user(answer)]
    assert tasks.detect_helper(turns, cfg) is helping


# B10: the helper answer comes from the close marker turn, not the last "madad" keyword
def test_helper_survives_goodbye_mentioning_madad_and_reworded_question(cfg) -> None:
    turns = [agent("आख़िरी सवाल: क्या किसी ने आपको जवाब बताए?"), user("हाँ, बेटी ने"),
             agent("आपकी मदद के लिए बहुत-बहुत धन्यवाद। नमस्ते।")]
    assert tasks.detect_helper(turns, cfg) is True


# B4: schooling
@pytest.mark.parametrize(
    ("answer", "years"),
    [("बी.ए. किया है", 15), ("बीए पास", 15), ("एमए", 17), ("कॉलेज तक", 14), ("B.A. kiya", 15),
     ("एक बात बताऊँ, मैंने बारहवीं तक पढ़ाई की", 12), ("दो साल", 2)],
)
def test_schooling_degrees_and_strong_tokens(cfg, answer, years) -> None:
    assert tasks.parse_schooling_years([user(answer)], cfg) == years


# B5: a digit string split over two user turns, and the साथ homophone
def test_hearing_split_turns_and_homophone(cfg) -> None:
    turns = [agent("4 7 2"), user("चार सात"), user("दो"), agent("3 9 5"), user("तीन नौ"), user("पाँच"),
             agent("8 1 6"), user("आठ एक छह")]
    assert tasks.score_hearing(turns, cfg)["correct"] == 3
    turns = [agent("4 7 2"), user("चार साथ दो"), agent("3 9 5"), user("x"), agent("8 1 6"), user("x")]
    assert tasks.score_hearing(turns, cfg)["items"][0]["correct"]


# B6: silence on delayed recall is DR 0, not "ended early"
def test_silent_recall_is_reached(cfg) -> None:
    res = tasks.score_recall([agent("छठा काम। कौन से शब्द याद हैं?"), agent("कोई बात नहीं।")], "A", cfg)
    assert res["reached"] and res["score"] == 0


# B7: orientation answers are scoped to their own question
def test_orientation_scoped_answers(cfg) -> None:
    call = datetime.fromisoformat("2026-10-28T10:15:00+05:30")  # Wednesday, October
    turns = [agent("पाँचवाँ काम। आज कौन सा दिन है?"), user("बुधवार"),
             agent("यह कौन सा महीना है?"), user("अक्टूबर"),
             agent("अभी कौन सा मौसम है?"), user("सर्दी, कल सोमवार को बारिश हुई थी"),
             agent("अभी दिन का कौन सा समय है?"), user("सुबह"),
             agent("आप किस गाँव या शहर में रहते हैं?"), user("मै सोनीपत में रहती हूँ")]
    res = tasks.score_orientation(turns, call, cfg)
    assert res["score"] == 5, res["answers"]


@pytest.mark.parametrize("place", ["नहीं मालूम", "मुझे नहीं मालूम", "भूल गई", "गाँव का नाम भूल गया"])
def test_place_dont_know_gets_no_point(cfg, place) -> None:
    call = datetime.fromisoformat("2026-10-28T10:15:00+05:30")
    res = tasks.score_orientation([agent("आप किस गाँव या शहर में रहते हैं?"), user(place)], call, cfg)
    assert res["items"]["place"] is False


# B8: a repeat request does not shift the trials
def test_repeat_request_does_not_shift_trials(cfg) -> None:
    turns = [agent(READ_C), user("फिर से बोलिए, सुनाई नहीं दिया"), agent(READ_C), user("दीया छाता"),
             agent(READ_C), user("छाता रस्सी बोतल"), agent(READ_C), user("छाता रस्सी बोतल मेज़")]
    assert tasks.score_learning(turns, "C", cfg)["trial_scores"] == [2, 3, 4]


def test_nothing_remembered_still_counts_as_a_trial(cfg) -> None:
    turns = [agent(READ_A), user("कुछ याद नहीं"), agent(READ_A), user("घर"), agent(READ_A), user("घर पानी")]
    assert tasks.score_learning(turns, "A", cfg)["trial_scores"] == [0, 1, 2]


# B9: marker spelling variants
@pytest.mark.parametrize(
    ("phrase", "task"),
    [("छठवाँ काम", "recall"), ("आखरी सवाल", "close"), ("चोथा काम", "fluency"), ("पांचवा काम।", "orientation"),
     ("Task 6", "recall")],
)
def test_marker_variants(phrase, task) -> None:
    from app.scoring.types import TASKS

    earlier = [agent(markers()[name][0]) for name in TASKS[: TASKS.index(task)]]
    seg = segment([*earlier, agent(phrase), user("x")], markers())
    assert task in seg.tasks


def test_overview_sentence_cannot_jump_to_close() -> None:
    seg = segment([agent("आज पहला काम सुनने का है और आख़िरी सवाल मदद के बारे में।"), user("ठीक"),
                   agent("दूसरा काम।"), user("आठ")], markers())
    assert list(seg.tasks) == ["hearing", "schooling"]


# C2: system/tool lines are not glued onto the user's answer
def test_system_lines_dropped() -> None:
    turns = parse_bolna_transcript("﻿assistant: नमस्ते\nuser: हाँ\nsystem: call transferred\ntool: x")
    assert [t.text for t in turns] == ["नमस्ते", "हाँ"]

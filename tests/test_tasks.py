from datetime import datetime

import pytest

from app.scoring import tasks
from tests.conftest import agent, user

READ_A = "घर... पानी... पेड़... रोटी... किताब... चाबी... दरवाज़ा... चाँद... कुर्सी... फूल। अब बताइए।"


# ---------------------------------------------------------------- hearing

def test_hearing_all_correct_with_words_digits_and_devanagari(cfg) -> None:
    turns = [agent("पहला काम। चार... सात... दो।"), user("four seven two"),
             agent("तीन नौ पाँच"), user("3-9-5"), agent("आठ एक छह"), user("आठ एक छह")]
    res = tasks.score_hearing(turns, cfg)
    assert res["correct"] == 3 and res["passed"] and res["aligned_to_agent_turns"]


def test_hearing_retry_counts(cfg) -> None:
    turns = [agent("4 7 2"), user("4 7 1"), agent("एक बार और, धीरे से। 4 7 2"), user("4 7 2"),
             agent("3 9 5"), user("3 9 5"), agent("8 1 6"), user("8 1 9")]
    res = tasks.score_hearing(turns, cfg)
    assert [i["correct"] for i in res["items"]] == [True, True, False]
    assert res["passed"]


def test_hearing_fails_below_two_of_three(cfg) -> None:
    turns = [agent("4 7 2"), user("kya?"), agent("3 9 5"), user("3 9 5"), agent("8 1 6"), user("8 6")]
    res = tasks.score_hearing(turns, cfg)
    assert res["correct"] == 1 and not res["passed"]


def test_hearing_answer_for_one_item_does_not_count_for_another(cfg) -> None:
    turns = [agent("4 7 2"), user("3 9 5"), agent("3 9 5"), user("nahi suna"), agent("8 1 6"), user("8 1 6")]
    assert [i["correct"] for i in tasks.score_hearing(turns, cfg)["items"]] == [False, False, True]


# ---------------------------------------------------------------- schooling

@pytest.mark.parametrize(
    ("answer", "years"),
    [("आठवीं तक पढ़ी हूँ", 8), ("das saal", 10), ("12th pass", 12), ("BA kiya", 15),
     ("मैं कभी स्कूल नहीं गई", 0), ("nahi, school nahi gaya", 0), ("पता नहीं", None), ("", None)],
)
def test_schooling_years(cfg, answer, years) -> None:
    assert tasks.parse_schooling_years([user(answer)], cfg) == years


@pytest.mark.parametrize(("years", "band"), [(0, "LOW"), (10, "LOW"), (11, "HIGH"), (16, "HIGH")])
def test_schooling_band_edges(cfg, years, band) -> None:
    assert tasks.schooling_band(years, cfg) == (band, False)


def test_unknown_schooling_is_assumed_low(cfg) -> None:
    assert tasks.schooling_band(None, cfg) == ("LOW", True)


# ---------------------------------------------------------------- learning

def test_learning_three_trials_each_word_once_per_trial(cfg) -> None:
    turns = [agent("तीसरा काम। मैं दस शब्द बोलूँगी।"),
             agent(READ_A), user("ghar ghar paani"),
             agent(READ_A), user("ghar paani ped"),
             agent(READ_A), user("ghar paani ped roti")]
    res = tasks.score_learning(turns, "A", cfg)
    assert res["trial_scores"] == [2, 3, 4]
    assert res["total"] == 9
    assert res["repeats"][0] == ["ghar"]


def test_learning_intrusions_logged_not_counted(cfg) -> None:
    turns = [agent(READ_A), user("ghar, nadi, chappal"), agent(READ_A), user(""), agent(READ_A), user("ghar")]
    res = tasks.score_learning(turns, "A", cfg)
    assert res["trials"][0] == ["ghar"]
    assert "nadi" in res["intrusions"][0] and "chappal" in res["intrusions"][0]
    assert res["total"] == 2


def test_learning_missing_trials_are_empty(cfg) -> None:
    res = tasks.score_learning([agent(READ_A), user("ghar")], "A", cfg)
    assert res["trial_scores"] == [1, 0, 0]
    assert res["answered"] == [True, False, False]


# ---------------------------------------------------------------- fluency

def test_fluency_synonyms_count_once(cfg) -> None:
    turns = [user("kutta, billi, dog, कुत्ता"), agent("हाँ... और?"), user("cat gaay")]
    res = tasks.score_fluency(turns, cfg)
    assert res["count"] == 3
    assert res["words"] == ["dog", "cat", "cow"]
    assert res["experimental_timing"] is True


def test_fluency_non_animals_not_counted(cfg) -> None:
    res = tasks.score_fluency([user("kutta, kursi, ped, sher")], cfg)
    assert res["words"] == ["dog", "lion"]
    assert "kursi" in res["non_animals"]


def test_fluency_with_timestamps_counts_only_the_window(cfg) -> None:
    stamps = [("kutta", 1.0), ("billi", 20.0), ("gaay", 59.5), ("sher", 61.0)]
    res = tasks.score_fluency([user("kutta billi gaay sher")], cfg, stamps)
    assert res["count"] == 3 and res["experimental_timing"] is False


# ---------------------------------------------------------------- orientation

def _orientation(day: str, month: str, season: str, tod: str, place: str):
    return [agent("पाँचवाँ काम। आज कौन सा दिन है?"), user(day),
            agent("यह कौन सा महीना है?"), user(month),
            agent("अभी कौन सा मौसम है?"), user(season),
            agent("अभी दिन का कौन सा समय है?"), user(tod),
            agent("आप किस गाँव या शहर में रहते हैं?"), user(place)]


def test_orientation_all_correct(cfg, call_time) -> None:
    res = tasks.score_orientation(_orientation("Wednesday", "October", "sardi", "subah", "Sonipat"), call_time, cfg)
    assert res["score"] == 5
    assert res["place_verified"] is False


def test_orientation_traditional_month_accepted(cfg, call_time) -> None:
    res = tasks.score_orientation(_orientation("बुधवार", "कार्तिक", "ठंड", "सुबह", "गाँव"), call_time, cfg)
    assert res["items"]["month"] is True


def test_orientation_wrong_answers_and_dont_know(cfg, call_time) -> None:
    res = tasks.score_orientation(_orientation("Monday", "June", "garmi", "raat", "pata nahi"), call_time, cfg)
    assert res["score"] == 0
    assert res["answers"]["day"] == "0"


def test_orientation_self_correction_uses_last_answer(cfg, call_time) -> None:
    res = tasks.score_orientation(_orientation("Monday... nahi, budhvar", "October", "", "", ""), call_time, cfg)
    assert res["items"]["day"] is True


def test_time_of_day_tolerance_near_boundary(cfg) -> None:
    late_morning = datetime.fromisoformat("2026-10-28T11:50:00+05:30")
    assert tasks.accepted_times_of_day(late_morning, cfg) == {"morning", "afternoon"}
    night = datetime.fromisoformat("2026-10-28T23:00:00+05:30")
    assert tasks.accepted_times_of_day(night, cfg) == {"night"}


def test_orientation_uses_ist_even_for_utc_call_time(cfg) -> None:
    utc = datetime.fromisoformat("2026-10-27T20:00:00+00:00")  # = Wed 01:30 IST
    res = tasks.score_orientation(_orientation("Wednesday", "October", "", "raat", ""), utc, cfg)
    assert res["items"]["day"] and res["items"]["time_of_day"]


# ---------------------------------------------------------------- recall / helper / consent

def test_recall_counts_unique_words(cfg) -> None:
    res = tasks.score_recall([user("घर, पानी, घर... और nadi")], "A", cfg)
    assert res["score"] == 2 and res["repeats"] == ["ghar"] and "nadi" in res["intrusions"]


@pytest.mark.parametrize(
    ("answer", "helping"),
    [("नहीं, मैं अकेली हूँ", False), ("haan, beta bata raha tha", True), ("no", False), ("hmm", None)],
)
def test_helper_detection(cfg, answer, helping) -> None:
    turns = [agent("आख़िरी सवाल: क्या कोई आपको जवाब बताने में मदद कर रहा था?"), user(answer)]
    assert tasks.detect_helper(turns, cfg) is helping


def test_consent(cfg) -> None:
    assert tasks.detect_consent([agent("क्या यह ठीक है?"), user("हाँ, ठीक है")], cfg) is True
    assert tasks.detect_consent([agent("क्या यह ठीक है?"), user("नहीं अभी नहीं")], cfg) is False


def test_speech_markers_are_flagged_experimental(cfg) -> None:
    res = tasks.speech_markers([agent("x"), user("um ghar matlab paani")], cfg)
    assert res["experimental"] is True and res["filler_rate"] > 0

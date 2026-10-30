import pytest

from app.scoring.outcome import INVALID, NORMAL, REFER, UNCERTAIN, decide_outcome, needs_review


@pytest.fixture
def rules(cfg):
    return cfg.raw


@pytest.mark.parametrize(
    ("dr", "f", "o", "expected"),
    [
        (0, 20, 5, REFER),
        (2, 20, 5, REFER),       # edge: DR <= 2
        (3, 20, 5, UNCERTAIN),   # edge: DR == 3
        (4, 20, 5, NORMAL),      # edge: DR >= 4
        (4, 7, 3, UNCERTAIN),    # secondary: F < 8 AND O <= 3
        (4, 8, 3, NORMAL),       # F == 8 is not < 8
        (4, 7, 4, NORMAL),       # O == 4 is not <= 3
        (10, 0, 0, UNCERTAIN),
    ],
)
def test_low_band(rules, dr, f, o, expected) -> None:
    assert decide_outcome("LOW", dr, f, o, [], rules)[0] == expected


@pytest.mark.parametrize(
    ("dr", "f", "o", "expected"),
    [
        (3, 20, 5, REFER),       # edge: DR <= 3
        (4, 20, 5, UNCERTAIN),   # edge: DR == 4
        (5, 20, 5, NORMAL),      # edge: DR >= 5
        (5, 10, 3, UNCERTAIN),   # secondary: F < 11 AND O <= 3
        (5, 11, 3, NORMAL),
        (5, 10, 4, NORMAL),
    ],
)
def test_high_band(rules, dr, f, o, expected) -> None:
    assert decide_outcome("HIGH", dr, f, o, [], rules)[0] == expected


def test_rule_fired_names_band_and_value(rules) -> None:
    assert decide_outcome("LOW", 3, 20, 5, [], rules) == (UNCERTAIN, "LOW band: delayed recall = 3")
    outcome, rule = decide_outcome("LOW", 4, 7, 3, [], rules)
    assert "animal naming = 7" in rule and "orientation = 3" in rule


@pytest.mark.parametrize(
    "reason",
    ["hearing_check_failed", "ended_before_delayed_recall", "too_many_empty_answers",
     "helper_present", "stopped_distress"],
)
def test_any_invalid_reason_overrides_scores(rules, reason) -> None:
    outcome, rule = decide_outcome("LOW", 10, 30, 5, [reason], rules)
    assert outcome == INVALID and reason in rule


def test_review_queue_membership() -> None:
    assert not needs_review(NORMAL)
    assert all(needs_review(o) for o in (UNCERTAIN, REFER, INVALID))

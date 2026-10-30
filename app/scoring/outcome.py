"""Band rules -> outcome + the rule that fired. PILOT placeholders from config/scoring.yaml."""

from __future__ import annotations

from typing import Any

NORMAL = "NORMAL"
UNCERTAIN = "UNCERTAIN"
REFER = "REFER"
INVALID = "INVALID"

INVALID_REASON_TEXT = {
    "hearing_check_failed": "hearing/line check failed (fewer than {min} of {max} digit strings repeated)",
    "ended_before_delayed_recall": "call ended before the delayed recall task",
    "too_many_empty_answers": "more than {pct}% of expected answers were empty or unintelligible",
    "helper_present": "the person said someone was helping them answer",
    "stopped_distress": "the call was stopped because the person seemed distressed",
}


def decide_outcome(
    band: str,
    delayed_recall: int,
    fluency: int,
    orientation: int,
    invalid_reasons: list[str],
    scoring: dict[str, Any],
) -> tuple[str, str]:
    """Return (outcome, rule_fired). Deterministic; every branch names its rule."""
    if invalid_reasons:
        return INVALID, "INVALID: " + "; ".join(invalid_reasons)

    rules = scoring["bands"][band]
    refer_max = int(rules["refer_if_dr_at_most"])
    uncertain_eq = int(rules["uncertain_if_dr_equals"])
    sec = rules["secondary_uncertain"]
    f_below, o_max = int(sec["fluency_below"]), int(sec["orientation_at_most"])

    if delayed_recall <= refer_max:
        return REFER, f"{band} band: delayed recall = {delayed_recall} (<= {refer_max})"
    if delayed_recall == uncertain_eq:
        return UNCERTAIN, f"{band} band: delayed recall = {delayed_recall}"
    if fluency < f_below and orientation <= o_max:
        return UNCERTAIN, (
            f"{band} band: delayed recall = {delayed_recall} (>= {uncertain_eq + 1}), but "
            f"animal naming = {fluency} (< {f_below}) and orientation = {orientation} (<= {o_max})"
        )
    return NORMAL, f"{band} band: delayed recall = {delayed_recall} (>= {uncertain_eq + 1})"


def needs_review(outcome: str) -> bool:
    return outcome in (UNCERTAIN, REFER, INVALID)

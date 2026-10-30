"""Per-task scorers. Pure functions: turns + config in, evidence dicts out."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.scoring.matching import Lexicon, find_matches, unique_in_order
from app.scoring.normalize import Token, phonetic_key, tokenize
from app.scoring.types import ScoringConfig, Turn

NOISE_TOKENS = frozenset({"inaudible", "unintelligible", "noise", "unclear", "blank", "silence"})

_DIGIT_WORDS_RAW = {
    0: ["zero", "shunya", "sunya", "shoonya", "शून्य"],
    1: ["one", "ek", "एक"],
    2: ["two", "do", "दो"],
    3: ["three", "teen", "tin", "तीन"],
    4: ["four", "char", "chaar", "चार"],
    5: ["five", "panch", "paanch", "पाँच", "पांच"],
    6: ["six", "chhe", "che", "chhah", "chah", "chheh", "छह", "छः", "छे"],
    7: ["seven", "saat", "sat", "सात", "साथ", "sath", "saath"],  # STT often writes साथ
    8: ["eight", "aath", "aat", "आठ"],
    9: ["nine", "nau", "nao", "नौ", "नो", "नव"],
}
DIGIT_WORDS: dict[str, str] = {
    t.key: str(d) for d, words in _DIGIT_WORDS_RAW.items() for w in words for t in tokenize(w)
}

_NUMBER_WORDS_RAW = {
    0: ["zero", "none", "never", "anpadh", "अनपढ़", "shunya", "शून्य"],
    1: ["one", "ek", "pehli", "pahli", "first", "एक", "पहली"],
    2: ["two", "do", "doosri", "dusri", "second", "दो", "दूसरी"],
    3: ["three", "teen", "teesri", "tisri", "third", "तीन", "तीसरी"],
    4: ["four", "char", "chaar", "chauthi", "fourth", "चार", "चौथी"],
    5: ["five", "panch", "paanch", "paanchvi", "panchvi", "fifth", "पाँच", "पांच", "पाँचवीं", "पांचवीं"],
    6: ["six", "chhe", "chhah", "chhathi", "chhati", "sixth", "छह", "छठी"],
    7: ["seven", "saat", "saatvi", "satvi", "seventh", "सात", "सातवीं"],
    8: ["eight", "aath", "aathvi", "athvi", "eighth", "आठ", "आठवीं"],
    9: ["nine", "nau", "nauvi", "ninth", "नौ", "नौवीं"],
    10: ["ten", "das", "dus", "dasvi", "dasvin", "matric", "tenth", "highschool", "दस", "दसवीं",
         "मैट्रिक"],
    11: ["eleven", "gyarah", "gyara", "gyarahvi", "eleventh", "ग्यारह", "ग्यारहवीं"],
    12: ["twelve", "barah", "bara", "barahvi", "baarvi", "inter", "intermediate", "twelfth",
         "बारह", "बारहवीं", "इंटर"],
    13: ["thirteen", "terah", "तेरह"], 14: ["fourteen", "chaudah", "चौदह"],
    15: ["fifteen", "pandrah", "graduate", "graduation", "ba", "bsc", "bcom", "degree", "पंद्रह",
         "ग्रेजुएट", "ग्रेजुएशन"],
    16: ["sixteen", "solah", "सोलह"],
    17: ["seventeen", "satrah", "postgraduate", "msc", "mcom", "सत्रह"],
    18: ["eighteen", "atharah", "अठारह"], 19: ["nineteen", "unnis", "उन्नीस"],
    20: ["twenty", "bees", "phd", "बीस", "पीएचडी"],
}
_DEGREES = {
    14: ["college", "कॉलेज"],
    15: ["बीए", "बीएससी", "बीकॉम", "बीकोम", "डिग्री", "bsc", "bcom", "ba"],
    17: ["एमए", "एमएससी", "एमकॉम", "mba", "एमबीए", "msc", "mcom"],
}
for _n, _words in _DEGREES.items():
    _NUMBER_WORDS_RAW.setdefault(_n, []).extend(_words)
# Bare cardinals ("ek", "do") are weak evidence: "एक बात बताऊँ... बारहवीं" means 12, not 1.
_CARDINALS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "ek", "do", "teen", "char", "chaar", "panch", "paanch", "chhe", "chhah", "saat", "aath", "nau", "das", "dus",
    "एक", "दो", "तीन", "चार", "पाँच", "पांच", "छह", "सात", "आठ", "नौ", "दस", "ग्यारह", "बारह",
]
NUMBER_WORDS: dict[str, int] = {
    t.key: n for n, words in _NUMBER_WORDS_RAW.items() for w in words for t in tokenize(w)
}
CARDINAL_KEYS = frozenset(t.key for w in _CARDINALS for t in tokenize(w))
_ABBREV_DOT = re.compile(r"(?<=\S)\.(?=\S)")

PLACE_QUESTION = (
    "gaon", "gav", "ganv", "gaanv", "शहर", "गाँव", "shahar", "jagah", "kahan",
    "town", "village", "city", "place",
)
HELPER_QUESTION = ("madad", "मदद", "help", "helping", "sahayata", "bata raha", "bata rahi")
# Someone was telling the answers ("बेटी बता रही थी") even without an explicit "yes".
HELPER_SAYS = ("bata raha", "bata rahi", "bata rahe", "बता रहा", "बता रही", "बता रहे", "मदद कर रहा",
               "मदद कर रही", "मदद कर रहे", "madad kar raha", "madad kar rahi", "was helping", "helped me")
REPEAT_REQUEST = ("phir se", "fir se", "dobara", "repeat", "again", "kya bola", "sunai nahi", "samajh nahi",
                  "फिर से", "दोबारा", "क्या बोला", "क्या बोली", "सुनाई नहीं", "समझ नहीं")
# Which orientation item an agent question asks about, checked in this priority order.
ORIENTATION_QUESTIONS = (
    ("time_of_day", ("samay", "समय", "time", "morning", "evening", "subah", "सुबह")),
    ("season", ("mausam", "मौसम", "season", "ritu", "ऋतु")),
    ("month", ("mahina", "महीना", "month", "mahine", "महीने")),
    ("place", PLACE_QUESTION),
    ("day", ("din", "दिन", "day", "vaar", "वार")),
)


# ---------------------------------------------------------------- helpers

def user_turns(turns: list[Turn]) -> list[Turn]:
    return [t for t in turns if t.role == "user"]


def has_content(text: str) -> bool:
    return any(len(t.raw) >= 2 and t.raw not in NOISE_TOKENS for t in tokenize(text))


def user_tokens(turns: list[Turn]) -> list[Token]:
    return [tok for t in user_turns(turns) for tok in tokenize(t.text)]


def _key_text(text: str) -> str:
    return " " + " ".join(t.key for t in tokenize(text)) + " "


def contains_phrase(text: str, phrases: frozenset[str]) -> bool:
    keyed = _key_text(text)
    return any(f" {p} " in keyed for p in phrases)


def _phrase_keys(phrases: tuple[str, ...]) -> frozenset[str]:
    return frozenset(" ".join(t.key for t in tokenize(p)) for p in phrases)


def parse_yes_no(text: str, cfg: ScoringConfig) -> bool | None:
    """True = yes, False = no, None = unclear. The LAST yes/no word wins (self-corrections:
    "नहीं नहीं... हाँ" = yes)."""
    toks = tokenize(text)
    no = find_matches(toks, cfg.no_lexicon, threshold=100)[0]
    yes = find_matches(toks, cfg.yes_lexicon, threshold=100)[0]
    if not no and not yes:
        # A bare honorific "जी" / "ji" is a polite yes.
        return True if any(t.raw == "ji" for t in toks) else None
    last_no = no[-1].position if no else -1
    last_yes = yes[-1].position if yes else -1
    return last_yes > last_no


REPEAT_REQUEST_KEYS = _phrase_keys(REPEAT_REQUEST)
HELPER_SAYS_KEYS = _phrase_keys(HELPER_SAYS)
ORIENTATION_QUESTION_KEYS = tuple((item, _phrase_keys(words)) for item, words in ORIENTATION_QUESTIONS)


def digit_sequence(text: str) -> str:
    out: list[str] = []
    for tok in tokenize(text):
        if tok.raw.isdigit():
            out.append(tok.raw)
        elif tok.key in DIGIT_WORDS:
            out.append(DIGIT_WORDS[tok.key])
    return "".join(out)


def _answer_after(turns: list[Turn], keywords: tuple[str, ...]) -> tuple[str, bool]:
    """Text of the user turns after the last agent turn containing a keyword."""
    idx = None
    for i, t in enumerate(turns):
        if t.role == "agent" and any(f" {k} " in _key_text(t.text) for k in map(phonetic_key, keywords)):
            idx = i
    if idx is None:
        return "", False
    answer: list[str] = []
    for t in turns[idx + 1 :]:
        if t.role == "agent":
            if answer:
                break
            continue
        answer.append(t.text)
    return " ".join(answer), True


# ---------------------------------------------------------------- tasks

def score_hearing(turns: list[Turn], cfg: ScoringConfig) -> dict[str, Any]:
    expected: list[str] = [str(s) for s in cfg.raw["hearing"]["digit_strings"]]
    min_correct = int(cfg.raw["hearing"]["min_correct"])
    agent_at: list[int | None] = []
    for exp in expected:
        found = next(
            (i for i, t in enumerate(turns) if t.role == "agent" and exp in digit_sequence(t.text)),
            None,
        )
        agent_at.append(found)
    aligned = all(a is not None for a in agent_at)
    items = []
    for n, exp in enumerate(expected):
        if aligned:
            start = agent_at[n]
            nxt = [a for a in agent_at[n + 1 :] if a is not None and a > start]  # type: ignore[operator]
            end = nxt[0] if nxt else len(turns)
            responses = [t for t in turns[start + 1 : end] if t.role == "user"]  # type: ignore[operator]
        else:
            responses = user_turns(turns)
        heard = [digit_sequence(t.text) for t in responses]
        items.append({
            "expected": exp,
            "heard": [h for h in heard if h],
            # Older speakers pause between digits, so one answer can arrive as two user turns.
            "correct": any(exp in h for h in heard) or exp in "".join(heard),
            "answered": any(has_content(t.text) for t in responses),
        })
    correct = sum(i["correct"] for i in items)
    return {
        "items": items,
        "correct": correct,
        "max": len(expected),
        "passed": correct >= min_correct,
        "aligned_to_agent_turns": aligned,
    }


def parse_schooling_years(turns: list[Turn], cfg: ScoringConfig) -> int | None:
    """Years of schooling from the person's answer (digits, number words or class names).

    An answer with a negation and no number ("नहीं, कभी स्कूल नहीं गई") means none (0);
    "I don't know" stays unknown.
    """
    weak: int | None = None
    for t in user_turns(turns):
        for tok in tokenize(_ABBREV_DOT.sub("", t.text)):
            m = re.match(r"^(\d+)(st|nd|rd|th|vi|vin|va)?$", tok.raw)
            if m and int(m.group(1)) <= 25:
                return int(m.group(1))
            if tok.key in NUMBER_WORDS:
                if tok.key not in CARDINAL_KEYS:
                    return NUMBER_WORDS[tok.key]  # class name, ordinal or degree
                weak = NUMBER_WORDS[tok.key] if weak is None else weak
    if weak is not None:
        return weak
    for t in user_turns(turns):
        if not contains_phrase(t.text, cfg.dont_know) and parse_yes_no(t.text, cfg) is False:
            return 0
    return None


def schooling_band(years: int | None, cfg: ScoringConfig) -> tuple[str, bool]:
    """(band, assumed). Unknown schooling falls back to the configured band."""
    if years is None:
        return str(cfg.raw["schooling"]["unknown_band"]), True
    return ("LOW" if years <= int(cfg.raw["schooling"]["low_band_max_years"]) else "HIGH"), False


def _match_words(turns: list[Turn], lexicon: Lexicon, cfg: ScoringConfig) -> dict[str, Any]:
    matches, unmatched = find_matches(user_tokens(turns), lexicon, cfg.threshold, cfg.stopwords)
    words, repeats = unique_in_order(m.canonical for m in matches)
    return {"words": words, "repeats": repeats, "intrusions": unmatched,
            "surfaces": [m.surface for m in matches]}


def _is_reading(turn: Turn, lexicon: Lexicon, cfg: ScoringConfig) -> bool:
    if turn.role != "agent":
        return False
    matches, _ = find_matches(tokenize(turn.text), lexicon, cfg.threshold, cfg.stopwords)
    return len({m.canonical for m in matches}) >= int(cfg.raw["learning"]["reading_min_list_words"])


def _trial_answered(trial: list[Turn], lexicon: Lexicon, cfg: ScoringConfig) -> bool:
    """Did the person attempt recall? A repeat request ("फिर से बोलिए") or "हाँ हाँ" is not an attempt,
    so a re-read after it continues the same trial instead of starting the next one."""
    text = " ".join(t.text for t in user_turns(trial))
    if not text.strip():
        return False
    if find_matches(tokenize(text), lexicon, cfg.threshold, cfg.stopwords)[0]:
        return True
    if contains_phrase(text, REPEAT_REQUEST_KEYS):
        return False
    if contains_phrase(text, cfg.dont_know):
        return True
    content = [t for t in tokenize(text) if t.stop_key not in cfg.stopwords and len(t.raw) >= 3]
    return len(content) >= 3


def split_trials(turns: list[Turn], lexicon: Lexicon, cfg: ScoringConfig) -> list[list[Turn]]:
    """Each agent turn that reads the list starts a new trial (unless the open trial has no recall
    attempt yet); user turns after it belong to that trial."""
    n_trials = int(cfg.raw["learning"]["trials"])
    trials: list[list[Turn]] = []
    for t in turns:
        if _is_reading(t, lexicon, cfg):
            if not trials or _trial_answered(trials[-1], lexicon, cfg):
                trials.append([])
            continue
        if trials:
            trials[-1].append(t)
    if not trials and user_turns(turns):
        trials = [list(turns)]  # agent reading not recognised: score everything as one trial
    trials = trials[:n_trials]
    return trials + [[] for _ in range(n_trials - len(trials))]


def score_learning(turns: list[Turn], form: str, cfg: ScoringConfig) -> dict[str, Any]:
    lexicon = cfg.form_lexicons[form]
    per_trial = []
    for trial in split_trials(turns, lexicon, cfg):
        res = _match_words(trial, lexicon, cfg)
        res["answered"] = any(has_content(t.text) for t in user_turns(trial))
        per_trial.append(res)
    return {
        "trials": [t["words"] for t in per_trial],
        "trial_scores": [len(t["words"]) for t in per_trial],
        "total": sum(len(t["words"]) for t in per_trial),
        "max": 10 * len(per_trial),
        "intrusions": [t["intrusions"] for t in per_trial],
        "repeats": [t["repeats"] for t in per_trial],
        "answered": [t["answered"] for t in per_trial],
    }


def score_fluency(
    turns: list[Turn], cfg: ScoringConfig, timestamps: list[tuple[str, float]] | None = None
) -> dict[str, Any]:
    window = float(cfg.raw["fluency"]["window_seconds"])
    if timestamps:
        text = " ".join(w for w, ts in timestamps if ts <= window)
        res = _match_words([Turn("user", text)], cfg.animal_lexicon, cfg)
        timing = {"experimental_timing": False, "timing_source": "asr_timestamps"}
    else:
        res = _match_words(turns, cfg.animal_lexicon, cfg)
        timing = {"experimental_timing": True, "timing_source": "whole_segment"}
    return {
        "count": len(res["words"]),
        "words": res["words"],
        "repeats": res["repeats"],
        "non_animals": res["intrusions"],
        "answered": any(has_content(t.text) for t in user_turns(turns)),
        "window_seconds": window,
        **timing,
    }


def _ist(call_time: datetime, cfg: ScoringConfig) -> datetime:
    offset = timedelta(minutes=int(cfg.raw["orientation"]["utc_offset_minutes"]))
    return call_time.astimezone(timezone(offset))


def accepted_times_of_day(local: datetime, cfg: ScoringConfig) -> set[str]:
    tol = int(cfg.raw["orientation"]["time_boundary_tolerance_minutes"])
    accepted: set[str] = set()
    for probe in (local, local - timedelta(minutes=tol), local + timedelta(minutes=tol)):
        hour = probe.hour + probe.minute / 60
        for name, spec in cfg.raw["orientation"]["times_of_day"].items():
            lo, hi = spec["hours"]
            if lo <= hour < hi or lo <= hour + 24 < hi:
                accepted.add(name)
    return accepted


def _last_match(tokens: list[Token], lexicon: Lexicon, cfg: ScoringConfig) -> tuple[str, int] | None:
    matches, _ = find_matches(tokens, lexicon, cfg.threshold, cfg.stopwords)
    return (matches[-1].canonical, matches[-1].position) if matches else None


def orientation_answers(turns: list[Turn]) -> dict[str, str | None]:
    """Text of the user's answer to each orientation question (None if the question wasn't found).

    Each agent question is assigned to one item by keyword (priority: time of day, season,
    month, place, day), so "मै सोनीपत में" in the place answer cannot turn the month into May.
    """
    answers: dict[str, list[str]] = {}
    current: str | None = None
    for t in turns:
        if t.role == "agent":
            keyed = _key_text(t.text)
            found = next(
                (item for item, keys in ORIENTATION_QUESTION_KEYS if any(f" {k} " in keyed for k in keys)), None
            )
            if found:
                current = found
                answers.setdefault(found, [])
            continue
        if current:
            answers[current].append(t.text)
    return {item: " ".join(answers[item]) if item in answers else None for item, _ in ORIENTATION_QUESTION_KEYS}


def score_orientation(turns: list[Turn], call_time: datetime, cfg: ScoringConfig) -> dict[str, Any]:
    local = _ist(call_time, cfg)
    per_item = orientation_answers(turns)
    all_tokens = user_tokens(turns)

    def toks(item: str) -> list[Token]:
        text = per_item[item]
        return all_tokens if text is None else tokenize(text)  # question not found: scan everything

    month_ok_seasons = {str(s) for s in cfg.raw["orientation"]["season_by_month"][local.month]}
    expected = {
        "day": local.strftime("%A"),
        "month": local.strftime("%B"),
        "season": sorted(month_ok_seasons),
        "time_of_day": sorted(accepted_times_of_day(local, cfg)),
    }
    items: dict[str, bool] = {}
    answers: dict[str, str | None] = {}

    day = _last_match(toks("day"), cfg.day_lexicon, cfg)
    answers["day"] = day[0] if day else None
    items["day"] = day is not None and int(day[0]) == local.weekday()

    greg = _last_match(toks("month"), cfg.month_lexicon, cfg)
    hindu = _last_match(toks("month"), cfg.hindu_month_lexicon, cfg)
    if greg and (not hindu or greg[1] >= hindu[1]):
        answers["month"] = greg[0]
        items["month"] = int(greg[0]) == local.month
    elif hindu:
        answers["month"] = hindu[0]
        items["month"] = hindu[0] in cfg.hindu_months_by_month.get(local.month, frozenset())
    else:
        answers["month"], items["month"] = None, False

    season = _last_match(toks("season"), cfg.season_lexicon, cfg)
    answers["season"] = season[0] if season else None
    items["season"] = season is not None and season[0] in month_ok_seasons

    tod = _last_match(toks("time_of_day"), cfg.time_lexicon, cfg)
    answers["time_of_day"] = tod[0] if tod else None
    items["time_of_day"] = tod is not None and tod[0] in expected["time_of_day"]

    place_text = per_item["place"]
    if place_text is None:
        users = user_turns(turns)
        place_text = users[-1].text if users else ""
    place_content = [
        t for t in tokenize(place_text) if t.stop_key not in cfg.stopwords and len(t.raw) >= 3
    ]
    answers["place"] = place_text.strip() or None
    items["place"] = bool(place_content) and not contains_phrase(place_text, cfg.dont_know)

    if any(v is not None for v in per_item.values()):
        answered = sum(bool(v and has_content(v)) for v in per_item.values())
    else:
        answered = min(5, sum(has_content(t.text) for t in user_turns(turns)))
    return {
        "score": sum(items.values()),
        "max": 5,
        "items": items,
        "answers": answers,
        "expected": expected,
        "place_verified": False,  # we cannot check the town/village; a reviewer can
        "answered_items": answered,
        "call_time_local": local.isoformat(),
    }


def score_recall(turns: list[Turn], form: str, cfg: ScoringConfig) -> dict[str, Any]:
    res = _match_words(turns, cfg.form_lexicons[form], cfg)
    return {
        "score": len(res["words"]),
        "max": 10,
        "words": res["words"],
        "repeats": res["repeats"],
        "intrusions": res["intrusions"],
        "answered": any(has_content(t.text) for t in user_turns(turns)),
        # The agent moving on after the recall question also proves the task was reached
        # (silence is a valid, low-scoring answer, not an early hang-up).
        "reached": bool(user_turns(turns)) or sum(t.role == "agent" for t in turns) > 1,
    }


def detect_helper(turns: list[Turn], cfg: ScoringConfig) -> bool | None:
    """Answer to "Is anyone helping you answer?" (True = someone is helping, None = unclear).

    `turns` is the close segment: its first agent turn is the helper question (it carries the
    close marker), so the answer is the user turns right after it, whatever the wording.
    """
    answer: list[str] = []
    started = False
    for t in turns:
        if t.role == "agent":
            if started and answer:
                break
            started = True
            continue
        if started:
            answer.append(t.text)
    text = " ".join(answer)
    if not text.strip():
        text, asked = _answer_after(turns, HELPER_QUESTION)
        if not asked or not text.strip():
            return None
    yn = parse_yes_no(text, cfg)
    if yn is None and contains_phrase(text, HELPER_SAYS_KEYS):
        return True
    return yn


def detect_consent(preamble: list[Turn], cfg: ScoringConfig) -> bool | None:
    users = [t for t in preamble if t.role == "user" and has_content(t.text)]
    for t in users:
        yn = parse_yes_no(t.text, cfg)
        if yn is not None:
            return yn
    return None


def speech_markers(all_turns: list[Turn], cfg: ScoringConfig) -> dict[str, Any]:
    """EXPERIMENTAL descriptive features. Never used for the outcome."""
    users = [t for t in all_turns if t.role == "user"]
    toks = [tok for t in users for tok in tokenize(t.text)]
    fillers = sum(tok.key in cfg.fillers for tok in toks)
    dont_know = sum(contains_phrase(t.text, cfg.dont_know) for t in users)
    latencies = [
        b.t - a.t for a, b in zip(all_turns, all_turns[1:], strict=False)
        if a.role == "agent" and b.role == "user" and a.t is not None and b.t is not None
    ]
    return {
        "experimental": True,
        "user_turns": len(users),
        "mean_words_per_turn": round(len(toks) / len(users), 2) if users else 0.0,
        "filler_rate": round(fillers / len(toks), 3) if toks else 0.0,
        "dont_know_count": dont_know,
        "mean_response_latency_s": round(sum(latencies) / len(latencies), 2) if latencies else None,
    }

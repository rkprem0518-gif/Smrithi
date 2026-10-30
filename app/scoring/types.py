"""Plain data types shared by the scoring engine and the services that feed it."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from app.scoring.matching import Lexicon, build_lexicon
from app.scoring.normalize import stop_keys, tokenize

TASKS = ("hearing", "schooling", "learning", "fluency", "orientation", "recall", "close")


@dataclass(frozen=True)
class Turn:
    role: str  # "agent" | "user"
    text: str
    t: float | None = None  # seconds from call start, when known


@dataclass
class Segments:
    """A transcript split into tasks by the agent's fixed marker phrases."""

    preamble: list[Turn] = field(default_factory=list)
    tasks: dict[str, list[Turn]] = field(default_factory=dict)
    markers_found: list[str] = field(default_factory=list)
    declined: bool = False
    stopped: bool = False

    def turns(self, task: str) -> list[Turn]:
        return self.tasks.get(task, [])


@dataclass(frozen=True)
class ScoringContext:
    call_time: datetime  # timezone-aware; orientation is checked against it
    language: str = "hi"
    word_form: str = "A"
    schooling_years: int | None = None  # entered in the UI; overrides the spoken answer
    # (word, seconds since the person started naming animals) from the optional ASR fallback.
    fluency_timestamps: list[tuple[str, float]] | None = None


@dataclass(frozen=True)
class FormWord:
    id: str
    hi: str
    en: str
    kn: str = ""


def _key_set(words: list[Any]) -> frozenset[str]:
    return frozenset(" ".join(t.key for t in tokenize(str(w))) for w in words)


@dataclass(frozen=True)
class ScoringConfig:
    """Everything the engine needs, built from the YAML dicts (no file I/O here)."""

    raw: dict[str, Any]
    threshold: float
    forms: dict[str, list[FormWord]]
    form_lexicons: dict[str, Lexicon]
    animal_lexicon: Lexicon
    stopwords: frozenset[str]
    day_lexicon: Lexicon
    month_lexicon: Lexicon
    hindu_month_lexicon: Lexicon
    hindu_months_by_month: dict[int, frozenset[str]]
    season_lexicon: Lexicon
    time_lexicon: Lexicon
    yes_lexicon: Lexicon
    no_lexicon: Lexicon
    dont_know: frozenset[str]
    fillers: frozenset[str]

    @classmethod
    def from_dicts(
        cls, scoring: dict[str, Any], wordlists: dict[str, Any], animals: dict[str, Any]
    ) -> ScoringConfig:
        forms: dict[str, list[FormWord]] = {}
        form_lexicons: dict[str, Lexicon] = {}
        for form, entries in wordlists["forms"].items():
            forms[form] = [FormWord(e["id"], e["hi"], e["en"], e.get("kn", "")) for e in entries]
            form_lexicons[form] = build_lexicon(
                {e["id"]: [e["hi"], e["en"], *([e["kn"]] if e.get("kn") else []), *e.get("variants", [])]
                 for e in entries}
            )
        orient = scoring["orientation"]
        # Canonical id = the word's own key; the original spelling is kept as a variant so
        # Devanagari answers (कार्तिक) match Devanagari-derived keys.
        hindu_all: dict[str, list[str]] = {}
        for words in orient["hindu_months"].values():
            for w in words:
                hindu_all.setdefault(" ".join(t.key for t in tokenize(str(w))), []).append(str(w))
        return cls(
            raw=scoring,
            threshold=float(scoring["matching"]["fuzzy_threshold"]),
            forms=forms,
            form_lexicons=form_lexicons,
            animal_lexicon=build_lexicon(animals["animals"]),
            stopwords=stop_keys(
                wordlists.get("stopwords", []),
                wordlists.get("stopwords_devanagari", []) + wordlists.get("stopwords_kannada", []),
            ),
            day_lexicon=build_lexicon({str(k): v for k, v in orient["days"].items()}),
            month_lexicon=build_lexicon({str(k): v for k, v in orient["months"].items()}),
            hindu_month_lexicon=build_lexicon(hindu_all),
            hindu_months_by_month={
                int(k): _key_set(v) for k, v in orient["hindu_months"].items()
            },
            season_lexicon=build_lexicon(orient["seasons"]),
            time_lexicon=build_lexicon(
                {k: v["words"] for k, v in orient["times_of_day"].items()}
            ),
            yes_lexicon=build_lexicon({"yes": scoring["yes_words"]}),
            no_lexicon=build_lexicon({"no": scoring["no_words"]}),
            dont_know=_key_set(orient["dont_know"]),
            fillers=_key_set(scoring["speech_markers"]["fillers"]),
        )


@dataclass
class ScoreResult:
    scorer_version: str
    outcome: str  # NORMAL | UNCERTAIN | REFER | INVALID
    rule_fired: str
    band: str  # LOW | HIGH
    band_source: str  # ui | call | assumed
    schooling_years: int | None
    consent_call: bool | None
    hearing: dict[str, Any]
    learning: dict[str, Any]
    fluency: dict[str, Any]
    orientation: dict[str, Any]
    delayed_recall: dict[str, Any]
    helper_present: bool | None
    invalid_reasons: list[str]
    empty_answers: dict[str, Any]
    speech_markers: dict[str, Any]
    segments_found: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

"""Turn a weekly call transcript into flags, a mood word, notes and a message for the family.

Fixed rules only (config/flags.yaml): the same words always give the same flags. The AI that holds the
conversation has no say in what gets flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.scoring.types import Turn

CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "flags.yaml"
_SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")
_LATIN = re.compile(r"[A-Za-z]")
MAX_QUOTE = 180


@lru_cache
def flag_config() -> dict[str, Any]:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Mention:
    category: str
    kind: str  # red | yellow | watch | safety
    label: str
    rule: str
    quote: str
    cleared: bool = False


@dataclass
class FlagOut:
    category: str
    level: str  # green | yellow | red
    quote: str
    rule: str
    family_visible: bool = True  # safety flags never go to the family


@dataclass
class Analysis:
    mentions: list[Mention] = field(default_factory=list)
    flags: list[FlagOut] = field(default_factory=list)
    mood: str = "okay"  # cheerful | okay | low
    message_for_family: str | None = None
    notes: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)  # categories the parent said got better

    @property
    def worst(self) -> str:
        levels = [f.level for f in self.flags]
        return "red" if "red" in levels else "yellow" if "yellow" in levels else "green"


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    if _LATIN.search(phrase):
        return re.compile(r"(?<![\w'])" + re.escape(phrase.lower()) + r"(?![\w'])")
    return re.compile(re.escape(phrase))


@lru_cache
def _compiled() -> list[tuple[str, dict[str, Any], list[re.Pattern[str]], list[re.Pattern[str]]]]:
    cfg = flag_config()
    order = {"red": 0, "safety": 0, "yellow": 1, "watch": 2}
    out = []
    for name, cat in sorted(cfg["categories"].items(), key=lambda kv: order[kv[1]["kind"]]):
        phrases = [p for lang in cat["phrases"].values() for p in lang]
        clear = [p for lang in (cat.get("clear") or {}).values() for p in lang]
        out.append((name, cat, [_phrase_pattern(p) for p in phrases], [_phrase_pattern(p) for p in clear]))
    return out


def _negated(sentence: str, start: int) -> bool:
    """English only: 'no pain', 'didn't fall', 'never lonely'."""
    words = re.findall(r"[a-z']+", sentence[:start])[-3:]
    return any(w in flag_config()["negations_en"] for w in words)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _quote(sentence: str) -> str:
    return sentence if len(sentence) <= MAX_QUOTE else sentence[: MAX_QUOTE - 1].rstrip() + "…"


def find_mentions(turns: list[Turn]) -> list[Mention]:
    """Every category the parent's own words touched, once per category (first quote wins)."""
    found: dict[str, Mention] = {}
    for turn in turns:
        if turn.role != "user":
            continue
        for sentence in _sentences(turn.text):
            low = sentence.lower()
            taken: list[tuple[int, int]] = []
            for name, cat, patterns, clears in _compiled():
                for pat in patterns:
                    m = pat.search(low)
                    if not m or any(m.start() < e and s < m.end() for s, e in taken):
                        continue
                    if _negated(low, m.start()):
                        continue
                    taken.append((m.start(), m.end()))
                    cleared = any(c.search(low) for c in clears)
                    prev = found.get(name)
                    if prev is None or (prev.cleared and not cleared):
                        found[name] = Mention(name, cat["kind"], cat["label"], cat["rule"], _quote(sentence), cleared)
                    break
    return list(found.values())


def _contains_any(text: str, phrases: list[str]) -> bool:
    low = text.lower()
    return any(_phrase_pattern(p).search(low) for p in phrases)


def detect_mood(turns: list[Turn], mentions: list[Mention]) -> str:
    if any(m.kind in ("red", "safety") or (m.category in ("mood", "loneliness") and not m.cleared) for m in mentions):
        return "low"
    cheerful = [p for lang in flag_config()["cheerful"].values() for p in lang]
    for turn in turns:
        if turn.role != "user":
            continue
        for sentence in _sentences(turn.text):
            low = sentence.lower()
            for p in cheerful:
                m = _phrase_pattern(p).search(low)
                if m and not _negated(low, m.start()):
                    return "cheerful"
    return "okay"


def message_for_family(turns: list[Turn]) -> str | None:
    """The parent's reply to Smriti's fixed closing question, unless it is just 'no / nothing'."""
    cfg = flag_config()
    nothing = {p.lower() for lang in cfg["nothing_replies"].values() for p in lang}
    for i, turn in enumerate(turns):
        if turn.role != "agent" or not any(q in turn.text.lower() for q in cfg["close_question"]):
            continue
        reply = next((t for t in turns[i + 1 :] if t.role == "user"), None)
        if reply is None:
            return None
        text = reply.text.strip()
        # Strip punctuation only: Indic vowel signs are not \w, so a "keep word characters" rule breaks them.
        bare = " ".join(re.sub(r"[.,!?।;:\"“”‘’()\-]", " ", text.lower()).split())
        if not bare or bare in nothing or (len(bare.split()) <= 3 and bare.split()[0] in nothing):
            return None
        return _quote(text)
    return None


def analyze(
    turns: list[Turn], history: list[tuple[str, datetime]] | None = None, now: datetime | None = None
) -> Analysis:
    """history: (category, when) of earlier mentions for this parent, for the 'came up twice' rule."""
    cfg = flag_config()
    now = now or datetime.now()
    window = timedelta(days=int(cfg["repeat_days"]))
    mentions = find_mentions(turns)
    out = Analysis(mentions=mentions, mood=detect_mood(turns, mentions), message_for_family=message_for_family(turns))
    for m in mentions:
        if m.cleared:
            out.cleared.append(m.category)
            out.notes.append(f"Said their {m.label.lower()} is better: “{m.quote}”")
            continue
        if m.kind in ("red", "safety"):
            level = "red"
        elif m.kind == "yellow":
            level = "yellow"
        else:
            earlier = sum(1 for cat, when in (history or []) if cat == m.category and now - when <= window)
            level = "yellow" if earlier + 1 >= int(cfg["repeat_calls"]) else "green"
        rule = m.rule if level != "green" else f"{m.label} mentioned (noted)"
        out.flags.append(FlagOut(m.category, level, m.quote, rule, family_visible=m.kind != "safety"))
        if m.kind != "safety":
            out.notes.append(f"Mentioned {m.label.lower()}: “{m.quote}”")
    return out

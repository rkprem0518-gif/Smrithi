"""Bolna transcript -> turns -> task segments, using the agent's fixed marker phrases.

Bolna's GET /executions/{id} returns `transcript` as one string of role-prefixed lines:

    assistant: Namaste ...
    user: haan ji

Lines without a role prefix continue the previous turn. Role labels vary between
endpoints ("assistant"/"agent"/"bot", "user"/"human"), so all of them are accepted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from rapidfuzz import fuzz

from app.scoring.normalize import normalize_text
from app.scoring.types import TASKS, Segments, Turn

_ROLE_LINE = re.compile(r"^\s*(assistant|agent|bot|ai|user|human|customer|caller)\s*:\s?(.*)$", re.I)
_AGENT_ROLES = {"assistant", "agent", "bot", "ai"}
FUZZY_MARKER_THRESHOLD = 92
FLAGS = ("stopped", "declined")


def _role(label: str) -> str:
    return "agent" if label.lower() in _AGENT_ROLES else "user"


def parse_bolna_transcript(transcript: str | None) -> list[Turn]:
    turns: list[Turn] = []
    for line in (transcript or "").splitlines():
        m = _ROLE_LINE.match(line)
        if m:
            turns.append(Turn(_role(m.group(1)), m.group(2).strip()))
        elif line.strip() and turns:
            prev = turns[-1]
            turns[-1] = Turn(prev.role, f"{prev.text} {line.strip()}".strip(), prev.t)
    return [t for t in turns if t.text]


def turns_from_json(items: Sequence[Mapping[str, Any]]) -> list[Turn]:
    """Fixture / API format: [{"role": "assistant"|"user", "text": "...", "t": 12.5?}]."""
    out = []
    for item in items:
        text = str(item.get("text") or item.get("content") or "").strip()
        if text:
            t = item.get("t")
            out.append(Turn(_role(str(item.get("role", "user"))), text, float(t) if t is not None else None))
    return out


def turns_to_bolna_transcript(turns: Sequence[Turn]) -> str:
    return "\n".join(f"{'assistant' if t.role == 'agent' else 'user'}: {t.text}" for t in turns)


def _marker_position(text_key: str, phrase_keys: Sequence[str]) -> int | None:
    """Position of the marker inside the agent turn, or None. Exact first, then fuzzy."""
    padded = f" {text_key} "
    best: int | None = None
    for p in phrase_keys:
        idx = padded.find(f" {p} ")
        if idx >= 0:
            best = idx if best is None else max(best, idx)
    if best is not None:
        return best
    for p in phrase_keys:
        if len(p) >= 8:
            res = fuzz.partial_ratio_alignment(p, text_key, score_cutoff=FUZZY_MARKER_THRESHOLD)
            if res is not None:
                return res.dest_start
    return None


def segment(turns: Sequence[Turn], marker_phrases: Mapping[str, Sequence[str]]) -> Segments:
    """Assign each turn to a task. Tasks only move forward; the marker turn opens its task."""
    keyed = {name: [normalize_text(p) for p in phrases] for name, phrases in marker_phrases.items()}
    seg = Segments()
    current: str | None = None
    for turn in turns:
        if turn.role == "agent":
            text_key = normalize_text(turn.text)
            for flag in FLAGS:
                if flag in keyed and _marker_position(text_key, keyed[flag]) is not None:
                    setattr(seg, flag, True)
                    seg.markers_found.append(flag)
            hits = []
            for name in TASKS:
                if name in keyed:
                    pos = _marker_position(text_key, keyed[name])
                    if pos is not None:
                        hits.append((pos, name))
            for _, name in sorted(hits):
                if current is None or TASKS.index(name) > TASKS.index(current):
                    current = name
                    seg.markers_found.append(name)
                    seg.tasks.setdefault(name, [])
        if current is None:
            seg.preamble.append(turn)
        else:
            seg.tasks[current].append(turn)
    return seg

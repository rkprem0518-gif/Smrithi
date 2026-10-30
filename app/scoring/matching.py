"""Deterministic fuzzy matching of transcript tokens against word lists and lexicons."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.scoring.normalize import Token, tokenize

DEFAULT_THRESHOLD = 85
MIN_FUZZY_LEN = 3  # shorter keys must match exactly


@dataclass(frozen=True)
class Lexicon:
    """Maps phonetic keys (possibly multi-word) to a canonical id."""

    keys: dict[str, str]
    max_ngram: int = 1
    _choices: tuple[str, ...] = field(default=(), repr=False)

    @property
    def choices(self) -> tuple[str, ...]:
        return self._choices or tuple(self.keys)


def build_lexicon(groups: Mapping[str, Iterable[str]]) -> Lexicon:
    """`groups` maps canonical id -> spelling variants (Devanagari, Latin, English)."""
    keys: dict[str, str] = {}
    max_ngram = 1
    for canonical, variants in groups.items():
        for variant in [canonical, *variants]:
            toks = tokenize(str(variant))
            if not toks:
                continue
            key = " ".join(t.key for t in toks)
            keys.setdefault(key, canonical)
            max_ngram = max(max_ngram, len(toks))
    return Lexicon(keys=keys, max_ngram=max_ngram, _choices=tuple(keys))


@dataclass(frozen=True)
class Match:
    canonical: str
    surface: str
    score: float
    position: int  # token index in the scanned text


def match_key(key: str, lexicon: Lexicon, threshold: float = DEFAULT_THRESHOLD) -> tuple[str, float] | None:
    if key in lexicon.keys:
        return lexicon.keys[key], 100.0
    if len(key.replace(" ", "")) < MIN_FUZZY_LEN:
        return None
    best = process.extractOne(key, lexicon.choices, scorer=fuzz.ratio, score_cutoff=threshold)
    if best is None:
        return None
    return lexicon.keys[best[0]], float(best[1])


def find_matches(
    tokens: Sequence[Token],
    lexicon: Lexicon,
    threshold: float = DEFAULT_THRESHOLD,
    stopwords: frozenset[str] = frozenset(),
) -> tuple[list[Match], list[str]]:
    """Greedy left-to-right scan, longest n-gram first.

    Returns (matches in order, unmatched content tokens). Stopwords are never matched,
    so filler like English "am" cannot be read as the list word "aam".
    """
    matches: list[Match] = []
    unmatched: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i].stop_key in stopwords:
            i += 1
            continue
        hit: tuple[str, float, int] | None = None
        for n in range(min(lexicon.max_ngram, len(tokens) - i), 0, -1):
            window = tokens[i : i + n]
            if n > 1 and any(t.stop_key in stopwords for t in window):
                continue
            if n == 1:
                found = match_key(window[0].key, lexicon, threshold)
            else:
                # Multi-word windows match exactly only: fuzzy-matching glued neighbours
                # ("chhata rassi" ~ "chhatri") would swallow a correct second word.
                spaced, glued = " ".join(t.key for t in window), "".join(t.key for t in window)
                exact = lexicon.keys.get(spaced) or lexicon.keys.get(glued)
                found = (exact, 100.0) if exact else None
            if found is not None:
                hit = (found[0], found[1], n)
                break
        if hit is None:
            if len(tokens[i].raw) >= 3 and not tokens[i].raw.isdigit():
                unmatched.append(tokens[i].raw)
            i += 1
            continue
        canonical, score, n = hit
        matches.append(Match(canonical, " ".join(t.raw for t in tokens[i : i + n]), score, i))
        i += n
    return matches, unmatched


def unique_in_order(items: Iterable[str]) -> tuple[list[str], list[str]]:
    """(first occurrences in order, repeats)."""
    seen: set[str] = set()
    uniq: list[str] = []
    repeats: list[str] = []
    for item in items:
        if item in seen:
            repeats.append(item)
        else:
            seen.add(item)
            uniq.append(item)
    return uniq, repeats

"""Deterministic fuzzy matching of transcript tokens against word lists and lexicons.

Guards against false positives (found in peer review):
- Script-aware: a Devanagari token only matches keys that came from Devanagari variants,
  so रात is not "rat", बात is not "bat" and चार is not "chair".
- Keys shorter than 5 letters match exactly; longer ones fuzzily (ratio >= threshold)
  and only with the same first letter.
- Plural/oblique endings (किताबें, घोड़े, फूलों, रोटियाँ) are retried as exact matches.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.scoring.normalize import Token, tokenize

DEFAULT_THRESHOLD = 85
MIN_FUZZY_LEN = 5  # shorter keys must match exactly
MIN_INFLECTED_LEN = 5  # only strip endings from tokens at least this long

# (ending, replacements) tried in order; result must match exactly.
_ENDINGS = (
    ("iyan", ("i",)), ("iyam", ("i",)), ("iyon", ("i",)), ("iyom", ("i",)),
    ("en", ("", "a")), ("em", ("", "a")), ("on", ("", "a")), ("om", ("", "a")),
    ("e", ("a", "i", "")),
    ("galu", ("", "u")), ("gal", ("", "u")),  # Kannada plural: ನಾಯಿಗಳು, ಮರಗಳು
)


@dataclass(frozen=True)
class Lexicon:
    """Maps phonetic keys (possibly multi-word) to a canonical id."""

    keys: dict[str, str]  # every key (Latin tokens may match any of them)
    deva_keys: dict[str, str] = field(default_factory=dict)  # keys from Devanagari variants
    knda_keys: dict[str, str] = field(default_factory=dict)  # keys from Kannada variants
    max_ngram: int = 1
    _choices: tuple[str, ...] = field(default=(), repr=False)
    _deva_choices: tuple[str, ...] = field(default=(), repr=False)
    _knda_choices: tuple[str, ...] = field(default=(), repr=False)

    @property
    def choices(self) -> tuple[str, ...]:
        return self._choices or tuple(self.keys)

    def for_script(self, script: str | bool) -> tuple[dict[str, str], tuple[str, ...]]:
        """Indic tokens only match keys from the same script; Latin tokens match everything."""
        if script is True or script == "deva":
            return self.deva_keys, self._deva_choices or tuple(self.deva_keys)
        if script == "knda":
            return self.knda_keys, self._knda_choices or tuple(self.knda_keys)
        return self.keys, self.choices


def build_lexicon(groups: Mapping[str, Iterable[str]]) -> Lexicon:
    """`groups` maps canonical id -> spelling variants (Devanagari, Latin, English)."""
    keys: dict[str, str] = {}
    deva_keys: dict[str, str] = {}
    knda_keys: dict[str, str] = {}
    max_ngram = 1
    for canonical, variants in groups.items():
        for variant in [canonical, *variants]:
            toks = tokenize(str(variant))
            if not toks:
                continue
            key = " ".join(t.key for t in toks)
            keys.setdefault(key, canonical)
            if all(t.script == "deva" for t in toks):
                deva_keys.setdefault(key, canonical)
            if all(t.script == "knda" for t in toks):
                knda_keys.setdefault(key, canonical)
            max_ngram = max(max_ngram, len(toks))
    return Lexicon(keys=keys, deva_keys=deva_keys, knda_keys=knda_keys, max_ngram=max_ngram,
                   _choices=tuple(keys), _deva_choices=tuple(deva_keys), _knda_choices=tuple(knda_keys))


@dataclass(frozen=True)
class Match:
    canonical: str
    surface: str
    score: float
    position: int  # token index in the scanned text


def _inflection_candidates(key: str) -> list[str]:
    out = [key[:-1]] if len(key) >= 4 and key.endswith("s") else []  # English plural: dogs, keys, trees
    if len(key) < MIN_INFLECTED_LEN:
        return out
    for ending, replacements in _ENDINGS:
        if key.endswith(ending):
            stem = key[: -len(ending)]
            out.extend(stem + r for r in replacements if len(stem + r) >= 3)
    return out


def match_key(
    key: str, lexicon: Lexicon, threshold: float = DEFAULT_THRESHOLD, deva: str | bool = False
) -> tuple[str, float] | None:
    keys, choices = lexicon.for_script(deva)
    if key in keys:
        return keys[key], 100.0
    for cand in _inflection_candidates(key):
        if cand in keys:
            return keys[cand], 99.0
    if len(key.replace(" ", "")) < MIN_FUZZY_LEN or not choices:
        return None
    # Both sides must be long enough: a short lexicon key (kuri) must not absorb a longer word (kursi).
    same_initial = [c for c in choices if c[:1] == key[:1] and len(c.replace(" ", "")) >= MIN_FUZZY_LEN]
    best = process.extractOne(key, same_initial, scorer=fuzz.ratio, score_cutoff=threshold)
    if best is None:
        return None
    return keys[best[0]], float(best[1])


def find_matches(
    tokens: Sequence[Token],
    lexicon: Lexicon,
    threshold: float = DEFAULT_THRESHOLD,
    stopwords: frozenset[str] = frozenset(),
) -> tuple[list[Match], list[str]]:
    """Greedy left-to-right scan, longest n-gram first.

    Returns (matches in order, unmatched content tokens). Stopwords are never matched.
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
            scripts = {t.script for t in window}
            deva = scripts.pop() if len(scripts) == 1 else "latin"
            if n == 1:
                found = match_key(window[0].key, lexicon, threshold, deva)
            else:
                # Multi-word windows match exactly only: fuzzy-matching glued neighbours
                # ("chhata rassi" ~ "chhatri") would swallow a correct second word.
                if any(t.stop_key in stopwords for t in window):
                    continue
                keys, _ = lexicon.for_script(deva)
                exact = keys.get(" ".join(t.key for t in window)) or keys.get("".join(t.key for t in window))
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

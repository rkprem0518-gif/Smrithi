"""Text normalisation: Devanagari -> Latin, lowercase, strip punctuation, phonetic keys.

Matching never needs a linguistically perfect transliteration, only a *consistent* one:
word lists, lexicons, marker phrases and transcripts all go through `tokenize`, so a
Devanagari word and its Latin spelling end up with the same (or a fuzzily close) key.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

# Devanagari block minus the dandas (। ॥), plus zero-width (non-)joiners used inside words.
_WORD = re.compile(r"[ऀ-ॣ०-ॿ‌‍]+|[ಀ-೿]+|[A-Za-z0-9]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_VIRAMA = "्"
_NUKTA = "़"
# Anusvara before a stop is pronounced as a nasal "n" (पंखा = pankha, not pamkha).
_ANUSVARA_N = re.compile(r"m(?=[kgcjtd])")
_RUNS = re.compile(r"(.)\1+")
_CANDRA = str.maketrans({"ॉ": "ो", "ऑ": "ओ", "ॅ": "े", "ऍ": "ए"})


def _is_consonant(ch: str) -> bool:
    return "क" <= ch <= "ह" or "क़" <= ch <= "य़"


def _is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


@lru_cache(maxsize=8192)
def deva_word_to_latin(word: str) -> str:
    """Transliterate one Devanagari word to lowercase Latin, dropping the final schwa."""
    word = word.replace("‌", "").replace("‍", "")
    # ITRANS has no mapping for the "candra" vowels used in English loanwords (वॉटर, डॉग, कॅट).
    word = word.translate(_CANDRA)
    if not word:
        return ""
    last = word[-1]
    if _is_consonant(last) or (last == _NUKTA and len(word) > 1 and _is_consonant(word[-2])):
        word = word + _VIRAMA  # घर -> ghar, not ghara
    latin = transliterate(word, sanscript.DEVANAGARI, sanscript.ITRANS)
    # ITRANS uses . ~ ^ as diacritic markers (पेड़ -> pe.D); they are not punctuation here.
    latin = latin.replace(".", "").replace("~", "").replace("^", "")
    return latin.lower()


@lru_cache(maxsize=8192)
def kannada_word_to_latin(word: str) -> str:
    """Kannada keeps its final vowel (ಮರ = mara), so no schwa handling; ITRANS writes short e/o
    as è/ò, which are folded to plain e/o."""
    latin = transliterate(word.replace("\u200c", "").replace("\u200d", ""), sanscript.KANNADA, sanscript.ITRANS)
    latin = latin.replace(".", "").replace("~", "").replace("^", "")
    latin = "".join(ch for ch in unicodedata.normalize("NFKD", latin) if not unicodedata.combining(ch))
    return latin.lower()


def _is_kannada(ch: str) -> bool:
    return "\u0c80" <= ch <= "\u0cff"


def phonetic_key(token: str) -> str:
    """Collapse spelling variation: ee->i, oo->u, w->v, z->j, doubled letters -> single."""
    key = token.lower()
    key = key.replace("ee", "i").replace("oo", "u")
    key = key.replace("w", "v").replace("z", "j").replace("q", "k")
    key = _ANUSVARA_N.sub("n", key)
    key = _RUNS.sub(r"\1", key)
    return key


@dataclass(frozen=True)
class Token:
    raw: str  # lowercase Latin surface form (used for digits and display)
    key: str  # phonetic key (used for matching)
    deva: bool = False  # came from an Indic script (Devanagari or Kannada), not Latin
    orig: str = ""  # the Indic word as written (Indic tokens only)
    script: str = "latin"  # latin | deva | knda

    @property
    def stop_key(self) -> str:
        # Devanagari stopwords compare on the original spelling: आम ("aam", mango) must not be
        # dropped as the English "am", and दीया (lamp) must not be dropped as दिया (gave),
        # although both transliterate to "diya".
        return f"deva:{self.orig}" if self.deva else self.raw


def tokenize(text: str) -> list[Token]:
    out: list[Token] = []
    for m in _WORD.finditer(unicodedata.normalize("NFC", text or "")):
        word = m.group(0)
        if _is_kannada(word[0]):
            for part in _NON_ALNUM.sub(" ", kannada_word_to_latin(word)).split():
                out.append(Token(part, phonetic_key(part), True, word, "knda"))
        elif _is_devanagari(word[0]) or word[0] in "‌‍":
            for part in _NON_ALNUM.sub(" ", deva_word_to_latin(word)).split():
                out.append(Token(part, phonetic_key(part), True, word, "deva"))
        else:
            low = word.lower()
            out.append(Token(low, phonetic_key(low), False))
    return out


def stop_keys(latin: list[str], devanagari: list[str]) -> frozenset[str]:
    """Build the stopword set for Token.stop_key lookups."""
    keys = {str(w).lower() for w in latin}
    keys |= {t.stop_key for w in devanagari for t in tokenize(str(w))}
    return frozenset(keys)


def normalize_text(text: str) -> str:
    """Space-joined phonetic keys; used for marker-phrase matching."""
    return " ".join(t.key for t in tokenize(text))

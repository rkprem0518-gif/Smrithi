"""Optional timestamped ASR over the call recording, to time the 60-second animal-naming window.

Bolna's execution transcript is a plain string without per-turn timestamps, so the fluency
count normally covers the whole animal-naming segment (`experimental_timing: true`).
With ASR_PROVIDER=deepgram, we re-transcribe the recording with word timestamps, find the
animal-naming marker, and return each word with its time since the first animal named.
Any failure returns None and scoring falls back to the whole segment.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.logs import log
from app.scoring.matching import Lexicon, match_key
from app.scoring.normalize import normalize_text, tokenize
from app.settings import Settings

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def window_from_words(
    words: list[tuple[str, float]],
    start_markers: list[str],
    end_markers: list[str],
    animal_lexicon: Lexicon,
    threshold: float,
) -> list[tuple[str, float]] | None:
    """Pure helper: words after the start marker and before the end marker, timed from the first animal."""
    toks = [(tok.key, w, t) for w, t in words for tok in tokenize(w)]
    keys = [k for k, _, _ in toks]
    marker_keys = {
        name: [normalize_text(m).split() for m in ms if normalize_text(m)]
        for name, ms in (("start", start_markers), ("end", end_markers))
    }

    def find(name: str, after: int) -> tuple[int, int] | None:
        for i in range(after, len(keys)):
            for mk in marker_keys[name]:
                if keys[i : i + len(mk)] == mk:
                    return i, i + len(mk)
        return None

    start = find("start", 0)
    if start is None:
        return None
    end = find("end", start[1])
    segment = toks[start[1] : end[0] if end else len(toks)]
    t0 = next((t for key, _, t in segment if match_key(key, animal_lexicon, threshold)), None)
    if t0 is None:
        return None
    return [(w, round(t - t0, 2)) for _, w, t in segment if t >= t0]


async def deepgram_words(recording_url: str, api_key: str) -> list[tuple[str, float]]:
    params = {"model": "nova-3", "language": "multi", "punctuate": "false"}
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.post(
            DEEPGRAM_URL, params=params, json={"url": recording_url},
            headers={"Authorization": f"Token {api_key}"},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    alt = data["results"]["channels"][0]["alternatives"][0]
    return [(w.get("punctuated_word") or w["word"], float(w["start"])) for w in alt.get("words", [])]


async def fluency_timestamps(
    recording_url: str | None,
    settings: Settings,
    markers: dict[str, list[str]],
    animal_lexicon: Lexicon,
    threshold: float,
) -> list[tuple[str, float]] | None:
    if settings.asr_provider == "none" or not recording_url:
        return None
    try:
        if settings.asr_provider == "deepgram" and settings.deepgram_api_key:
            words = await deepgram_words(recording_url, settings.deepgram_api_key)
        else:
            # TODO(sarvam): Sarvam's batch STT with timestamps needs a file upload job;
            # not wired yet. Use ASR_PROVIDER=deepgram for timing.
            log("asr_provider_not_implemented", provider=settings.asr_provider)
            return None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        # TODO(bolna): confirm recording_url is fetchable without auth by a third party.
        log("asr_failed", provider=settings.asr_provider, error=type(exc).__name__)
        return None
    return window_from_words(words, markers["fluency"], markers["orientation"], animal_lexicon, threshold)

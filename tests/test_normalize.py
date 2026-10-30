import pytest

from app.scoring.matching import build_lexicon
from app.scoring.normalize import deva_word_to_latin, normalize_text, phonetic_key, tokenize


@pytest.mark.parametrize(
    ("deva", "latin"),
    [
        ("घर", "ghar"),
        ("पानी", "paani"),
        ("पेड़", "ped"),
        ("चाँद", "chaand"),
        ("पंखा", "pankha"),
        ("छाता", "chhata"),
        ("मेज़", "mez"),
        ("घड़ी", "ghadi"),
        ("किताब", "kitaab"),
    ],
)
def test_devanagari_and_latin_spellings_share_a_key(deva: str, latin: str) -> None:
    assert normalize_text(deva) == normalize_text(latin)


def test_medial_schwa_is_close_enough_for_fuzzy_match(cfg) -> None:
    # दरवाज़ा -> "daravaja" vs darwaza -> "darvaja": not identical, but within the fuzzy threshold.
    from app.scoring.matching import match_key

    assert match_key(normalize_text("दरवाज़ा"), build_lexicon({"darwaza": []}))[0] == "darwaza"


def test_final_schwa_is_dropped() -> None:
    assert deva_word_to_latin("घर") == "ghar"
    assert deva_word_to_latin("किताब") == "kitAb".lower()


def test_punctuation_and_case_are_stripped() -> None:
    assert [t.raw for t in tokenize("Ghar, PAANI... ped!")] == ["ghar", "paani", "ped"]


def test_danda_is_punctuation() -> None:
    assert [t.raw for t in tokenize("घर। पानी॥")] == ["ghar", "pani"]


def test_devanagari_digits_become_ascii() -> None:
    assert [t.raw for t in tokenize("४ ७ २")] == ["4", "7", "2"]


def test_phonetic_key_collapses_spelling_variants() -> None:
    assert phonetic_key("paanee") == phonetic_key("pani")
    assert phonetic_key("phool") == phonetic_key("phul")
    assert phonetic_key("darwaza") == phonetic_key("darvaja")


def test_tokens_remember_their_script() -> None:
    deva, latin = tokenize("आम am")
    assert deva.deva and not latin.deva
    assert deva.raw == latin.raw == "am"
    assert deva.stop_key != latin.stop_key


def test_empty_input() -> None:
    assert tokenize("") == []
    assert tokenize(None) == []  # type: ignore[arg-type]

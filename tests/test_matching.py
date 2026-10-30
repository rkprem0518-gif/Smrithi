from app.scoring.matching import build_lexicon, find_matches, match_key, unique_in_order
from app.scoring.normalize import tokenize


def words(text, lexicon, cfg):
    matches, _ = find_matches(tokenize(text), lexicon, cfg.threshold, cfg.stopwords)
    return [m.canonical for m in matches]


def test_exact_devanagari_latin_and_english_all_match(cfg) -> None:
    lx = cfg.form_lexicons["A"]
    assert words("घर ghar house", lx, cfg) == ["ghar", "ghar", "ghar"]


def test_fuzzy_match_accepts_asr_misspellings(cfg) -> None:
    lx = cfg.form_lexicons["A"]
    assert words("kitaabe chabhi kurshi", lx, cfg) == ["kitaab", "chaabi", "kursi"]


def test_fuzzy_threshold_rejects_unrelated_words(cfg) -> None:
    lx = cfg.form_lexicons["A"]
    assert words("gaadi bandar machhli", lx, cfg) == []


def test_short_keys_need_exact_match() -> None:
    lx = build_lexicon({"aam": ["mango"]})
    assert match_key("am", lx) == ("aam", 100.0)
    assert match_key("ma", lx) is None


def test_english_stopword_am_is_not_mango_but_devanagari_aam_is(cfg) -> None:
    lx = cfg.form_lexicons["B"]
    assert words("I am not sure", lx, cfg) == []
    assert words("आम", lx, cfg) == ["aam"]
    assert words("aam", lx, cfg) == ["aam"]


def test_neighbouring_words_are_not_glued_together(cfg) -> None:
    lx = cfg.form_lexicons["C"]
    assert words("chhata, rassi... botal", lx, cfg) == ["chhata", "rassi", "botal"]


def test_multiword_variant_matches(cfg) -> None:
    lx = cfg.form_lexicons["C"]
    assert words("sun light", lx, cfg) == ["dhoop"]


def test_intrusions_are_reported_not_matched(cfg) -> None:
    lx = cfg.form_lexicons["A"]
    matches, unmatched = find_matches(tokenize("ghar, nadi, kursi"), lx, cfg.threshold, cfg.stopwords)
    assert [m.canonical for m in matches] == ["ghar", "kursi"]
    assert unmatched == ["nadi"]


def test_animal_synonyms_share_one_group(cfg) -> None:
    lx = cfg.animal_lexicon
    assert words("kutta dog कुत्ता", lx, cfg) == ["dog", "dog", "dog"]


def test_unique_in_order() -> None:
    assert unique_in_order(["a", "b", "a", "c", "b"]) == (["a", "b", "c"], ["a", "b"])

# Scoring specification (scorer `0.1.0-pilot`)

> **PILOT. Not validated. Never a diagnosis.** Every number here is a placeholder in
> [`config/scoring.yaml`](../config/scoring.yaml) to be re-derived with clinicians from local data.

Scoring is deterministic: the same transcript always gives the same result. No LLM is used to score. Every outcome stores its evidence (matched words per trial, animals counted, orientation answers, hearing responses) and the exact rule that fired.

## 1. From call to segments

Bolna returns the transcript as one string of `assistant: …` / `user: …` lines ([`segmenter.py`](../app/services/segmenter.py)). Lines without a prefix continue the previous turn.

The agent says a fixed **marker phrase** at the start of each task ([`config/agent.json`](../config/agent.json) → `smriti_markers`, also in the prompt):

| Task | Hindi | English |
|---|---|---|
| hearing | पहला काम | Task one |
| schooling | दूसरा काम | Task two |
| learning | तीसरा काम | Task three |
| fluency | चौथा काम | Task four |
| orientation | पाँचवाँ काम | Task five |
| recall | छठा काम | Task six |
| close | आख़िरी सवाल | Last question |
| stopped (distress) | हम यहीं रुकते हैं | Let us stop here |
| declined | आज जाँच नहीं करेंगे | We will not do the check today |

Each agent turn is checked for markers (exact match on normalised text, then fuzzy ≥ 92 for longer phrases). Tasks only move forward; a marker turn opens its task; turns before the first marker are the consent preamble.

## 2. Normalisation and matching

[`normalize.py`](../app/scoring/normalize.py), [`matching.py`](../app/scoring/matching.py)

1. Unicode NFC; Devanagari words are transliterated (ITRANS) with the final schwa dropped (घर → ghar), lowercased, punctuation removed. Dandas (। ॥) are punctuation.
2. A **phonetic key** collapses spelling variation: `ee→i`, `oo→u`, `w→v`, `z→j`, anusvara before a stop → `n` (पंखा → pankha), doubled letters → single.
3. Each token is looked up exactly, then (plural/oblique endings stripped: -en, -on, -iyan, -e, -s, Kannada -galu) exactly again, then with **rapidfuzz ratio ≥ 85** and the same first letter, only when both keys have 5+ letters. Devanagari tokens match only Devanagari-derived spellings and Kannada tokens only Kannada ones (so रात is never "rat"); Latin tokens match everything. Multi-word variants ("sun light") match exactly only, so two neighbouring list words are never glued into one.
4. **Stopwords** are never matched. Latin and Devanagari stopwords are kept apart, so आम ("aam", mango) is not dropped as the English word "am".
5. Each word counts **once per trial**. Words that do not match the active form are logged as **intrusions** (shown on the report, not counted).

## 3. Tasks

| Task | How it is scored |
|---|---|
| Hearing | The agent reads 4-7-2, 3-9-5, 8-1-6. For each, the user turns between the agent turn containing that string and the next one are searched for the digits (spoken as digits, Hindi or English number words, or Devanagari numerals). A retry counts. **< 2 of 3 → INVALID**. |
| Schooling | The UI value wins if given. Otherwise the first number in the answer (digits, number words, class names like आठवीं / 12th / BA). A negation without a number ("कभी स्कूल नहीं गई") = 0. Unknown → **LOW band, flagged "assumed"**. LOW ≤ 10 years, HIGH > 10. |
| Word learning | Every agent turn that names ≥ 5 list words is a *reading* and starts a trial; user turns after it belong to that trial. 3 trials, 0–10 each, total 0–30. |
| Animal naming | Unique synonym groups from [`animals.yaml`](../config/animals.yaml) (kutta = dog = कुत्ता counts once). Birds, fish, insects count. Non-animals are listed, not counted. Without timestamps the whole segment is counted (`experimental_timing: true`). With `ASR_PROVIDER=deepgram`, only words within 60 s of the first animal count. |
| Orientation | Checked against the call time in **IST**. Day of week; month (Gregorian **or** either of the two overlapping traditional months, e.g. October = आश्विन/कार्तिक); season (lenient: neighbouring seasons accepted, e.g. October = autumn/winter/monsoon); time of day (morning 5–12, afternoon 12–16, evening 16–20, night 20–5, ±45 min at boundaries); town/village (accepted if a place is named; **not verifiable**, flagged for the reviewer). If the person corrects themselves, the last answer counts. |
| Delayed recall | Unique list words named after the recall marker, 0–10. |
| Helper | Answer to "was anyone helping you answer?" Yes (and no negation) → **INVALID**. |

## 4. Outcome

| Band | REFER | UNCERTAIN | NORMAL |
|---|---|---|---|
| LOW (≤ 10 yrs) | DR ≤ 2 | DR = 3, or DR ≥ 4 with F < 8 **and** O ≤ 3 | DR ≥ 4 otherwise |
| HIGH (> 10 yrs) | DR ≤ 3 | DR = 4, or DR ≥ 5 with F < 11 **and** O ≤ 3 | DR ≥ 5 otherwise |

DR = delayed recall, F = animals named, O = orientation. The learning total is shown as primary evidence but no pilot rule uses it yet.

**INVALID** (checked first, overrides everything):

| Code | Rule |
|---|---|
| `hearing_check_failed` | fewer than 2 of 3 digit strings repeated |
| `ended_before_delayed_recall` | no recall segment, or no user turn in it |
| `too_many_empty_answers` | > 30% of the 14 expected answers (3 hearing + 1 schooling + 3 trials + 1 fluency + 5 orientation + 1 recall) empty or unintelligible ("I don't know" counts as an answer) |
| `helper_present` | the person said someone was helping |
| `stopped_distress` | the agent said the stop marker |

UNCERTAIN, REFER and INVALID always go to the reviewer queue.

## 5. Experimental speech markers

Answers given, mean words per answer, filler-word rate, "I don't know" count, mean response latency (only when timestamps exist). Shown collapsed on the report, labelled experimental, and **never used for the outcome** (the engine computes the outcome before and independently of them).

## 6. Worked examples (the four fixtures)

| Fixture | Form | Band | Hearing | Trials | Animals | Orientation | DR | Outcome | Rule fired |
|---|---|---|---|---|---|---|---|---|---|
| [normal](../fixtures/normal.json) | A | LOW (8 yrs, said) | 3/3 | 5, 7, 8 = 20 | 15 | 5 | 6 | NORMAL | `LOW band: delayed recall = 6 (>= 4)` |
| [uncertain](../fixtures/uncertain.json) | B | LOW (never went) | 3/3 | 3, 4, 5 = 12 | 7 | 4 (कार्तिक accepted) | 3 | UNCERTAIN | `LOW band: delayed recall = 3` |
| [refer](../fixtures/refer.json) | C | HIGH (12th) | 3/3 (retry) | 2, 3, 4 = 9 | 6 | 1 | 2 | REFER | `HIGH band: delayed recall = 2 (<= 3)` |
| [invalid_hearing](../fixtures/invalid_hearing.json) | A | LOW (5, UI) | 1/3 | 4, 5, 6 = 15 | 9 | 5 | 5 | INVALID | `INVALID: hearing_check_failed` |

Try your own transcript without a database or keys:

```bash
curl -X POST localhost:8000/api/demo/score -H "Content-Type: application/json" \
  -d '{"transcript": "assistant: पहला काम। चार सात दो\nuser: चार सात दो", "word_form": "A"}'
```

## 7. Word lists

Original, culturally familiar, concrete, **no animals** (so they cannot clash with task 4), no overlap between forms. [`config/wordlists.yaml`](../config/wordlists.yaml).

| Form | Words |
|---|---|
| A | ghar, paani, ped, roti, kitaab, chaabi, darwaza, chaand, kursi, phool |
| B | nadi, chappal, aam, ghadi, gilaas, thali, baadal, sabun, taala, pankha |
| C | dibba (box), rassi, chhata, patta, bazaar, kapda, dhoop, chammach, botal, mez |

Every word also has a Kannada form (`kn`), read aloud on Kannada calls: A = ಮನೆ, ನೀರು, ಮರ, ರೊಟ್ಟಿ, ಪುಸ್ತಕ, ಕೀಲಿ, ಬಾಗಿಲು, ಚಂದ್ರ, ಕುರ್ಚಿ, ಹೂವು. Form C's lamp (दीया) was replaced by box (डिब्बा) because speech-to-text writes it the same as दिया ("gave").

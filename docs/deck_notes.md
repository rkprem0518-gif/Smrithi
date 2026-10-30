# Deck notes

Numbers and screenshots for the pitch deck. **Verify every external statistic against its source before putting it on a slide.**

## Problem (verify before use)

- India's LASI-DAD study (Lee et al., *Alzheimer's & Dementia*, 2023) estimated dementia prevalence of about **7.4% in adults 60+**, roughly **8.8 million people**. Most are never assessed.
- Standard screening tests assume literacy and a clinic visit; many older Indians have little schooling and live far from a memory clinic.
- The 10/66 Dementia Research Group built assessment approaches that work for people with little or no education. Smriti borrows that idea and puts it on a phone call.

## What we built (verifiable in this repo)

- A 5-minute voice check in Hindi/English on Bolna: hearing check, schooling, 10-word list × 3, 1-minute animal naming, orientation, delayed recall.
- Deterministic, explainable scoring: 30 list words across 3 forms, ~70 animal synonym groups, 14 expected answers, 5 INVALID rules, every score with its evidence and the rule that fired.
- Human-in-the-loop reviewer queue for every Uncertain / Refer / Invalid result.
- Privacy by design: double consent, hashed phone numbers, delete-my-data, redacted logs.
- Offline demo with 4 realistic Hinglish calls scored by the real engine; full test suite (run `pytest` for the current count), Bolna mocked with respx.

## Bolna features used

Agent API v2 · outbound calls with `user_data` dynamic variables (one agent, 3 word forms) · executions API · webhooks + polling fallback · `/user/me` readiness check · Sarvam Saaras STT + Bulbul TTS for Hindi · call controls (silence timeout for the 1-minute task, max call length) · Web Call SDK (optional).

## Live numbers to fill after the first calls

| Metric | Value |
|---|---|
| Real calls completed | |
| Median call length | |
| Cost per call (Bolna `total_cost`) | |
| ASR misses per call (list words) | |
| Marker phrases detected / expected | |

## Screenshots to take

1. Home page (English) with "not a diagnosis" banner.
2. Start page with consent box.
3. Live page mid-call (stepper).
4. Report: UNCERTAIN, Hindi, word chips per trial with the intrusion shown.
5. Report: INVALID (hearing check failed) with the reason.
6. Reviewer queue with transcript open.
7. Terminal: `python scripts/check_live.py` → READY, and `pytest` all green.

## One-liner

"A 5-minute phone call in Hindi that tells a family whether to see a doctor about memory, fairly, even for people who never went to school, and never pretends to diagnose."

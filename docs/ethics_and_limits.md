# Ethics and limits

## What Smriti is, and is not

- A **pilot memory check** that helps a family or clinic decide whether to see a doctor. It produces one of: Normal, Uncertain - retest, Refer to clinician, Invalid call.
- **Not a diagnosis.** It never names a disease. The agent is instructed never to say "dementia", "Alzheimer", "disease" or "बीमारी", and every report says "not a diagnosis".
- **Not validated.** The tasks are inspired by the 10/66 Dementia Research Group battery, but the word lists, the animal lexicon and every cutoff are our own pilot placeholders. They have not been tested against clinical assessments.

## Consent

- **Twice:** the person starting the check ticks a consent box (with the older person's permission), and the agent asks the older person for a spoken yes at the start of the call, telling them it is a memory check, not a medical test, and that the call is recorded.
- No, or unsure after one clarification → the agent ends politely, nothing is scored, the session is `declined`.
- The person can stop at any time. Signs of distress → the agent stops, reassures, and the session is `stopped` (never scored as a result).

## Human in the loop

Every UNCERTAIN, REFER and INVALID result goes to a reviewer queue with the transcript, the recording and the evidence. Reviewers can agree, override, or ask for a retest. Pilot deployments must have a named, trained reviewer.

## Privacy

- Data minimisation: the phone number is used to place the call and then kept only as a salted hash plus the last 4 digits. No names are collected.
- Data stays in the app's own SQLite database. Logs carry ids only; phone-number-like strings and transcript fields are redacted.
- "Delete this data" (`DELETE /api/sessions/{id}`) removes the transcript, recording link and scores.
- Audio is held by Bolna (recording URL). A real deployment needs a data-processing agreement and a retention policy with the voice provider.
- India's **Digital Personal Data Protection Act 2023** applies to real use: purpose limitation, consent notices in the person's language, and grievance contact.

## Fairness and bias

- **Education:** the 10/66 approach was designed for people with little or no schooling. No reading or writing is needed; schooling bands change the cutoffs; "none" is a normal answer.
- **Culture and language:** familiar everyday words, Hinglish accepted, traditional month names (कार्तिक) accepted, lenient season answers.
- **Known risks:** speech recognition is less accurate for older voices, strong regional accents, dentures, hearing loss and noisy or weak phone lines. These can lower scores for reasons unrelated to memory. Mitigations: the hearing/line check, the INVALID rules, fuzzy matching, and human review. These reduce but do not remove the bias.
- **Access:** phone-based checks exclude people without a phone or privacy at home; the helper question flags assisted answers, but cannot detect all of them.
- **Gender and region:** cutoffs must be checked separately by gender, region and education in any validation study.

## Safety

- Helplines are shown only from `HELPLINE_TEXT`, which must be filled with a verified number. We do not ship a default number.
- A REFER result is phrased to reduce alarm: many causes of memory problems (hearing, mood, sleep, medicines, vitamin levels) are treatable.

## Regulation (India)

- Software intended to screen for or help diagnose a disease is likely **Software as a Medical Device** under the Medical Devices Rules 2017, regulated by **CDSCO**. Smriti makes no clinical claim today; any clinical use needs that pathway first.
- A pilot with real participants needs approval from an Institutional Ethics Committee, following the ICMR National Ethical Guidelines for biomedical and health research involving human participants.

## Limits of this version

- Pilot cutoffs; no normative data.
- Animal naming is not timed to exactly 60 s unless the optional ASR pass runs.
- The town/village answer is not verified automatically.
- Hindi and English only.
- One call is a snapshot: mood, tiredness and the phone line all affect it. Retesting is part of the design.

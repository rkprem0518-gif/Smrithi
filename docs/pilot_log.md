# Pilot log (anonymised)

Use one row per call. **No names, no phone numbers, no addresses.** Use the Smriti `session_id` (or its first 8 characters) to link to the report. Get consent from the participant (and the caregiver) before each call, and ethics approval before any pilot beyond the team's own families.

## Summary (fill in after the pilot)

| Metric | Value |
|---|---|
| Calls attempted | |
| Calls completed (reached delayed recall) | |
| Completion rate | |
| Median call duration (min) | |
| Outcome mix (NORMAL / UNCERTAIN / REFER / INVALID / declined / stopped) | |
| INVALID reasons (hearing / ended early / empty answers / helper) | |
| Participants with ≤ 5 years of schooling: completed / attempted | |
| Non-readers: completed / attempted, any task they struggled with | |
| Reviewer agreement with the automatic outcome | |
| Median Bolna cost per call | |

## Calls

| # | Date | session_id | Language | Age band (60-69 / 70-79 / 80+) | Schooling yrs | Reads? (y/n) | Phone type / line quality | Duration (min) | Status | Outcome | Rule fired | Reviewer decision | Transcript problems (ASR misses, marker missed) | Participant / caregiver feedback |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | | | | | | |
| 2 | | | | | | | | | | | | | | |
| 3 | | | | | | | | | | | | | | |
| 4 | | | | | | | | | | | | | | |
| 5 | | | | | | | | | | | | | | |

## Things to watch

- Did the agent say every marker phrase exactly? (If not, add the variant to `config/agent.json` → `smriti_markers`.)
- Words the ASR got wrong: add real spellings to `config/wordlists.yaml` `variants` or `config/animals.yaml`.
- Did anyone find a task confusing, too fast, or upsetting?
- Was 25 s `hangup_after_silence` long enough during animal naming?

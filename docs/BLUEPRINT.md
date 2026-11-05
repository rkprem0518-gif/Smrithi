# Smriti blueprint

Status: foundation document, written 5 Nov 2026 after the first live calls, team discussion and three research passes.
Everything we build next should sit on top of this. Change it only on purpose, in a commit that says why.

---

## 1. The soul of the product (does not change)

> **Smriti is a friend who calls your parents every week, in their own language, remembers what they told her,
> and makes sure the family acts when something matters. We start with memory.**

Five promises we never break:

1. **The parent comes first.** The parent agrees, the parent decides what is shared, the parent can stop at any time.
   A son or daughter can never override the parent's "no".
2. **We never diagnose.** Smriti notices and passes it on. Doctors diagnose. Words we never use about a person:
   "dementia", "disease", "you have", "screening result".
3. **Fixed rules decide, not the AI's mood.** The memory check is scored by fixed rules, and flags are raised by fixed
   rules. The same answers always give the same result.
4. **A person checks before anyone is worried.** Every serious flag and every memory-check concern is seen by a human
   before the family gets a call.
5. **It is a conversation, not an interrogation.** The parent can talk first, ask things, and say "not today".

---

## 2. Who uses it

| Role | What they use | What they can do | What they can NOT do |
|---|---|---|---|
| **Parent / grandparent** (the owner) | Only phone calls. No app, no smartphone needed. | Talk, report anything, say "call me later", "stop the calls", "don't tell my son about this", "tell my daughter I'm fine", choose language and what gets shared. | Nothing is hidden from them: Smriti says it is an AI and says what it will share. |
| **Family contact** (son, daughter, grandchild) | Family app (web for now). | See the timeline and flags the parent allowed, read "what Appa wants you to know", suggest call times, request a memory check (the parent must agree on the call), get a phone call from Smriti when something matters. | Read raw transcripts, change the parent's sharing choice, force calls the parent refused. |
| **Care desk** (the human reviewer) | Care desk screen (the current review queue, grown). | See red/yellow flags and memory-check results first, listen to the exact audio moment, approve or dismiss, trigger the family call, note follow-ups. | Diagnose. Share anything the parent did not allow (except a real emergency, see 6.4). |
| **Admin** (us) | Admin page. | Agents, costs, failed calls, consent logs. | — |

**Who is the care desk?**
- Demo and pilot: our own team.
- Next: a partner's care managers. Elder-care companies that already run care managers or community managers are
  the natural fit (for example Emoha, Anvayaa, KITES Senior Care in Bengaluru; verify each before approaching).
- The software is the same; only who logs in changes. So we can sell to families **and** to care companies.

**Family conflict rule:** when the parent and the family disagree, the parent wins. The family sees *that* a call
happened and the parent's chosen level of detail, never more.

---

## 3. One call, three parts

Every call has the same shape. Only the middle changes.

```
1. OPEN TALK      "How have you been since we spoke? Anything you'd like to tell me?"     (1–2 min)
                  The parent leads. Smriti listens, remembers last week, follows up gently.
2. TODAY'S PART   Weekly: one light topic from the playbook (festival, grandchildren, food, walk, cricket).
                  Every few months: the memory check (exactly as built today, word for word).
3. CLOSE          "Anything else? Anything you want me to tell Ravi?" + say what will be shared.  (30 s)
```

### 3.1 The memory check stays pure

- Inside the memory check, Smriti only does the memory check. If the parent brings up something else in the middle,
  Smriti says: "Let me remember that, we'll talk about it right after our little game." Then it continues.
- Open talk is allowed **before** "Task one" and **after** a new end phrase: *"That's the end of our memory game."*
  (HI / KN versions to be added). The scorer already ignores everything before Task one. It must also ignore
  everything after the end phrase (today, talk after the last question would be read as the helper answer).
- The memory check is due every 3–6 months, or sooner if weekly calls show memory slips twice in a month.
  The family can request one; the parent must say yes on the call.

### 3.2 Remembering across calls (cheap and fast)

Bolna has no memory between calls, so we pass it in. Before each call we send in `user_data`:
- `notes`: 3–5 short lines from earlier calls ("Knee hurt after temple walk on Tuesday. Granddaughter Pinky has exams.")
- `topics`: 2–3 topic cards picked from the India playbook (section 7) for this person, this week, this festival.
- `name`, `language`, `share_level`, `memory_check_due`.

No knowledge-base lookups during the call: they add delay and cost, and the playbook slice is small enough to send.

### 3.3 Key lines (English; Hindi and Kannada versions go in the prompt, word for word)

| Moment | Line |
|---|---|
| First ever call | "Hello, am I speaking with Kamala ji? I'm Smriti, an AI assistant. Your son Ravi asked me to call you. I'd like to call you once a week for a short chat. Is that alright with you?" |
| Which language (first call only) | "Which language would you like to speak: English, Hindi or Kannada?" |
| What is shared (first call) | "Shall I tell Ravi only that you're doing well, or also if you mention a health worry? You can change this any time." |
| Someone else answers | "I'm Smriti, calling for Kamala ji. When would be a good time to call her?" (no health talk with anyone else) |
| Weekly opening | "Hello Kamala ji, it's Smriti! How have you been since we last spoke?" |
| Remembering | "Last week you said your knee hurt after the temple walk. Is it better now?" |
| Before the memory check | "Shall we play our little memory game today? It takes about four minutes." |
| End of memory check | "That's the end of our memory game. Thank you!" |
| Close | "Is there anything you'd like me to tell Ravi?" … "I'll let him know you're doing well. Talk to you next week!" |
| Not sure if they want to stop | "Shall we continue?" |
| Upset / wants to stop | "Of course. We'll stop here. Take care, Kamala ji." |
| Red flag (chest pain, fall, can't breathe) | "That sounds important. Please call 112 now, or ask someone near you to. I'm also letting our care team know." |

---

## 4. Flags: how a worry becomes an action

```
Call ends → Bolna extraction pulls out mentions → fixed rules set the level → care desk → family call
```

**Categories** (fixed list): body pain · sleep · appetite · mood · loneliness · medicines · falls · memory slips ·
safety (abuse, being left alone, money pressure).

Each mention keeps the parent's own words and the call date.

**Levels** (decided by rules, not by the AI):

| Level | Examples | What happens |
|---|---|---|
| Green | Talked happily, no concerns | Timeline only |
| Yellow | The same pain in 2+ calls this month; sleeping badly 2 weeks running; "I feel alone"; skipped medicines | Care desk reviews within a day; family sees it if the parent allowed |
| Red | Chest pain, a fall, breathlessness, confusion about where they are, talk of not wanting to live, signs of abuse | In-call: tell them to call 112 (or 14567 Elder Line). After: care desk immediately, then the family call |
| Memory concern | Memory check REFER, or UNCERTAIN twice | Care desk reviews, then Smriti calls the family and offers help booking a doctor |
| No answer | 2 weeks with no completed call | Family is told: "We couldn't reach Appa for two weeks." |

**India note:** low mood often shows up as body complaints (aches, "ghabrahat", "dil baith raha hai"), so pain
mentions plus mood mentions together raise the level. The parent's own words are always shown, never a label.

**Abuse exception:** if the worry is about a family member, the care desk handles it and that family member is
not called. Route: Elder Line 14567 or HelpAge India.

---

## 5. Screens

### 5.1 Family app

1. **Timeline** (calendar style, newest first): one card per call. "Tue 4 Nov · 4 min · Kannada · 🙂 Cheerful.
   Talked about Pinky's exams. Knee pain again (2nd time this month)." Flags shown as small coloured dots.
2. **This week**: "2 flags this week: knee pain, slept badly." Buttons: *Call Appa now* · *See what to do*.
3. **What Appa wants you to know**: messages the parent asked Smriti to pass on.
4. **Memory**: last memory check in plain words, date of the next one. Never a raw score on the main screen.
5. **Settings**: suggested call times and days, language, contacts. A banner shows the parent's sharing choice.

### 5.2 Care desk (grown from today's review queue)

- Queue ordered red → memory concern → yellow → oldest.
- Each case: the parent's words, the flag rule that fired, a play button that jumps to that moment of the audio,
  transcript, previous calls.
- Actions: *Approve and call family* · *Dismiss with note* · *Schedule a recheck* · *Escalate (112 / 14567)*.

### 5.3 Parent

No screen. Everything by voice. Optional later: a missed-call number that makes Smriti call back (needs our own
telephony hook; Bolna has no built-in missed-call trigger).

---

## 6. Using Bolna well (verified in Bolna docs, Nov 2026)

| Need | Bolna feature | Status for us |
|---|---|---|
| Speak Hindi, Kannada, English and switch mid-call | `multilingual_config`, `agent_language` | Live today |
| Clear audio on noisy lines | `noise_cancellation_level` 85 | Live today |
| Hang up cleanly after goodbye | `hangup_after_LLMCall` + `call_cancellation_prompt` | Live today |
| "Are you there?" in their language | `check_user_online_message` | Live today |
| Weekly calls at a set time | `POST /call` with `scheduled_at` from our scheduler (Bolna has no weekly repeat) | Build |
| Only call 9am–9pm their time, skip nap time | Agent `calling_guardrails` start/end hour; out-of-window calls are rescheduled automatically | Build |
| Retry when nobody answers | `retry_config` (no-answer, busy; up to 3 tries; 30/60/120 min) | Build |
| Don't count voicemail as a call | Voicemail detection + `retry_on_voicemail` | Build |
| "Call me at 5" | `task_config.auto_reschedule` (beta) | Try |
| Pull out mentions after the call | Extraction categories → `extracted_data` with confidence | Build (confirm the questions API body first) |
| Hear family and medicine names right | Sarvam `saaras:v4` `keywords` (up to 50) | Build |
| Hand over to a human in distress | `transfer_call` tool to the care desk number | Later |
| Book a doctor | Cal.com tools ("Calendar availability", "Book appointment") or our own `api_tools` | Later |
| English recognition | Deepgram nova-3 is English only: fine for the English agent, not Hindi/Kannada | Try |

**Cost (estimate, check with Bolna):** platform price for our models is listed at about $0.06 per minute;
a 4-minute weekly call is about 16 minutes a month, so roughly $1 per parent per month before telephony
(the India telephony rate is not published).

---

## 7. The India playbook (small, curated, India-first)

A short file per language, not a big database. Each **topic card** = a natural opener + what it can reveal.

| Card | Opener | What it can reveal |
|---|---|---|
| Grandchildren | "How is Pinky? Exams going well?" | Mood, memory of recent events, loneliness |
| Morning routine | "Did you go for your walk today?" | Mobility, pain, sleep |
| Food | "What did you cook today?" | Appetite, energy, living alone |
| Festival (from a calendar) | "Ugadi is coming. Any plans?" | Social contact, mood, orientation in time |
| Temple / prayer | "Did you go to the temple this week?" | Mobility, social life |
| Cricket / serials / news | "Did you watch the match?" | Engagement, memory |
| Visitors | "Did anyone come to see you?" | Loneliness |

Rules: one or two cards per call, never a checklist; follow the parent's lead; India sources first.
- **LASI** (India's national ageing study) for patterns among older Indians.
- **10/66** for the memory check (already used).
- **Indian psychiatry studies** on how distress is described.

General research from abroad is used only where it clearly applies.

---

## 8. Rules we follow (India)

Not legal advice: have a lawyer confirm before a paid launch.

| Rule | What we do |
|---|---|
| DPDP Act 2023 + Rules 2025 (main duties from about May 2027) | The parent is the data owner and gives consent by voice, in their language. Withdrawing is as easy as agreeing. Erase on request. Plan for breach reports. A child's consent alone is never enough. |
| Telemedicine Practice Guidelines 2020 | No advice, diagnosis or medicine suggestions. Concerns go to a human, then a doctor. |
| CDSCO draft software-as-medical-device guidance (Oct 2025) | We describe ourselves as wellbeing check-ins plus a memory check that suggests seeing a doctor. We make no "screening device" or "detects dementia" claims until a regulatory opinion. |
| TRAI rules for automated calls (2025–2026 amendments) | Declare AI calling to the telecom provider. Use service-call numbers, never promotional ones. Say "I'm an AI" at the start. Keep consent records. Never market on these calls. |
| Senior citizens' welfare | The parent can always refuse. Abuse signs go to the care desk, 14567 or HelpAge, never to the family member involved. |

---

## 9. Facts safe to use in a pitch

| Fact | Source |
|---|---|
| About 7.4% of Indians aged 60+, roughly 8.8 million people, have dementia. | LASI-DAD, *Alzheimer's & Dementia*, 2023 |
| India's 60+ share: 10.1% (2021), projected 15% (2036) and 20.8% (2050). Southern states, including Karnataka, are ageing faster than the national average. | UNFPA India Ageing Report 2023 |
| 5.7% of people aged 60+ live alone: 9.0% of women and 2.6% of men. | LASI Wave 1, 2017–18 |
| Roughly 2 in 5 Indians over 60 use the internet. A phone call reaches the rest. | Data for India, from a national survey; say "roughly" |
| Languages: 43.6% Hindi, 4.37 crore Kannada speakers. | Census 2011 |

**Do not say:**
- "Only 10% of dementia is diagnosed" (no solid source).
- Any phone-ownership split by state.
- "Voice works better than apps for elders" (not proven).
- "57% prefer local languages" (disputed).

---

## 10. What we build, in order

The repo does not need a rewrite. Today's code is the memory-check engine. We add the weekly check-in next to it.

| Step | What | Done when |
|---|---|---|
| 1 | End phrase for the memory check; the scorer ignores talk after it | Test: talk after the end phrase does not change the helper answer |
| 2 | Weekly check-in agent (open talk → topic → close), with `notes` and `topics` in user_data | A live call remembers last week's note |
| 3 | Flag rules (fixed categories and levels, word lists in HI/KN/EN), from the transcript first and Bolna extraction later | Tests for yellow and red cases in all three languages |
| 4 | Data: Parent (consent, share level, call times), FamilyContact, Call (check-in or memory), Flag, Note, ConsentEvent | Migrations plus tests |
| 5 | Family timeline page | Shows seeded weeks plus the new live call |
| 6 | Care desk actions (approve → call family) | The family phone rings with a plain-words explanation |
| 7 | Weekly scheduler + calling hours + retries + voicemail | Calls go out on schedule in a test run |
| 8 | Later: booking (Cal.com), transfer to human, missed-call callback, India data residency | — |

---

## 11. The demo (local, about 5 minutes)

1. **Problem (30 s):** "We call home and hear 'all fine'. Memory changes are the ones families notice last."
2. **Family timeline:** three seeded weeks for "Appa": knee pain twice, slept badly, cheerful about Pinky's exams.
   The memory check is due.
3. **Live call on speaker:** a teammate plays Appa. Smriti remembers the knee and switches to Kannada. Appa mentions
   that he can't sleep.
4. **About a minute later:** the new card appears on the timeline with Appa's own words and a yellow flag.
5. **Care desk:** approve → the second teammate's phone rings → Smriti explains in plain words and suggests a
   doctor visit.
6. **Second use case:** the memory-check report from a real earlier call, with the review queue.
7. **Close:** "Smriti makes sure someone acts. Built for India, on India's voice platform."

**Backups:**
- A recorded video of the full flow.
- Seeded data so the screens never look empty.
- Demo mode if the network fails.

---

## 12. Things we noticed that are easy to miss

- **Scam fear:** elders are taught not to talk to unknown callers. The family introduces Smriti first, saves its number
  as a contact (we give them a contact card), the number never changes, and on every first call Smriti says
  "I will never ask for money, bank details or an OTP."
- **Shared phones:** someone else may answer. Confirm the name first, and never discuss health with anyone else.
- **"I'm fine" is the default answer.** Topics about their world, plus trends across weeks, matter more than direct
  questions.
- **Hearing loss:** keep speech slow (already 0.85 speed), offer to repeat, and use short sentences.
- **Silence is a signal:** two weeks without a completed call is itself worth telling the family.
- **Calling times matter:** avoid nap and prayer times. The parent picks; the family only suggests.
- **Travel and noise are real:** a noisy or interrupted call is marked INVALID and rescheduled, never scored. A real
  test call showed this.
- **Cost stays low:** short weekly calls, a memory check only every few months, no lookups during the call, and
  one extraction pass after the call.

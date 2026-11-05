# Smriti: hard questions and our answers

For the interview and the finale. Answers are short on purpose: say the first line, and add the rest only if asked.
Rules for answering:
- **Never invent numbers.** "We haven't measured that yet; here's how we will" is a strong answer.
- Facts we can cite are in [BLUEPRINT.md §9](BLUEPRINT.md).
- Lines marked **(fill in)** must be your own truth.

---

## 1. The product

**Q: What is Smriti, in one line?**
A friend who calls your parents every week in their language, remembers what they said, and makes sure the family
acts when something matters. We start with memory.

**Q: Isn't this just another automated call?**
No. Automated calls play recordings and grade answers later; if the person goes off-script, the call breaks.
Smriti holds a real conversation: it lets the parent talk first, remembers last week, switches language
mid-call and handles "call me later". Only the memory check is structured, and it's scored by fixed rules after the call.

**Q: So is the AI deciding if someone has dementia?**
Never. The AI holds the conversation. Fixed rules score the memory check and raise flags, so the same answers
always give the same result. A person reviews every concern before the family hears about it. Only a doctor diagnoses.

**Q: Why a phone call and not an app?**
- The parent needs nothing new: no smartphone, no app, no internet. Roughly 2 in 5 Indians over 60 use the internet,
  so a call reaches the rest.
- The family, who pays and acts, gets the app.

**Q: Why memory first?**
- It's the change families notice last. "She sounds fine on the phone" hides it.
- Memory and language are things a phone call can actually measure.
- There's an established test (10/66) built for low-literacy, multilingual settings.
- About 7.4% of Indians over 60, roughly 8.8 million people, have dementia (LASI-DAD 2023).

**Q: What else will it check later?**
Only what a call can genuinely notice: mood, loneliness, pain that keeps coming up, sleep, whether medicines are being
taken, and changes after a hospital stay. Never "full health checkups".

---

## 2. Who needs this (product–market fit)

**Q: Who is the customer?**
The **user** is the parent or grandparent. The **buyer** is their son, daughter or grandchild, a working
professional living in another city or country. Next come care companies and employers (see §4).

**Q: How do you know they want it?**
Honest answer: we have live test calls, not paying users yet.
- **(fill in)** Conversations with families so far, and what they said.
- Next step: a 4-week pilot with 20–30 families in Bengaluru.
- What we'll measure: do parents pick up week after week, and do families open the timeline and act on flags?

**Q: What's the "hair on fire" moment?**
- After a fall or a hospital stay.
- After a parent forgets something important.
- When a sibling says "Amma sounded off".
- Before a festival visit home.

Those moments are where families sign up.

**Q: Will elders actually talk to an AI?**
- Our test callers chatted, switched languages and joked with it.
- The call says plainly that it's an AI and is a short, friendly chat in their own language.
- The family introduces Smriti first, so it isn't a stranger calling.
- **(fill in)** Any reaction from a real elder you've tested with.

**Q: What does it cost a family?**
- Hypothesis to test in the pilot: an affordable monthly family plan.
- Our cost is low: Bolna lists about $0.06 a minute for our models, so a 4-minute weekly call is roughly $1 a month
  before telephony. That's an estimate to confirm with Bolna.

---

## 3. Founder–market fit and team

**Q: Why are you the right team?**
**(fill in, truthfully)** Your link to the problem (grandparents, family), your languages (Hindi, Kannada, English)
and what you shipped in the buildathon:
- a working multilingual voice agent on Bolna;
- fixed-rule scoring in three scripts;
- a review queue;
- fixes from real calls: noise, language switching, wrong hang-ups.

**Q: What did you learn from real calls?** (shows you test with reality)
- Hindi speech-to-text heard चार as "chair", so we made word matching script-aware.
- A Kannada call hung up after 25 seconds because the first transcript was slow, so we added a localised "are you there?" check.
- On a noisy call, two digit strings got merged, so the agent now says one string per message.
- "That's all" was taken as "stop the call", so the agent now stops only when it's clear, and otherwise asks "Shall we continue?".
- A tester who was travelling stopped the call. It came out INVALID, which is correct: no false result.

**Q: What if one of you leaves?**
**(fill in)** Roles, and that the code, the tests and the blueprint are written down so anyone can continue.

---

## 4. Getting it out there (push and pull)

**Q: How do you get users?**
- **Pull (families come to us):**
  - "Send Appa a call" links shared on WhatsApp.
  - Siblings joining the same family circle.
  - Festival and "back home" moments.
  - The parent's birthday.
- **Push (partners bring families):**
  - Elder-care companies whose care managers can become our care desk (Emoha, Anvayaa, KITES in Bengaluru, still to be verified).
  - Employers offering a parent-care benefit.
  - Hospitals for follow-up after discharge.
  - Insurers later.
- **Start narrow:** Bengaluru, Kannada + Hindi + English, families of tech professionals.

**Q: Why won't a big company copy this?**
They can copy a call. What's harder to copy:
- Scoring checked across Indian languages and scripts.
- The trust of parents and families.
- A consent model built around the parent.
- The full loop from call to human review to family to doctor.
- Months of real-call fixes.

**Q: Competitors?**
| Competitor | What it is | How we differ |
|---|---|---|
| Joy Calls, CheckWellCall, Callie Care, AloneAssist | US daily check-in calls | English, no memory test |
| Samarth, Dozee Shravan, Care4Parents | Indian remote-parent care | Apps, sensors or care managers |

None combines a plain phone call in Indian languages with a structured memory check and a family loop.

**Q: Is the market big enough?**
- India's 60+ share goes from 10.1% (2021) to 15% (2036) to 20.8% (2050) (UNFPA 2023).
- Southern states, including Karnataka, are ageing faster than the national average.
- Every elder is a recurring weekly call for years.

---

## 5. Clinical safety and accuracy

**Q: Is the phone version of the memory test validated?**
Not yet. Be upfront about it.
- The tasks come from 10/66, which was designed for low-literacy, multilingual populations.
- Moving it to the phone needs validation: comparing our result with a clinician's assessment in a pilot.
- Until then, Smriti only says "worth seeing a doctor", never a diagnosis.

**Q: What about false alarms and missed cases?**
- **False alarm:** a person reviews first, and the family hears "worth a check", not "dementia".
- **Missed case:** the weekly calls and repeat checks catch changes over time, and families can always ask for a check.
- **Noisy or interrupted calls** are marked INVALID and retried, never scored.

**Q: Hearing loss, low education, or a parent who never went to school?**
- Task 1 is a hearing check.
- We record years of schooling because the original test adjusts for education.
- Speech is slowed (0.85 speed), repeats are allowed, and the parent can choose their language.

**Q: What if someone says something dangerous, like chest pain, a fall or not wanting to live?**
- During the call: "Please call 112 now, or ask someone near you." The care team is alerted immediately.
- For abuse or neglect, the route is Elder Line 14567 or HelpAge, never the family member involved.

**Q: Who is liable if something is missed?**
- We position Smriti as wellbeing check-ins plus a prompt to see a doctor, not a medical device.
- We never advise or prescribe (Telemedicine Guidelines 2020).
- We'll get a regulatory opinion before making any screening claims.

---

## 6. Privacy, consent and family conflict

**Q: Isn't this surveillance of parents?**
No. The **parent owns it**:
- They agree by voice on the first call, in their language.
- They choose what's shared: "only that I'm fine", "health worries too", or everything important.
- They can stop at any time.
- The family never reads raw transcripts.

This also follows India's DPDP Act, under which the parent is the data owner.

**Q: What if the son wants calls and the mother doesn't?**
The mother wins. The son can suggest; Smriti asks her; her "no" is final.

**Q: Elders are told not to talk to unknown callers because of scams. Won't they hang up?**
- The family introduces Smriti, and we give them a contact card so the call shows "Smriti".
- The number is always the same, and caller-ID verification is planned.
- Smriti says on every first call: "I will never ask for money, bank details or an OTP." This is also protection against scams.

**Q: Where is the data stored? Is it secure?**
- Phone numbers are hashed, the webhook and admin access use tokens, and nothing is shared without consent.
- Bolna is US-hosted by default and offers India data residency on Enterprise, which we'd use for health data.
- Recording deletion goes through Bolna support today, and we'd automate it.

**Q: Someone else answers the phone?**
Smriti confirms the name first and never discusses health with anyone else. It just asks for a good time to call.

---

## 7. Engineering (what a senior engineer will ask)

**Q: What if the call drops halfway through?**
- If the memory check is incomplete, it's INVALID and never scored.
- For a check-in, whatever was said is kept.
- The call is retried automatically: Bolna's `retry_config` covers no-answer and busy, up to 3 tries at 30/60/120 min.

**Q: Network or telephony failures?**
- The call request isn't retried blindly, so we never double-call. We retry only on connection errors.
- Bolna queues calls beyond our concurrency limit.
- Voicemail detection means an answering machine doesn't count as a call.

**Q: What if your webhook is down?**
- A poller fetches the result anyway.
- Scoring is guarded by an atomic database claim and a unique score per session, so a duplicate webhook and the poller can never score twice.

**Q: Speech recognition errors, accents, Hinglish or Kanglish?**
- Sarvam saaras v4 for Hindi and Kannada.
- Our matching handles English words written in Hindi or Kannada script ("हाउस", "ಹೌಸ್"), plurals, and fuzzy matches with strict limits.
- Keyword boosting for family and medicine names is next.
- English: try Deepgram nova-3.

**Q: Latency?**
- Streaming speech-to-text and voice, a small fast language model (gpt-4.1-mini), short replies.
- Bolna reports first-response delay per call, and we show it on the "Behind the call" screen.

**Q: The AI could hallucinate or be manipulated ("ignore your instructions")?**
- The AI only converses, and key lines are fixed word for word.
- Temperature is 0.2.
- Scores and flags come from fixed rules over the transcript, so talking the AI into something can't change a result.

**Q: How does it scale to 100,000 calls a week?**
- Bolna batches and scheduled calls, with calling hours enforced in the person's time zone (9am–9pm).
- Concurrency grows with the plan.
- Scoring is plain Python over text: cheap and parallel.
- Our side is a simple web app plus a queue.

**Q: What if Bolna goes down or changes prices?**
- Calls queue and retry.
- Our scoring, data and app are ours. The agent is defined in a config file, so in theory it's portable.
- But we're building on Bolna on purpose: Indian languages are its strength.

**Q: How do you test?**
- Over 270 automated tests: scoring in three scripts, the segmenter, the API, the Bolna client (mocked), and regressions from every live call.
- Plus real calls.

**Q: How do you keep costs down?**
- Short weekly calls, with the memory check only every few months.
- No knowledge-base lookups during the call: notes and topics are sent in with the call.
- One extraction pass after the call.

---

## 8. Try to kill it

| Attack | Why it doesn't kill us | If it turns out true, how we adapt |
|---|---|---|
| "Elders won't pick up AI calls." | The family introduces it, it's always the same number, saved as "Smriti", it says it's an AI, and the chat is short and warm. | Start with a short human-intro call, or let the parent start it with a missed call. |
| "Families won't pay." | The cost per parent is low, and the moments that trigger sign-ups are real (falls, discharge, forgetfulness). | Sell through care companies, employers and insurers instead. The product stays the same. |
| "The phone memory test isn't valid." | We don't diagnose. We say "worth seeing a doctor", and a person reviews first. | Run the pilot validation with a clinic. Tune the cut-offs, or use it only as a trend tracker. |
| "It's surveillance and creates family conflict." | The parent owns it and chooses what's shared, and their no is final. | Offer a "just say I'm fine" level as the default. |
| "Big tech or Bolna could build it themselves." | Bolna is a platform; it needs vertical products like ours. Our edge is the scoring, the trust and the care loop. | Partner with Bolna as the elder-care showcase or design partner. |
| "Regulators will call it a medical device." | We position it as wellbeing plus a doctor nudge, with no screening claims. | Get a regulatory opinion. If needed, go through a clinical partner, where clinicians use it as a decision aid. |
| "Speech recognition fails for elderly accents in noisy homes." | Noise cancellation, a retry before scoring, and INVALID instead of a wrong score. Real calls already drove these fixes. | Keyword boosting, speech models tuned on elderly voices (with consent), and per-language providers. |
| "Scam fears and TRAI rules on robocalls." | We declare AI calling, use service numbers, keep consent records and say "never money or OTP". | Caller-ID verification and calls the family starts. |
| "Someone in distress and the AI can't help." | It stops, gives 112 / 14567 and alerts the human care desk. | Use Bolna's transfer-to-human tool to the care desk. |
| "No traction yet." | True. We're at buildathon stage with real live calls. | A 4-week pilot with clear success measures: pickup rate, family actions, doctor visits. |

---

## 9. Why this is good for Bolna

1. **A new vertical:** family health and elder care. Bolna's customers today are mostly banking, e-commerce, edtech and recruitment.
2. **The steadiest usage a voice platform can get:** a scheduled weekly call per elder, for years. It's predictable minutes, not one-off campaigns.
3. **The hardest proof of Indian voice AI:** elderly speakers, code-mixing, noisy lines, Kannada and Hindi. If it works for Ajji, it works for every customer.
4. **It uses Bolna's features deeply:**
   - in use today: language switching mid-call, noise cancellation, custom hang-up and "are you there?" handling, webhooks and executions;
   - planned: batches, calling hours, retries, voicemail detection, auto-reschedule, extractions, Cal.com booking, transfer to human, Truecaller verification.
5. **A story Bolna can tell:** "Voice AI that keeps families connected", which is good for brand and fundraising.
6. **Two outbound conversations per concern** (elder, then family), so more value per user.

---

## 10. Questions we should ask them

**Bolna:**
- Can the trial calling limit be lifted for the demo and pilot?
- Is there interest in a healthcare or elder-care design partnership?
- How are scheduled recurring calls priced, and are there volume rates?
- Timeline for India data residency outside Enterprise?
- Can extraction questions be fully set up through the API?
- Can a transfer tool take a dynamic number (the family's)?
- Truecaller business verification: process and cost?

**Judges and organisers:**
- What would make this pilot-ready in your eyes?
- Which partner would you approach first: care company, hospital or employer?

---

## 11. Numbers: safe vs. avoid

**Safe to say (cite if asked):**
- 7.4% of people 60+ have dementia, about 8.8 million (LASI-DAD 2023).
- The 60+ share goes from 10.1% to 15% to 20.8% (UNFPA 2023).
- 9.0% of older women and 2.6% of older men live alone (LASI Wave 1).
- Roughly 2 in 5 people over 60 use the internet.

**Avoid:**
- "Only 10% are diagnosed".
- Phone ownership by state.
- "Voice beats apps for elders".
- Any accuracy number for our test.
- Any user count we don't have.

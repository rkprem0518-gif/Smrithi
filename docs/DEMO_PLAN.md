# Smriti demo plan

The goal: 5 minutes in which the judges *feel* the product, see that it is real, and see why it matters to Bolna.
Built on top of [BLUEPRINT.md](BLUEPRINT.md). If this plan and the blueprint disagree, the blueprint wins.

## 0. Run the demo: three apps, three ports, one server

```bash
.venv/Scripts/python scripts/seed_family.py --sample  # optional: sample family (Appa, Ravi, Priya, Dr. Meera); --empty to start blank
.venv/Scripts/python scripts/run_demo.py              # one process, three ports, live sync between them
```

| Port | App | Demo login | Use it for |
|---|---|---|---|
| http://localhost:8000/smriti.html | Family | Ravi (son) or Priya (daughter) | Today, timeline, calendar, memory, reports, schedules, family circle, history |
| http://localhost:8001 | Elder ("For Appa") | Raghunath Rao (Appa) | Big-text page: say yes to new members, call me now, my language, what is shared, pause calls |
| http://localhost:8002 | Care team (clinic) | Dr. Meera Iyer | Patients, review queue, approve → Smriti calls the family, behind the call (costs) |

- **Separate logins:** each port has its own login cookie, so all three can be open side by side in one browser.
- **One address:** the same apps are also at http://localhost:8000/elder/ and http://localhost:8000/care/ (this is how the Render deploy serves them).
- **Real calls with your own key:** family app → **Connect Bolna** (under the Real calls switch) → paste the API key. Smriti creates its three agents on that account; calls stay simulated until the switch is on.
- **Live sync:** anything done in one app shows up in the others within a second.
- **Screen language:** English · हिंदी · ಕನ್ನಡ, switched in the sidebar or on the login card.
- **Ports:** set them in `.env` with `FAMILY_PORT`, `ELDER_PORT` and `CLINIC_PORT`.
- **Offline backup with no real calls:** run with `DEMO_MODE=1`. Calls are then simulated and Bolna is never contacted.
- **Calls:** real calls only happen when someone presses a call button in live mode. Automatic scheduled calls are off unless `SCHEDULER_ENABLED=1`, and even then only in demo mode.

---

## 1. The story in one breath

> "We call home, and they say *all fine*. Smriti is the friend who calls our parents every week, in their language,
> remembers what they said, and makes sure the family acts when something matters. We start with memory,
> because that is what families notice last."

The demo shows exactly that, in that order: **the family's worry → the call → the moment Smriti remembers →
the timeline updating → a human checks → the family gets a call and a doctor's visit goes on the calendar.**

End on the strongest moment. People remember the peak and the end, so the end is the son's phone ringing,
not a settings page.

---

## 2. What we build for the demo

Sized for the middle: enough to show the whole loop working for real, nothing that is only there to look busy.

### Build (real, working)

| # | Piece | What the judges see |
|---|---|---|
| 1 | **Weekly check-in call** (Bolna, multilingual) | A warm 90-second call: open talk → one topic → close. Smriti says she's an AI, remembers last week ("Is your knee better?"), switches language if asked. |
| 2 | **Memory check, unchanged** + end phrase | Shown through a report from a real earlier call. Scoring stays exactly as built. |
| 3 | **Flag engine** (fixed rules, HI/KN/EN word lists) | After the call, the card shows the parent's own words and a green, yellow or red flag. |
| 4 | **Family app** (the star) | Week strip, thread timeline, "what Appa wants you to know", flags, memory section, Call now button. |
| 5 | **Live call panel** | Dialling → ringing → talking → "Smriti is writing the notes…" → the new card slides into the timeline, with no refresh. |
| 6 | **Care desk** | Queue (red first). Opening a case shows the words, the rule that fired and the audio. Approve → family call. |
| 7 | **Family call-back** (second Bolna agent) | The son's phone rings. Smriti explains in plain words and offers to set up a doctor's visit. |
| 8 | **Calendar** | The calendar shows the weekly calls, the memory check due date and the doctor's visit. **Add to Google Calendar** uses a prefilled link, so no sign-in is needed. An .ics download is also offered. |
| 9 | **Reports** | **Family monthly report** with mood across weeks, completed calls, flags by type and memory history. **Doctor summary**, one printable page, shared only if the parent allowed. |
| 10 | **Call details for Bolna** | Cost, duration, response delay and recording for each call, plus the wallet balance. This answers the "what did that call cost?" question on the spot. |
| 11 | **Save Smriti's number** | A contact card (.vcf) the family puts on the parent's phone, so the call shows "Smriti" like any saved contact. |
| 12 | **Seeded history** | Eight weeks of believable data for "Appa", so no screen is ever empty. A reset script restores it in one command. |

### Say, but do not build (roadmap, one sentence each)

| Feature | What we say |
|---|---|
| Mobile app + caller ID | "In the app, the call shows as *Smriti · Family check-in*. Bolna supports Truecaller business verification for numbers." |
| Real doctor booking | "Next: Bolna's Cal.com booking tools and clinic partners. Today it creates a request on the family calendar." |
| Google Calendar two-way sync | "Today it's a one-click add; next is a full sync." |
| Missed-call callback | "The parent gives a missed call and Smriti calls back. This needs our own telephony hook." |
| WhatsApp summaries | "Through Bolna workflows (AiSensy)." |
| Care companies signing in | "The same care desk, used by a partner's care managers." |
| Memory book / diary, companion mode | "Later. We're nailing three things first." |
| India data residency | "Bolna offers it on Enterprise." |

### Not doing at all, on purpose
- Therapy or "venting" mode.
- Any diagnosis wording.
- Live knowledge-base lookups during the call.
- Payments.
- A native app for the demo.
- Gamified scores.

---

## 3. What's new compared with the original Smriti

1. Smriti is now a **weekly check-in** product, and the memory check runs inside it every few months.
2. Every call is **conversation first**: the parent can talk, report and ask before anything structured happens.
3. **Memory across calls**: notes from last time plus India topic cards, sent in with the call.
4. **Flags** with the parent's own words, raised by fixed rules.
5. **Parent-owned consent and sharing levels.** The family can suggest but cannot override.
6. **Family app**: timeline, calendar and reports.
7. The care desk now leads to a **family call-back** and a **doctor's visit on the calendar**.
8. A **doctor summary page** and **call details for Bolna**.
9. Safety lines: "I'm an AI", "I will never ask for money or an OTP", 112 / 14567 escalation.

---

## 4. Design: calm, warm, grown-up

### Feel
Calm technology, the opposite of an alarm app. Warm enough to trust, competent enough to rely on.
Nothing shouts unless it has to: colour is reserved for meaning, so a red dot really means something.

### Colour (no purple, no brown, no gradients)

| Token | Colour | Why |
|---|---|---|
| `--paper` | `#F6F4EF` (soft porcelain) | Easier on the eyes than pure white and feels like paper, not a dashboard. |
| `--ink` | `#1C2B2D` (deep ink) | High contrast for older eyes, softer than black. |
| `--peacock` | `#0E5E63` (peacock teal) | The main colour. Blue-green reads as calm, trust and health, and peacock is unmistakably Indian. |
| `--marigold` | `#E3A72F` | Warmth and festival, used for highlights and the "remembered" moments. |
| `--sage` | `#5E8C6A` | Green flag: all well. |
| `--amber` | `#C98A1B` | Yellow flag: worth a look. |
| `--vermilion` | `#B8432F` | Red flag: act now. Used sparingly. |
| `--mist` | `#E4E9E6` | Lines and quiet surfaces. |

Dark mode uses the same hues on `#111A1B`.

### Type
- **Atkinson Hyperlegible** for all body text. It was designed by the Braille Institute for low-vision readers, so it's legible for older eyes, and the reason behind the choice is part of the story.
- **Fraunces** (a soft serif) for headings. It feels mature and human, like a letter rather than an app.
- **Noto Sans Devanagari / Noto Sans Kannada** for Hindi and Kannada, with a matched size.
- Minimum body size 18 px. Touch targets at least 48 px. Contrast meets WCAG AA or better.

### Motifs
- **The thread.** The timeline is a single soft thread that connects every call. *Smriti* means memory, and the
  thread is what holds memories together. Each call is a knot (a small dot) on the thread, coloured by its flag.
- **The parent's own words** are shown in a quote style, larger than labels, so the person is the centre of the screen,
  not the metrics.
- **Remembered moments** get a marigold underline: "Last week: knee hurt after the temple walk."

### Psychology we lean on
- **Recognition over recall.** Everything is visible, with no menus to remember.
- **Progressive disclosure.** The headline first, then detail on tap.
- **Few choices per screen**, which keeps decisions fast.
- **Calm by default, colour only for meaning**, so the family's attention goes where it should.
- **Faces and names, not IDs.** "Appa", never "Patient #42".
- **Peak-end.** The demo and each call end on a warm line.

### Screens (one web app, sidebar on desktop, bottom tabs on phone width)

1. **Today**
   - Greeting: "Good morning, Ravi."
   - Appa's card: photo initial, last call, mood word, next call.
   - "This week": 2 small flags, each with Appa's words.
   - Large **Call Appa now** button.
2. **Timeline**
   - The thread with a week strip on top. Tapping a knot opens the call: summary, Appa's words, topic, language, duration, and the remembered note.
3. **Calendar**
   - A month view with weekly calls, the memory check due date and the doctor's visit.
   - **Add to Google Calendar** and .ics buttons.
4. **Memory**
   - The last check in plain words.
   - History dots across months.
   - The next check date.
   - "What this means / what it does not mean".
5. **Reports**
   - Family monthly report.
   - Doctor summary, printable, with a banner showing the parent's consent.
6. **Care desk** (separate entry)
   - The queue, the case view with an audio jump, and Approve → call family.
7. **Behind the call** (for Bolna)
   - Per-call cost, duration, first-response delay and hang-up reason.
   - Wallet balance.
   - The Bolna features in use.
8. **Live call panel**
   - Slides up from the bottom when a call starts. Status steps: dialling, ringing, talking, writing notes, done.
   - A soft animated sound wave while the call is live.

---

## 5. The 5-minute run, second by second

People: **A** presents. **B** runs the laptop. **C** holds the "son's" phone.
The judge plays the parent; if they decline, B plays Appa from a second phone.

| Time | On screen | Said | Notes |
|---|---|---|---|
| 0:00–0:30 | Today screen, Appa's card | The hook. Use **your own real story** about a grandparent, if you have one. Never invent one. | Slow, warm, no slides. |
| 0:30–1:00 | Timeline: the thread, 8 weeks | "Here is Appa's month. Knee pain twice, he slept badly, he's cheerful about Pinky's exams. The memory check is due." | Hover over one knot to show his words. |
| 1:00–1:15 | Tap **Call now** with the judge's number | "Let's have Smriti call *you*. You're Appa today." | **The number must already be verified on Bolna** (section 6). |
| 1:15–3:00 | Live panel: ringing → talking | Speakerphone. Smriti: "Hello! I'm Smriti, an AI assistant your family set up… Last week you said your knee hurt. Is it better?" | If the judge asks to switch, say "Kannada please" to show the language change. |
| 3:00–3:20 | Panel: "writing notes" → the new knot appears on the thread | "No refresh. Smriti wrote the notes in the judge's own words, and fixed rules set the flag. No AI guesswork." | If no worry was mentioned, the card is green: "Cheerful, talked about…". That is a fine outcome too. |
| 3:20–3:50 | Care desk: a red-first queue with a real memory-check REFER case | "A person always checks before the family worries. Smriti never diagnoses." | The case comes from a real earlier call, pre-loaded. |
| 3:50–4:25 | Approve → C's phone rings on speaker | Smriti to the son: "Your father's memory check suggests a visit to a doctor. This is not a diagnosis. Shall I add a visit to your calendar?" | Let it run about 20 s, then hang up. |
| 4:25–4:40 | The calendar shows the doctor's visit; **Add to Google Calendar** | "From one phone call to a doctor's visit, in one flow." | |
| 4:40–4:52 | **Behind the call**: cost of the judge's call | "That call cost ₹X on Bolna." (Read the real number off the screen.) | It answers the cost question before anyone asks. |
| 4:52–5:00 | Back to Today | "Smriti makes sure someone acts. Built for India, on India's voice platform." | Stop talking. Pause. |

### If something breaks
- **The call doesn't connect in 20 s:**
  - Say "Telephony, live: this is exactly why we retry automatically."
  - B taps **Call** to the backup verified phone.
  - If that fails too, play the 60-second recording.
- **The webhook is slow:** the poller fills in the card within about 15 s. Talk over it: "Smriti is writing the notes."
- **No internet:** switch to demo mode. Every screen still works on seeded data.
- **The judge says something unexpected:** let Smriti handle it. That's the point of the demo.

---

## 6. Must-do before the demo

1. **Bolna trial limits.** Trial accounts can only call verified numbers and only 2 calls at a time.
   - Ask Tanisha / Bolna today to lift the limit for the demo, or upgrade.
   - Otherwise, verify the judge's number in the Bolna dashboard before the session starts (it needs their OTP), plus two backup numbers of our own.
2. Run the full flow at least 3 times on the demo laptop and network, including one time with the tunnel off (poller only).
3. Make sure the wallet has enough credit for about 10 calls of 2–5 minutes.
4. Charge the phones and turn off Do Not Disturb. Turn up speaker volume. Use a quiet room.
5. Record the backup video of the full flow.
6. Seed reset: `scripts/seed_demo.py --reset` (to be built) right before going on.
7. Make the browser window full screen at 125% zoom, with notifications off.

---

## 7. Build order (tonight → before demo)

Each step leaves something showable, so we can stop at any step and still demo.

1. Design system plus the Today / Timeline screens on seeded data. After this, the app *looks* finished.
2. Live call panel wired to the events stream, with **Call now** using the existing Bolna call path.
3. Check-in agent prompt (open talk → topic → close; notes and topics from user_data; "I'm an AI", "never money or OTP") and the memory-check end phrase.
4. Flag engine with tests, so a call becomes a card with words and a flag.
5. Care desk approve → family call-back agent.
6. Calendar with the Google link and .ics, the reports and doctor summary, Behind the call, and the contact card.
7. Rehearse, record the backup, freeze.

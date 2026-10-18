# Other Challenge 1 teams

Notes from reading two other teams' public repos after the event (October 18, 2026). Nothing
from their code is copied here. Facts come from their READMEs and commit history; anything else
is marked as our read.

## Lamplight (2nd place)

- Repo: https://github.com/stefan-cruceru/ihh-referral-intake (MIT)
- Demo: https://stefan-cruceru.github.io/ihh-referral-intake/
- Team: Stefan Cruceru, Samantha Rubinchik

### What they built

- About 8,000 lines of Python and JS, 196 tests, 80 merged pull requests. Windows exe, Docker,
  demo site and a 2-minute video.
- One app for all three challenges.
- Intake: watched folder, drag and drop, and a hospital upload page with an instant receipt and
  case code. Each referral gets an owner (round-robin by shift). The 2-hour clock starts on
  arrival; packets after 8:30 PM are marked for the morning shift.
- Three models:
  - Haiku sorts pages and is a cheap first gate.
  - Opus reads pages and applies the rules.
  - Sonnet does a second, independent read; if the numbers disagree, a person reads the page.
- The two gates first: self-care and behavioral stability (IHH has no Title 22 license).
- Only the clinical line can say no. The code enforces it.
- Chase ladder: one message listing everything missing, including critical values nobody found
  (for example heart failure with no ejection fraction). Reminder at 30 minutes, note to the
  supervisor at 60, "we need more time" at 15 minutes left. All drafts.
- After a yes: Kipu fields, census row and site email, drafted.
- Resource finder and a large-print client handout (Challenge 2). Practice mode on invented
  patients (Challenge 3).
- English and Spanish, accessibility modes, Copilot/MCP plugin, prompt-injection checks with a
  test attack packet, a print campaign for staff rollout.

### What IHH told them (from their `docs/workflow-and-timing.md`)

- About half of referrals are withdrawn; about a quarter of all referrals are lost because IHH
  was too slow. IHH's chosen measure: fewer withdrawals.
- Social workers send one referral to several programs. The first to answer gets the patient.
- The clinical second check is one person, with notes in a shared Excel sheet. Usually 20 to 40
  minutes, sometimes 24 hours.
- The director said retyping is not the pain. They want a list of what is missing.
- Every IHH employee has Copilot under a BAA.

These are their notes from IHH conversations. We did not confirm them with IHH.

### Weak spots

- No published accuracy. Their "Where it gets things wrong" section still says "To fill in from
  the eval run on R01 to R11."
- Time savings are placeholders (40 vs 10 minutes), and they say so.
- Live Kipu, Teams sign-in and a production mode are built but off by default. Their README says
  this goes past the event's prototype-only rule.

### Why they likely placed 2nd (our read)

1. They interviewed IHH several times and wrote it down.
2. They built for IHH's top number, withdrawals, with the chase ladder.
3. They fit IHH's tools: Kipu, Teams, Copilot, the Excel census.
4. One tool covers all three challenges.

## IHH Claude October (Ritwik Trehan)

- Repo: https://github.com/ritwikntrehan/IHH-Claude-October-Trehan (MIT)

### What they built

- Mostly research and architecture documents (about 60 markdown files).
- Three Power Automate flows in a sandbox tenant, shown as screenshots. Their own notes say the
  flows were never run end to end.
- Offline Tesseract OCR across all 282 pages, kept private. No accuracy measured. A Claude vision
  run was blocked by their own data-handling check; a later private run is reported without
  published results.
- A small offline HTML demo on one synthetic PDF with hand-written findings and an in-memory
  review log.
- JSON schemas for a review bundle and review actions.
- Privacy handled well: no packets or keys in git history.

### Useful from it

- Microsoft 365 / Power Automate as the backbone, since IHH already runs on it.
- Their numbers from event talks: about 1,000 packets and a $3,000 to $5,000 monthly compute
  budget, so about $3 to $5 per packet. Not confirmed with IHH.
- A 30-day shadow run as the pilot: the coordinator decides as usual, the tool is compared after.

## How we compare

| | Lamplight | Trehan | OCMEE |
|---|---|---|---|
| Measured on IHH's real decisions | Not published | No | All 4 denials caught, 2 approvals wrongly flagged, 459/459 quotes found |
| IHH interviews written down | Yes, 4 sessions | Partial | No |
| Chases the hospital | Reminder ladder | No | Drafted reply only |
| Missing critical value becomes a question | Yes | No | No (known gap) |
| Clinical-line-only denial | Enforced | No | No |
| Fits Microsoft / Kipu | Built, off by default | Designed | No |
| Challenges covered | All 3 | 1 | 1 |

## What we would add next

1. Missing critical values (INF-1/2, CARD-2 and similar) become questions to the hospital and
   lower the score.
2. A chase ladder of reminder drafts at fixed times.
3. A clinical-line step: a likely "no" goes to a reviewer, and only that person confirms it.
4. A cheap Haiku first pass to cut cost per packet.
5. Written notes from every IHH conversation.

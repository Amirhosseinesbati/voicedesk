# VoiceDesk — independent portfolio project

## Honest case study

**Problem.** A small home-services office needs to answer routine questions and book eligible visits while keeping an operator in control of uncertain or unsupported calls. The hard part is not generating a friendly sentence: it is preserving an exact customer-approved appointment through interruptions, concurrent demand, reconnects, and calendar conflicts.

**Approach.** VoiceDesk separates streaming audio from a durable semantic booking workflow. A calm browser studio shows transcript, captured slots, proposals, and calendar evidence; an operator console presents call outcomes and handoffs. A curated fictional knowledge base supplies service/pricing sources. The booking path requires explicit confirmation, server-side revalidation, a transactional local capacity claim, and an idempotent operation record. The live provider and Google Calendar are configured adapters, while the demo uses local data and clearly marked simulations.

**Dataset and verification.** A deterministic generator creates eight services, six staff, three zones, 400 fictional customers, and 600 appointments. The fixture validator checked all 600 appointments for references, workspace ownership, duration, schedules, blackouts, and confirmed-resource overlap. The conversation corpus contains 40 development and 80 held-out cases, with hidden answer labels separated from public turns. The final-source, isolated text API replay recorded 40/40 correct development and 80/80 correct held-out outcomes, 50/50 exact held-out target times, and zero unauthorized mutations; 10/10 development policy answers cited their expected knowledge source. Twenty complete synthetic conversation scripts are available. WAV rendering, live microphone behavior, and latency remain unverified. These are fictional records, not customer results or revenue.

**Design decision.** Checkpoint meaningful turns and action state, not raw audio frames. That keeps the booking ledger durable without making audio streaming wait for database writes. Local capacity locking protects local callers, and the Google adapter must recheck and reconcile conflicts caused by outside calendar writers.

**Current limit.** This is a commercial pilot starting point. It should be described as a working product only for journeys that the final handover verifies. Live provider credentials, real calendar authorization, acoustic testing, retention review, deployment hardening, and actual operator review remain customer-specific work.

## 60–90 second demo script

Use the running demo and label all records synthetic. These are presenter steps, not claimed screenshots or measured results.

| Time | Presenter action | Evidence to show |
| --- | --- | --- |
| 0–10 s | Open the studio; point out voice and text controls plus the synthetic/demo label. | Connection and transcript status are truthful. |
| 10–25 s | Ask for a boiler service. Start a suggested date, then interrupt and change the day. | The old proposed date disappears and the corrected details appear. |
| 25–40 s | Hear or read available alternatives; ask for exact local date and timezone. | Calendar-backed slot and qualified staff/resource. |
| 40–55 s | Confirm the exact service, zone, date, and time. | A persisted booking reference and operator calendar update. |
| 55–70 s | Request roof inspection on the seeded fully booked day, 2026-10-14. | A real unavailable result and a later alternative. |
| 70–85 s | Open the operator view. | Transcript, booking record, knowledge source, and handoff queue. |

If live audio is not configured, explicitly call the run a **text/demo replay** and skip voice latency claims. Never imply the assistant audio is live if it comes from a script.

## 3–5 minute technical walkthrough

1. **Architecture (about 45 seconds):** show the audio WebSocket/stream separately from the FastAPI semantic turn endpoint and LangGraph checkpoint transitions; identify where session/turn IDs and workspace authorization are checked.
2. **Policy and slots (about 45 seconds):** show the curated knowledge article source, service/zone/staff hours, DST-aware local time, and the full-day roof inspection fixture.
3. **Booking safety (about 75 seconds):** trace proposal version → explicit confirmation → server recheck → local capacity claim → booking operation/idempotency record. Show how an interruption invalidates the prior proposal, and why external calendar writes need conflict reconciliation.
4. **Operator and recovery (about 45 seconds):** show a handoff event, persisted session status, provider health, and clear failure/retry state. Explain transcript retention and that audio retention is disabled until encrypted storage and purge are configured.
5. **Evidence and limits (about 45 seconds):** show the 40/40 development and 80/80 held-out text API reports alongside the separated answer labels, then state the live microphone and latency limits exactly as recorded in the handover.

## Content angles

- **Product design:** A voice UI that exposes actual connection, transcript, slot, and booking state, with full keyboard/text access.
- **Reliability engineering:** Confirmation-bound proposals, local capacity claims, idempotent booking operations, and clear provider conflict handling.
- **Evaluation discipline:** Deterministic calendar truth, disjoint held-out scenario templates, separate audio/text results, and no invented accuracy or latency.

## Verified screenshot register

The local browser captures were visually inspected on 2026-09-28 at 1440, 1024, and 390 px; no clipping or overlap was found in the verified set. These eight selected images are real captures from the running local app; `04-studio-1024.png` and `09-operator-1024.png` are additional verified breakpoint captures in the same directory.

| View | Viewport | Verified file |
| --- | ---: | --- |
| Login | 1440 px | [01-login-1440.png](screenshots/verified/01-login-1440.png) |
| Validation error | 1440 px | [02-login-error-1440.png](screenshots/verified/02-login-error-1440.png) |
| Studio | 1440 px | [03-studio-1440.png](screenshots/verified/03-studio-1440.png) |
| Studio mobile | 390 px | [05-studio-390.png](screenshots/verified/05-studio-390.png) |
| Proposal review | 1440 px | [06-review-1440.png](screenshots/verified/06-review-1440.png) |
| Booked result | 1440 px | [07-booked-1440.png](screenshots/verified/07-booked-1440.png) |
| Operator console | 1440 px | [08-operator-1440.png](screenshots/verified/08-operator-1440.png) |
| Operator mobile | 390 px | [10-operator-390.png](screenshots/verified/10-operator-390.png) |

## Resume bullet templates using measured evidence only

- Built a reproducible synthetic appointment corpus for an independent voice receptionist portfolio project: **8 services, 6 staff resources, 3 zones, 400 customers, and 600 appointments** with a configurable reference date and seed.
- Validated **600/600 generated appointments** for referential integrity, service duration, hours, blackouts, and confirmed-resource overlap in the deterministic fixture gate; this is a data correctness result, not live booking reliability.
- Designed a separated **40-case development / 80-case held-out** conversation evaluation set with **20 complete synthetic audio scripts**, keeping ground-truth outcomes outside runtime prompts and retrieval.
- Measured **80/80 correct held-out text API outcomes**, **50/50 exact target times**, and **zero unauthorized mutations** across 60 observed appointment mutations on one recorded source revision; live voice performance remains unmeasured.

Only add live-call completion rates, latency, customer value, or commercial results after those values have been measured and recorded with denominators.

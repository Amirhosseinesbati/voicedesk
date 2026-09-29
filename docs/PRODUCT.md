# VoiceDesk product

VoiceDesk is an independent portfolio project for **Cedar Home Services**, a fictional residential maintenance business. Its pilot offer is a browser voice receptionist with a staff calendar and an operator console. Every seeded person, booking, policy, and call script is synthetic.

## Users and value

| User | Primary work |
| --- | --- |
| Customer | Ask about eligible services and starting prices; find a qualified available time; book, move, or cancel an owned visit after explicit confirmation. |
| Operator | Review the day/week calendar, transcript and structured call outcome, knowledge sources, failed calls, and human handoffs. |
| Administrator | Configure users, business policies, services, retention, and connector health for one customer installation. |

## Required customer flow

1. Open a session in English. The browser asks for microphone permission only when voice is started. The studio shows actual connection and listening/processing/speaking states, mute/stop, transcript status, and a complete text alternative. Audio retention is off by default; transcript retention is on with configured retention controls.
2. The semantic workflow extracts service, service zone, desired date and time, duration, customer identity/contact, and timezone. It asks for missing or ambiguous details. A relative date becomes an exact local date and timezone before a proposal is accepted.
3. Service/pricing answers cite the curated fictional knowledge source visible to the operator. Availability comes from the selected calendar adapter and qualified staff schedule. A suggestion is not a reservation.
4. A booking requires a precise summary and an explicit customer confirmation. The server rechecks availability and eligibility, claims local capacity transactionally, and records an idempotent booking operation. A stale proposal returns a conflict and alternatives.
5. A move or cancellation requires booking ownership verification. A move keeps the old appointment until the replacement commits safely. Reconnects, duplicate calls, and ambiguous provider responses must not create silent duplicate changes.
6. An interruption supersedes prior assistant audio and any unconfirmed pending proposal. Persistent audio failure, emergency requests, and unsupported work create a factual human handoff, with no invented booking.

## Modes

| Mode | Behavior |
| --- | --- |
| `DEMO` | Reproducible local calendar and structured fixtures, synthetic data, and local outbox. Any scripted transcript or audio replay is labelled as simulation. No real customer notification or payment is sent. |
| `CONNECTED` | Configured model/audio providers and optional Google Calendar access. Provider credentials, IDs, and destinations are server configuration. A failed connected request surfaces an error; it never becomes simulated success. |

The streaming audio connection is separate from the durable semantic booking graph. LangGraph checkpoints meaningful turns, proposals, confirmation, booking operations, and handoffs rather than raw audio frames. Local slot claims prevent two local one-capacity bookings. Uncontrolled external calendar writers can still cause a provider conflict; the integration rechecks and reconciles that outcome.

## Interface direction

The studio uses dark ink navigation, a cream work surface, emerald availability, and a restrained waveform driven by real audio activity. It combines call controls, live transcript, captured details, and the calendar timeline. The operator console includes a day/week calendar, booking details, call history, handoff queue, knowledge citations, and provider health. Every voice task also has a keyboard/text path. Mobile and desktop layouts, visible focus, semantic labels, reduced motion, and explicit empty/disconnected/failure states are part of v1.

## Explicit scope boundaries

Telephony/SIP, outbound calling, additional languages, payment collection, self-service SaaS tenancy, billing, and Kubernetes are optional future work. The commercial starting point is one customer per installation with workspace-scoped records and a second seeded isolation workspace for access tests. The pilot must pass the verified gates in [EVALUATION.md](EVALUATION.md) before any claim of production readiness.

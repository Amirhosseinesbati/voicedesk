# Commercialization notes

VoiceDesk is an **independent portfolio project** and a starting point for paid installation/customization, not an existing customer product or a claim of production readiness.

## Ideal buyer and offer

The first buyer is a single-location or regional home-services business that already has a calendar, receives repeated service/pricing and scheduling questions, and has an operator who can review exceptions. The v1 offer is a browser voice receptionist plus a customer calendar connection, seeded business policies, operator console, and deployment support. One customer per installation keeps retention, access, and service rules straightforward. The optional sales modules are voice transport, structured slot collection, appointment policy/calendar adapter, and booking operation ledger.

## Customer onboarding sequence

1. Confirm business owner, decision maker, service area, supported services, durations, staff/resource capacity, working hours, closure dates, and timezone.
2. Agree on what the assistant may answer from approved policy sources and which requests require handoff. Review emergency wording and local verification for booking changes.
3. Set up a customer-owned model/audio account and a spending cap. Store credentials only in server-side deployment secrets. Select model IDs and voice/provider region in configuration.
4. Connect an authorized Google Calendar test calendar or use the local calendar adapter. Map external calendar IDs, writer permissions, and reconciliation process.
5. Set transcript/audio retention and redaction with the buyer. Audio retention stays off unless explicitly enabled and documented. Set backup, restore, and access roles.
6. Import or configure real services, staff, zones, hours, and approved policy articles; remove the synthetic demo namespace and example credentials from the customer installation.
7. Run a sandbox pilot with scripted edge cases and operator review, then a small authorized live-call smoke test. Record actual text/audio outcomes, p50/p95 latencies, failures, and spend.
8. Agree on support ownership, provider outage handling, log retention, calendar conflict escalation, and change control before live customer traffic.

## Deployment prerequisites

The documented deployment uses Docker Compose, PostgreSQL, a FastAPI application, and a browser client behind HTTPS. A real deployment needs a trusted domain and TLS termination, database backup/restore and monitoring, server secrets, a configured model/audio provider, approved calendar credentials, privacy/retention terms, and an operator response process. Google Calendar integration does not make local transactions atomic with external writers; the business must accept and rehearse conflict reconciliation.

## Configurable monthly cost model

Rates change by vendor and region. Populate this worksheet from the **current contract and provider price pages** before quoting a customer; the variables below are not vendor prices or a sales estimate.

| Variable | Meaning | Example input source |
| --- | --- | --- |
| `C` | Connected calls/month | Buyer call forecast |
| `m` | Average billable audio minutes/call | Pilot measurement |
| `t_in`, `t_out` | Model input/output tokens/call | Tracing or provider usage |
| `r_stt`, `r_tts` | STT and TTS cost per billed minute (or convert character billing) | Current provider contract |
| `r_in`, `r_out` | Model cost per input/output token | Current provider contract |
| `s_gb`, `r_storage` | Retained GB and storage price/GB-month | Retention policy and host quote |
| `h`, `r_support` | Monthly maintenance hours and hourly support cost | Support agreement |

Monthly API/storage/support estimate: `C × (m × r_stt + m × r_tts + t_in × r_in + t_out × r_out) + s_gb × r_storage + h × r_support`. Add separate host/database, network egress, backup, observability, and any calendar-provider fees from current contracts. Estimate low/expected/high call volume and set a spending cap. The local demo has zero external API calls and no customer delivery costs.

## Supported integrations and v1 limits

The local calendar is the complete demo connector; Google Calendar is the specified connected connector subject to authorized credentials and live verification. Local confirmation messages go to a demo outbox. Any external notification channel requires separate approval and configuration. Telephony/SIP, outbound calls, multiple languages, payment collection, subscriptions, and a public multi-tenant SaaS are outside v1.

## Redistribution review

Use only assets and packages whose license obligations are checked in [DEPENDENCIES.md](DEPENDENCIES.md). The current design bundles DM Sans and Manrope under OFL-1.1; include the installed copyright and license notices with any redistributed font files. No externally sourced photograph, logo art, or voice recording is bundled. Synthetic audio scripts were written for this project; optional local TTS WAV output must be reviewed under the installed engine/voice terms before redistribution. Do not promise rights to any real customer content, voice, calendar data, or provider output without the relevant contract.

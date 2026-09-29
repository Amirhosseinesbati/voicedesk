# Security and privacy

## Trust boundaries

The browser, speech transcripts, knowledge-base text, model output, and Google Calendar responses are untrusted inputs. FastAPI owns authorization, booking policy, proposal versions, and mutations. The model may extract details or draft a reply, but it cannot authorize an appointment. Session IDs and graph thread IDs are locators, not credentials.

The default installation serves one business. Each record is workspace scoped, including sessions, transcripts, appointments, proposals, handoffs, outbox entries, and checkpoints. The demo contains two seeded workspaces for isolation tests. Administrative, operator, viewer, and demo access must be distinct. A viewer must not mutate bookings, and a customer must pass the local booking verification step before changing an appointment.

## Browser sessions and actions

- Use password hashes, server controlled session cookies, and role checks at each route. Set `COOKIE_SECURE=true` behind HTTPS for deployment. Do not expose `APP_SECRET_KEY` or provider credentials to the web bundle.
- Protect cookie-authenticated mutations against cross-site requests. Restrict CORS to configured origins and check origin on the audio WebSocket handshake.
- Confirmation must carry the exact current proposal version. A correction, interruption, or new relevant turn invalidates the prior proposal. The commit path rechecks workspace, ownership, service rules, and capacity.
- Treat an operation ID as an idempotency key, not proof of authorization. Duplicate calls return the recorded outcome; provider timeouts need reconciliation before retry.

## Content and retention

Transcripts are retained by default for the operator. Audio retention is off by default. If audio is enabled, obtain the caller's consent and set retention and access rules for the customer deployment. Never present generated voices as human voices. The interface discloses AI generated speech and labels synthetic data.

Do not index or prompt with hidden evaluation answers. Do not let a retrieved policy page, transcript, or tool output replace system rules. Render text safely; escape spreadsheet exports against formula execution. Uploads and arbitrary URL fetches are outside the core v1 flow and must not be added without type, size, and network restrictions.

Keep secrets only in environment or a deployment secret manager. Redact tokens, customer contacts, and raw audio from logs and tracing. LangSmith tracing is optional and off by default. Include correlation IDs and operation IDs without full sensitive payloads.

## Deployment checks and residual risks

Before customer use: enable HTTPS, use unique secrets and strong operator passwords, restrict network exposure, define retention, configure encrypted backups and a restore drill, and test Google Calendar conflict/reconciliation with the customer's own calendar. The local transaction cannot prevent unrelated external calendar writers from racing. Live audio and model quality, interruption latency, and provider-specific failures require a credentialed test in the actual deployment environment. See [HANDOVER.md](HANDOVER.md) for verified and pending items.
Add rate limiting and account lockout at the trusted reverse proxy or identity layer before exposing login or verification endpoints to the public internet. These controls were not load-tested in the local demo.


# VoiceDesk API

The FastAPI application serves OpenAPI at `/openapi.json` and interactive reference pages at `/docs`. All paths below begin with `/api`. Times are ISO 8601; appointment and availability timestamps include an offset. The browser uses an HTTP-only signed session cookie. After login, send the returned `csrf_token` as `X-CSRF-Token` on every state-changing HTTP request. The server resolves the workspace from the authenticated user rather than a caller-supplied ID. Viewer accounts can read scoped records but cannot create sessions or mutate bookings.

## Authentication and discovery

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/login` | Sign in with `{email,password}` and receive user and CSRF token. |
| `GET` | `/auth/me` | Restore the signed-in user and CSRF token. |
| `POST` | `/auth/logout` | Revoke the current session. |
| `GET` | `/health` | Database liveness and server mode. |
| `GET` | `/health/providers` | Honest configured/simulated/unverified provider states. |
| `GET` | `/catalog` | Workspace services, zones, staff and eligibility IDs. |
| `GET` | `/knowledge` | Curated policy articles with source metadata. |
| `GET` | `/replays` | DEMO scripted audio replay catalogue. |

## Conversation and booking

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/sessions` | Create `{mode:"demo"|"connected",channel:"text"|"voice"}`. Mode must match the server. |
| `GET` | `/sessions` | Recent scoped sessions. |
| `GET` | `/sessions/{id}` | Session, finalized turns, observable events, stable slots and current proposal. |
| `POST` | `/sessions/{id}/turns` | Submit `{turn_id,text,source}`. Repeat the same turn ID/text to retrieve the saved result; changed text conflicts. |
| `POST` | `/sessions/{id}/proposals` | Create an exact booking proposal from service, zone, offset-aware start time, timezone and customer details. |
| `POST` | `/sessions/{id}/proposals/{proposal_id}/confirm` | Confirm with `{version,hash,confirmed:true,idempotency_key}`. The server rechecks availability and creates the appointment only after this call succeeds. |
| `GET` | `/calendar/availability` | Query `service_id`, `zone_id`, `date`, `timezone`; returns actual eligible local slots, and filters Google busy time when configured. |
| `GET` | `/appointments` | Scoped appointments; optional `from_at` and `to_at`. |
| `GET` | `/appointments/by-reference/{reference}` | Find an owned booking in this workspace. |
| `POST` | `/appointments/{id}/verify` | Exchange booking email and six-digit confirmation code for a short-lived action token. |
| `POST` | `/appointments/{id}/cancel` | Cancel using verification token and idempotency key. |
| `POST` | `/appointments/{id}/reschedule` | Move to an offset-aware new start using verification token and idempotency key. |
| `GET` | `/handoffs` | Human handoff queue. |
| `GET` | `/booking-operations` | External booking ledger, including pending or uncertain operations. |
| `POST` | `/booking-operations/{id}/reconcile` | Reconcile a Google Calendar operation before any uncertain retry. |

The returned proposal contains `version` and `hash`; present its exact service, zone, staff, local date, time, timezone and customer to the caller before confirmation. Corrections or an interrupted pending turn invalidate the prior proposal. A stale hash/version or busy slot returns a conflict, never a success-shaped booking. A successful booking response can include a one-time demo verification code. Do not write this code to transcripts or routine logs.

## Voice transport

Connect to `WS /api/sessions/{id}/stream` with the signed browser cookie from an allowed origin. The server checks role, workspace, session and mode before accepting. The first message is the actual connection state and retention disclosure. In CONNECTED mode the client sends `start`, `mute`, base64 PCM16 `audio_chunk` messages at 24 kHz with a stable `turn_id`, `end_turn`, `interrupt`, and `stop`. The server emits `status`, `transcript_delta`, finalized `transcript`, `reply_text`, `audio_chunk`, `done`, and `error`. Only a finalized transcript enters the durable LangGraph turn workflow. Audio frames are not checkpointed.

DEMO accepts `replay_turn` with `{turn_id,text}` from a labelled script and `interrupt`/`stop`; it does not represent microphone input. An interrupt suppresses pending speech and proposals. Once a booking commit has completed, its durable result is still returned and a change requires the verified cancel/reschedule flow. Reconnecting the WebSocket retains the server-owned session and completed turns; it starts a new audio transport after process restart.

## Errors and client contract

Validation errors use FastAPI's `422` shape. Domain errors return `{code,detail}` with `400` or `409`; calendar provider failures use `503`. Authentication failures use `401`; missing operator role or CSRF token uses `403`; another workspace's resource appears as `404`. Show the returned detail near the relevant control and re-read the session or availability after a conflict. The generated frontend contract is [`openapi.generated.ts`](../apps/web/src/lib/openapi.generated.ts); run `pnpm api:generate` or `pnpm api:check` from `apps/web` against a local API. `/openapi.json` is the source of truth.


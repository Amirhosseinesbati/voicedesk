# Architecture

VoiceDesk is a self-hostable modular monolith for one customer installation. Every business record carries a workspace ID; the demo seeds two isolated fictional workspaces. The UI has a studio for a caller and a console for an operator. FastAPI owns authorization and all business mutations. PostgreSQL is the deployment database; the explicitly labelled SQLite fallback is for local demo checks only.

```mermaid
flowchart LR
  Browser[React studio and operator console] -->|HTTPS, session cookie, JSON| API[FastAPI]
  Browser <-->|WebSocket audio and turn events| Audio[Audio transport]
  Audio -->|final transcript with stable turn ID| Graph[LangGraph semantic workflow]
  API --> Graph
  Graph --> Policy[Curated service policy]
  Graph --> Calendar[Calendar and booking application service]
  Calendar --> DB[(PostgreSQL business tables)]
  Graph --> CP[(PostgreSQL checkpoints)]
  Audio <-->|configured STT and TTS| VoiceProvider[OpenAI audio APIs]
  Graph <-->|configured structured output| Model[LangChain model adapter]
  Calendar <-->|free/busy and event API| Google[Google Calendar]
  Calendar --> Outbox[Booking operation and demo outbox]
```

The graph handles finalized semantic turns: interpretation, slot collection, clarification or policy lookup, availability, proposal, customer confirmation, revalidation, commit, and factual outcome. Frames and partial transcripts stay in the streaming transport. The browser may interrupt playback at once; the server rejects an action associated with an invalidated proposal or superseded turn.

```mermaid
flowchart TD
  Turn[Finalized turn] --> Interpret[Interpret and update slots]
  Interpret --> Route{Enough information?}
  Route -->|No| Clarify[Ask for missing or ambiguous details]
  Route -->|Policy question| Policy[Answer from curated source]
  Route -->|Booking intent| Availability[Query calendar availability]
  Availability --> Propose[Versioned proposal]
  Propose --> Confirm[Pause for explicit customer confirmation]
  Confirm -->|Correction or no| Turn
  Confirm -->|Yes, same version| Revalidate[Recheck authorization, rules and capacity]
  Revalidate -->|Available| Commit[Claim booking operation and commit]
  Revalidate -->|Conflict| Alternatives[Offer alternatives]
  Commit --> Receipt[Persist receipt and demo outbox message]
  Interpret -->|Unsupported or repeated failure| Handoff[Human handoff queue]
```

## Data model

```mermaid
erDiagram
  Workspace ||--o{ Service : owns
  Workspace ||--o{ ServiceZone : owns
  Workspace ||--o{ StaffResource : owns
  Workspace ||--o{ Customer : owns
  Workspace ||--o{ VoiceSession : owns
  Workspace ||--o{ Appointment : owns
  Workspace ||--o{ BusinessHours : sets
  Workspace ||--o{ Blackout : sets
  Workspace ||--o{ User : authorizes
  Service ||--o{ Appointment : booked_for
  ServiceZone ||--o{ Appointment : serves
  StaffResource ||--o{ Blackout : may_block
  StaffResource ||--o{ Appointment : fulfills
  StaffResource ||--o{ SlotClaim : capacity
  Customer ||--o{ Appointment : owns
  VoiceSession ||--o{ TranscriptTurn : records
  VoiceSession ||--o{ SessionEvent : observes
  VoiceSession ||--o{ Proposal : proposes
  VoiceSession ||--o{ Handoff : escalates
  Proposal ||--o| SlotHold : holds
  Proposal ||--o{ BookingOperation : confirms
  Appointment ||--o{ SlotClaim : claims
  Appointment ||--o{ BookingOperation : changes
```

The graph's thread ID and session ID are locators, never authorization. An authenticated request must verify workspace and role before it can read, stream, or resume either. Booking confirmation carries the proposal version and an idempotency key. The server rechecks current appointment state and available capacity in the same operation that claims a local slot. External provider calls are recorded with observable states so an ambiguous timeout can be reconciled rather than blindly repeated.

## Boundaries and limitations

- DEMO uses fictional data and local simulators. The connected adapter requires separately configured provider credentials and an explicit spending limit for live tests.
- Google Calendar free/busy and event writes cannot be atomic with unrelated calendar writers. External conflicts must be reconciled.
- No telephony, outbound calls, payment collection, or multilingual flow is in v1.
- Audio is not retained by default. A customer's retention settings, reverse proxy TLS, backups, and secrets management are deployment responsibilities.

See the four [architecture decisions](adr/001-audio-and-semantic-state.md) for the reasons and tradeoffs.


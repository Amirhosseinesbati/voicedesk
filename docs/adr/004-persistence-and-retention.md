# ADR 004: Separate graph checkpoints from business records

Status: accepted, 2026-09-27.

PostgreSQL holds business entities, transcript turns, booking operations, and LangGraph checkpoints. Graph state refers to scoped IDs, not large audio blobs. Approval is tied to an exact proposal version and checked again when the action executes. The database operation ledger owns external side effects and reconciliation; checkpoints alone do not prevent duplicate provider writes.

Transcripts are retained by default for the operator view. Audio retention is disabled by default and needs explicit configuration. A deployment must set retention periods and protect backups in line with customer policy.

Tradeoff: PostgreSQL adds a service to operate; an explicit SQLite fallback exists only to make a local demo practical without Docker and does not stand in for PostgreSQL locking verification.


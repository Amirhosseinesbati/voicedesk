# ADR 002: Local calendar is authoritative for local capacity

Status: accepted, 2026-09-27.

The local appointment store applies service, zone, resource, business-hour, blackout, and overlap rules at confirmation time inside a transaction. An operation ID and proposal version make retries safe and reject superseded confirmations. The Google Calendar adapter is an external projection and availability input; its writes and ambiguous timeouts must be reconciled through the operation ledger.

This local lock cannot make independent Google Calendar writers atomic. A provider conflict is surfaced as a conflict or reconciliation state. A reschedule retains the old appointment until the replacement is secured; cancellation and rescheduling require booking ownership verification.

Tradeoff: one business per installation and workspace scoped records are simpler than a shared SaaS scheduler, while still allowing two demo workspaces to verify isolation.


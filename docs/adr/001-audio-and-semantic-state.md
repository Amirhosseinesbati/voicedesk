# ADR 001: Keep audio transport outside the semantic graph

Status: accepted, 2026-09-27.

Audio frames and partial transcripts are transient transport data. Only finalized user turns, proposals, approvals, actions, and observable outcomes belong in LangGraph state. The browser and API exchange audio over a WebSocket while the semantic turn enters a checkpointed graph. This avoids a database write per frame and permits reconnection to the same server-owned session. A new provider connection may be needed after process restart; durable conversation and booking records remain available.

Tradeoff: a reconnect cannot resume the exact audio sample at which a socket failed. The UI must show the connection break and invite the caller to restate any incomplete turn.


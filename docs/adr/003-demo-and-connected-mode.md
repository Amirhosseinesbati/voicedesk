# ADR 003: Explicit demo and connected modes

Status: accepted, 2026-09-27.

DEMO uses a seeded fictional business, deterministic fixtures, a local calendar, and a demo outbox. CONNECTED uses configured model, audio, and calendar adapters. The same booking and authorization rules run in both modes. A missing key or provider error in CONNECTED mode is an error; it never becomes a simulated successful call.

Tradeoff: deterministic demo parsing may not understand every free-form sentence. The UI provides a text alternative and asks for clarification. Fixture evaluation is reported separately from live model and microphone results.


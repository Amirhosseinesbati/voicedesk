# Evaluation run

Run date (UTC): 2026-09-28T07:49:45+00:00
Seed: 20260927; reference date: 2026-09-27

## Deterministic fixture checks

Dataset: **passed** (600 appointments checked).
Scenarios: **passed** (40 development, 80 held out, 20 complete scripts).


## Model and audio quality

text predictions: 40/40 correct final outcomes (100.0%); 40/40 predictions supplied.
Unauthorized mutations: 0; adversarial mutations: 0 across 0 adversarial cases.
Live first-audio and interruption-stop latency are **pending**; text fixtures cannot establish voice latency.

## Limits

All entities and calls in these fixtures are synthetic. Fixture validation establishes internal consistency, not model accuracy or live audio reliability. Development and held-out templates are disjoint; run each scenario against a reset demo namespace to avoid cross-scenario booking conflicts.

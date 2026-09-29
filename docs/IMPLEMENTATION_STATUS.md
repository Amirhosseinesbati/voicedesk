# Implementation status

Updated: 2026-09-28. This file records work against the VoiceDesk brief. It is not a claim of release readiness.

## Product and architecture plan

1. Build a FastAPI modular monolith with workspace scoped records, local transactional calendar, Google Calendar adapter, versioned booking proposals, and an idempotent booking operation ledger. PostgreSQL is the deployment database. An explicitly labelled SQLite demo fallback permits local verification on machines without Docker.
2. Keep live audio transport separate from semantic conversation state. A WebSocket carries audio and connection events; finalized turns enter a LangGraph workflow. Persist meaningful state transitions and expose text input through the same turn endpoint.
3. Build a React studio and operator console against the API. A demo mode uses synthetic data and deterministic fixtures; connected mode requires configured model, audio, and calendar credentials. Never fall back from a failed connected call to synthetic success.
4. Generate a fixed seed full dataset and held out scenarios. Verify the booking invariants, ownership, workspace boundaries, and UI journeys. Record actual evaluation results and visual inspection at three widths.
5. Deliver Compose, lockfiles, migrations, setup and operations instructions, architecture decisions, an evidence based handover, and an honest portfolio case study.

## Current state and evidence

- API, React studio/operator console, local calendar, Google adapter, LangGraph semantic turns/checkpoints, WebSocket audio transport, auth/workspace scoping, migrations, Compose and lockfiles are implemented. An explicit DEMO reset, a connected Cedar pilot bootstrap (catalog and first admin, no demo customers), and an explicit workspace retention purge CLI exist.
- A fresh local SQLite migration and full DEMO seed completed: 8 services, 6 staff, 3 zones, 400 customers and 600 appointments. Deterministic fixture evaluation passed 600/600 appointment invariants, 40/80 scenario split and 20/20 scripted audio fixtures. It does not establish voice/model accuracy.
- `scripts/smoke_api.py` passed: auth, availability, no booking before confirmation, stale proposal rejection, duplicate confirmation idempotency, verified cancellation and workspace isolation. Final backend `pytest` passed 7 tests covering concurrent slot claims, Google uncertain reconciliation and batched availability, scoped DEMO reset, checkpoint-aware retention purge, CONNECTED bootstrap, DST fold/gap, ambiguous-phrase handoff routing, and sourced policy routing. `ruff check . --no-cache` passed.
- Frontend `pnpm lint`, `pnpm typecheck`, `pnpm build` and `pnpm api:check` exited 0. `pnpm test:e2e` passed 2/2 Playwright journeys with one worker. A responsive test found no global horizontal overflow at 1440, 1024 and 390 px. Ten real screenshots are in `docs/screenshots/verified`; eight selected captures are linked in PORTFOLIO.md.
- As a Docker-independent availability check on this host, the SQLite DEMO was served on `127.0.0.1:5188` with its API on `127.0.0.1:8000`; browser entry, proxied health, login and authenticated session returned HTTP 200. Port 5173 was already occupied by another local project.
- `docker compose config -q` exited 0. Docker Engine is reachable, and an ignored `.env` now has randomly generated local application and database secrets. The API image build stopped when Docker Desktop reported an internal storage I/O error while the Windows C drive had less than 1 GB free. BuildKit cleanup also failed on its metadata store; a clean-source legacy build reached the daemon but hit the same storage error. WSL kernel logs subsequently confirmed EXT4 read/write/journal errors on Docker's `sdd` data disk, so freeing space alone may not repair the store. No VoiceDesk containers were started, so PostgreSQL migration and restore remain unverified. Other projects have running containers and were left untouched. No OpenAI or Google credentials were available; connected live booking, voice latency and calendar reconciliation need authorized provider tests.
- Python mypy passed a bounded, explicit ten-file scope (configuration, domain, schemas, models, calendar, auth, seed, audio, knowledge and prompts). A full `mypy src` run still reports 99 errors in the remaining API/graph/booking modules; CI checks the passing scope and this debt is open.
- Final-source, single-worker text replay passed 40/40 development outcomes and 80/80 held-out outcomes, with 20/20 and 50/50 exact target times respectively. The held-out run recorded 60 appointment mutations, zero unauthorized mutations, 10/10 adversarial cases with zero mutations, and zero worker errors. All 10 development policy answers carried the expected `kb:<service>` citation. Start/end source SHA-256 matched across both runs. Earlier failures and invalid fixture diagnostics are preserved and explained in `docs/EVALUATION.md`.

## Next verification gates

1. Free host storage and repair Docker Desktop's failing data disk with the owner aware of the other running containers; only then build/start Compose, run PostgreSQL migration/concurrency checks and a disposable restore smoke test.
2. Configure authorized OpenAI and Google sandbox credentials with a spending limit, run live microphone and calendar tests, measure first-audio/interruption latency, and check uncertain-operation reconciliation.
3. Expand full-API mypy coverage, schedule retention cleanup and add public-facing login/verification rate limiting before customer deployment.


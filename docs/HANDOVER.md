# VoiceDesk handover

Date: 2026-09-28. VoiceDesk is an **independent portfolio project** for fictional Cedar Home Services. Every seeded customer, appointment, call and outbox item is part of a **Synthetic demo dataset**. This is a working local commercial pilot starting point, with the deployment and live-provider gates below still open. The final local Git revision is identified in the current commit section.

## Launch

From this directory in Windows PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up --build
```

Set unique `APP_SECRET_KEY` and `POSTGRES_PASSWORD` in `.env` before the Compose command. An ignored local `.env` with randomly generated values for both now exists on this host. Open `http://localhost:8080`; API reference is at `http://localhost:8000/docs`. On POSIX, use `cp .env.example .env`, edit it, then `docker compose up --build`. The API container applies Alembic migrations and idempotently seeds the full DEMO dataset on startup. Docker Engine is reachable, but Docker Desktop reported internal storage I/O errors during image build while the Windows C drive had less than 1 GB free; WSL kernel logs also showed EXT4 errors on its data disk. Compose startup and the PostgreSQL restore drill are still pending.

For a Docker-free DEMO on this Windows host, use Python 3.12, uv, Node 24 and pnpm 11 in two terminals:

```powershell
cd apps/api
$env:APP_MODE = 'demo'
$env:DATABASE_URL = 'sqlite:///./voicedesk-demo.db'
$env:DEMO_DATA_SIZE = 'full'
uv sync --frozen
uv run alembic upgrade head
uv run python -m voicedesk.seed
uv run uvicorn voicedesk.main:app --port 8000
```

```powershell
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:5173`. The POSIX equivalents are in [README.md](../README.md). SQLite is an explicit local fallback; PostgreSQL locking and restore behavior must be rechecked before customer deployment.

During this host's Docker storage investigation, the SQLite DEMO was also served on `http://127.0.0.1:5188` because port 5173 belonged to another local project. The browser entry point and its proxied API health, login, and authenticated session all returned HTTP 200. This is a local development session, not a Compose/PostgreSQL result.

## Demo accounts

| Role/workspace | Email | Password |
| --- | --- | --- |
| Cedar operator | `operator@cedar.example.com` | `DemoVoiceDesk2026!` |
| Cedar admin | `admin@cedar.example.com` | `DemoVoiceDesk2026!` |
| Cedar viewer | `viewer@cedar.example.com` | `DemoVoiceDesk2026!` |
| Harbor operator (isolation check) | `operator@harbor.example.com` | `DemoVoiceDesk2026!` |

These accounts are synthetic DEMO fixtures. Remove or replace them before any connected customer installation. The browser studio offers a text alternative and labelled scripted replay. DEMO microphone capture is intentionally unavailable because it would not constitute live speech verification.

## Verification matrix

| Area | Observed status and limit |
| --- | --- |
| Full synthetic data | Passed generator/validator: 8 services, 6 staff, 3 zones, 400 customers, 600/600 internally consistent appointments; 40 development, 80 held-out scenarios and 20 complete scripts. |
| Local booking workflow | Passed API smoke: auth, availability, zero appointment before confirmation, stale correction rejection, duplicate confirmation idempotency, verified cancellation and workspace isolation. Backend `pytest` passed 7 tests covering a simultaneous one-capacity booking race, DST fold/gap, Google uncertain/create reconciliation and batched busy intervals, scoped DEMO reset, checkpoint-aware retention purge, CONNECTED bootstrap without demo customer records, handoff priority after an ambiguous phrase, and a sourced policy answer despite a non-scheduling date phrase. |
| Browser journey | Passed 2/2 one-worker Playwright tests: login and text turn through persisted booking, operator calendar, invalid code error, valid owner verification, and responsive overflow checks. Ten real captures at 1440/1024/390 px are in [`screenshots/verified`](screenshots/verified). Eight are selected in [PORTFOLIO.md](PORTFOLIO.md). |
| Frontend checks | `pnpm lint`, `pnpm typecheck`, `pnpm build`, and `pnpm api:check` all exited 0. The generated types matched the running API OpenAPI schema. The final `pnpm test:e2e` passed 2/2 tests with one worker in 6.9 s using local Chrome, including no global horizontal overflow at 1440/1024/390 px. |
| Conversation outcome target | Final-source, one-worker text API replay passed 40/40 development and 80/80 held-out final outcomes; 20/20 and 50/50 exact target times respectively. The held-out run recorded 60 appointment mutations, zero unauthorized mutations, 10/10 adversarial cases with zero mutations, and zero worker errors. All 10 development policy answers cited the expected knowledge source. Source SHA-256 matched at the start and end of both runs; details and earlier diagnostics are in [EVALUATION.md](EVALUATION.md). These numbers do not measure live speech. |
| Connected model/audio | Code path and configuration exist. No OpenAI credentials or spending limit were supplied, so live microphone booking, speech quality and p50/p95 latency are unverified. No synthetic replay is counted as live voice. |
| Google Calendar | Adapter, bounded calls, operation ledger and reconciliation path are implemented. Live calendar access/conflict behavior is unverified without authorized Google credentials and a sandbox calendar. Local transactional claims do not guarantee atomicity against outside calendar writers. |
| PostgreSQL/Compose/restore | `docker compose config -q` exited 0. An ignored `.env` has random local secrets. Docker daemon access was confirmed, but both BuildKit and legacy API builds failed on Docker Desktop storage I/O errors; WSL logged EXT4 read/write/journal errors on its data disk. No VoiceDesk container was started. PostgreSQL migration/locking and restore smoke test are pending. |
| Audio fixture files | Twenty complete scripted TTS fixtures and a dry-run generator are present. WAV files were not rendered because no approved offline voice renderer/asset rights were available. |

## Next customer-specific steps

1. Run the one-time CONNECTED bootstrap described in [README.md](../README.md) with a new admin password, then configure the business's real service catalogue, zone eligibility, hours, holidays, staff, pricing policy, timezone, retention period, and operator accounts. The bootstrap catalogue is explicitly fictional and synthetic. Review content and voice disclosure with the customer.
2. Deploy behind HTTPS with a unique signing secret, secure cookies, restrictive CORS/origin rules, PostgreSQL backup schedule, and a tested restore. Replace DEMO credentials and review the full dependency/license inventory.
3. Configure an authorized OpenAI key/model IDs and, if used, a Google service account shared with a dedicated customer test calendar. Use a fixed spending limit. Run the live microphone booking/interruption tests and measure first-audio and interruption-stop latency; reconcile any ambiguous calendar operation before retry.
4. Run a separate live audio evaluation and operator review in the customer environment. Complete the open deployment, rate-limit, retention-scheduling, and full-type-coverage gates in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Current commit

The application revision used for the measured text replay is tagged `voicedesk-pilot-2026-09-28`. Resolve its exact hash with `git rev-parse voicedesk-pilot-2026-09-28`. Later local changes only narrow the Docker build context and record the Docker host storage failure. No remote deployment or publication was performed.


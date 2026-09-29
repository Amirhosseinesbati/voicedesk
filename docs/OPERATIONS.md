# Operations

## Start and health

Copy `.env.example` to `.env`, set unique `APP_SECRET_KEY` and `POSTGRES_PASSWORD`, and choose `APP_MODE=demo`. With Docker Engine running, use `docker compose up --build` from the repository root. The web entry point is `http://localhost:8080`; the API is available at `http://localhost:8000`. The API container runs schema migrations and idempotent demo seeding before serving traffic. Use the health and provider health endpoints to distinguish an up API from a configured audio/calendar provider.

On a workstation without Docker, use the documented SQLite DEMO fallback in [README.md](../README.md). SQLite is not the commercial concurrency target; run PostgreSQL migration and locking checks before installation.

To reset only the two seeded DEMO workspaces after stopping active demo calls, run `docker compose exec api python -m voicedesk.reset_demo --confirm`. The command refuses `APP_MODE=connected`, clears only the `cedar-demo` and `harbor-demo` business records and their prefixed graph checkpoint threads, then reseeds the configured demo size. For a local SQLite demo, run the same module from `apps/api` with `APP_MODE=demo` and the intended `DATABASE_URL` set. A reset is destructive for those synthetic workspaces, so export any demo evidence you want to keep first.

For a fresh CONNECTED database, start the API after migrations and run `docker compose exec api python -m voicedesk.bootstrap_connected --email admin@your-domain.example`. The CLI prompts for a strong password and refuses to reuse DEMO credentials or an already initialized installation. It seeds only the fictional Cedar catalogue/curated policies and a new admin; no demo customers, appointments, or demo accounts are copied. This is pilot configuration, so review and replace services, zones, hours, policy text, and staff with the customer's authorized values before serving real callers. See the mode setup in [README.md](../README.md).

## Backups and restore

The PostgreSQL volume contains business tables and graph checkpoints. Schedule encrypted `pg_dump` backups, retain them according to customer policy, and protect access to backup files. For a manual Compose backup:

```sh
docker compose exec db sh -c 'pg_dump -U voicedesk -Fc voicedesk > /tmp/voicedesk.dump'
docker compose cp db:/tmp/voicedesk.dump ./voicedesk.dump
```

Restore only to a disposable database for a smoke test. Create that database, copy the dump into the DB container, restore it, then query counts for sessions, appointments, operations, and checkpoint tables:

```sh
docker compose cp ./voicedesk.dump db:/tmp/voicedesk-restore.dump
docker compose exec db createdb -U voicedesk voicedesk_restore
docker compose exec db pg_restore -U voicedesk -d voicedesk_restore /tmp/voicedesk-restore.dump
docker compose exec db psql -U voicedesk -d voicedesk_restore -c '\dt'
```

Do not replace a live database with a dump as a verification exercise. Reconcile any in-flight provider operation after a real restore. If audio retention is enabled and files are stored outside PostgreSQL, back up that scoped storage separately. The current host's Docker daemon is reachable, but an internal storage I/O error prevented the image build; WSL also reported EXT4 read/write/journal errors on Docker's data disk. A real restore smoke test is pending. Check host free space and repair the Docker data store before retrying. Preserve other running projects' containers and volumes during recovery.

## Connector setup

DEMO uses the local calendar, deterministic conversation fixtures, and a demo outbox; it sends no messages. For CONNECTED, provide an OpenAI API key and model IDs through environment variables, select `CALENDAR_PROVIDER=google`, share the customer's calendar with an authorized service account, and configure `GOOGLE_CALENDAR_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON`. The latter accepts single-line service-account JSON or a path inside the API container. For a file path, mount a local ignored `secrets/google.json` read-only at `/run/secrets/google.json` through a Compose override and set the variable to that container path. Never commit the key. Use a dedicated test calendar and a spending limit for the first live checks. The server must report missing or failed connectors as errors, not synthetic success. See [Google Calendar credentials](https://developers.google.com/workspace/guides/create-credentials) and [free/busy reference](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query).

## Changes, retries, and retention

Apply Alembic migrations before API startup. Run the full synthetic generator explicitly when changing demo scenarios; record seed, reference date, and counts in the data card. A demo reset is limited to demo workspaces. Keep operation IDs stable across retries and inspect the operation ledger after ambiguous Google timeouts before retrying provider writes. A proposed slot is not a reservation; every confirmation rechecks capacity.

Set `RETENTION_DAYS` for the customer's policy. Retention cleanup is an **explicit CLI operation**, not an automatic scheduler: run `docker compose exec api python -m voicedesk.purge_retention --workspace <workspace-id> --confirm` from an authorized maintenance window. It deletes expired transcript turns, session events, handoffs, demo outbox rows and their scoped graph checkpoint threads for that workspace, and scrubs old session slots/replies. Booking business records follow a separate customer policy. Record the run and check counts; schedule it externally if the customer requires automatic enforcement. Audio retention remains off until consent, storage protection, and a deletion process are configured. Keep optional tracing disabled or redacted by default. Back up before upgrades and test the restore procedure on a disposable database.


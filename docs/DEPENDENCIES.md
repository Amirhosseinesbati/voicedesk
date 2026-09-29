# Dependencies and redistribution review

This records what is selected and what has actually been verified for the pilot. A package version in a manifest is not evidence that its container build or live provider path has passed. Recheck supported releases, security advisories, and license obligations before customer redistribution.

## Runtime and lock status

| Component | Declared version or exact image tag | Evidence/status |
| --- | --- | --- |
| Python API | Python `>=3.12,<3.14`; Docker `python:3.12.13-slim-bookworm` | Declared in `apps/api/pyproject.toml` and Dockerfile; container build validation pending. |
| Python dependency manager | `uv==0.12.19` in API Dockerfile | Declared; `apps/api/uv.lock` is present and a local `.venv` was inspected on 2026-09-28. Container frozen install remains to be verified. |
| PostgreSQL | `postgres:17.11-alpine3.24` | Exact Compose tag declared; migration and backup/restore verification tracked separately. |
| Frontend build | `node:24.13.0-alpine3.23`, `pnpm@11.19.0` | Dockerfile/package manifest declarations. `apps/web/pnpm-lock.yaml` is present. |
| Frontend serving | `nginx:1.29.5-alpine3.23` | Exact Dockerfile tag declared. |

The direct Python packages in `apps/api/pyproject.toml` use version ranges; the following **resolved local `.venv` versions** were read from `importlib.metadata` on 2026-09-28. This is package-install evidence, not a claim that every API path or container image passed tests.

| License expression or installed metadata | Direct Python packages and locally installed versions |
| --- | --- |
| MIT | `alembic` 1.20.0; `argon2-cffi` 25.1.0; `fastapi` 0.141.1; `httplib2` 0.32.0; `langchain` 1.4.2; `langchain-core` 1.6.5; `langchain-openai` 1.6.6; `langgraph` 1.2.12; `langgraph-checkpoint-postgres` 3.1.2; `langgraph-checkpoint-sqlite` 3.1.1; `pydantic-settings` 2.15.0; `sqlalchemy` 2.1.1. |
| Apache 2.0 / Apache-2.0 | `google-api-python-client` 2.200.0; `google-auth` 2.58.1; `google-auth-httplib2` 0.4.2; `openai` 2.54.0. |
| BSD-3-Clause | `uvicorn` 0.54.0; `websockets` 16.1.1. |
| Unlicense | `email-validator` 2.3.0. |
| LGPL-3.0-only | `psycopg` 3.3.6. Its obligations and the `psycopg[binary]` extra need explicit redistribution review before a customer image is delivered. |
| Installed LICENSE file; identifier pending inspection | `itsdangerous` 2.2.0. Its metadata did not expose a license expression, though `LICENSE.txt` is present. |

Development-only installed packages: `httpx` 0.28.1 (BSD-3-Clause), `mypy` 1.20.2 (MIT), `pytest` 9.1.1 (MIT), and `ruff` 0.16.9 (MIT). `hatchling` is a build requirement in the manifest but was not present in the inspected runtime environment; verify its resolved lock/version and license from the build environment. The installed distributions listed above each had a license file in their package metadata except that `hatchling` was not installed. Python transitive packages and the `psycopg-binary` wheel still require a full inventory before distribution.

The frontend manifest fixes these direct versions, and local `node_modules` package metadata and license files were inspected on 2026-09-28:

| License reported by installed package metadata | Direct packages and installed versions |
| --- | --- |
| MIT | `@tanstack/react-query` 5.104.0; `react` 19.3.0; `react-dom` 19.3.0; `@eslint/js` 9.39.1; `@tailwindcss/vite` 4.3.3; `@types/node` 24.19.0; `@types/react` 19.3.0; `@types/react-dom` 19.3.0; `@vitejs/plugin-react` 6.1.1; `eslint` 9.39.1; `eslint-plugin-react-hooks` 7.1.1; `eslint-plugin-react-refresh` 0.5.7; `openapi-typescript` 7.13.0; `tailwindcss` 4.3.3; `typescript-eslint` 8.70.1; `vite` 8.3.1. |
| ISC | `lucide-react` 1.48.0. |
| Apache-2.0 | `typescript` 5.9.3; `@playwright/test` 1.63.0. |
| OFL-1.1 | `@fontsource/dm-sans` 5.3.0; `@fontsource/manrope` 5.3.0. The installed font packages contain their font license text. |

These identifiers and files verify the **direct local JS packages only**. Transitive dependencies, image layers, and any package versions changed by a later lock update still need a generated third-party notice/SBOM review before distribution. Retain required copyright and license notices in the customer build; verify any copyleft or additional notice obligation from the complete dependency tree. The presence of an open-source license does not grant rights to provider APIs, voice models, customer data, or trademarks.

## Assets and voices

The current UI bundles **DM Sans and Manrope** through Fontsource under OFL-1.1. Keep each font's copyright notice and license with redistributed font files; do not sell the font files on their own or use reserved names for a modified version without permission. No third-party photograph, illustration, or real voice recording is bundled by the fixture work. `lucide-react` supplies interface icons under the installed package's ISC license; include its notice if distributing bundled code/assets. The 20 conversation scripts are generated original synthetic text. WAV files are **not** currently generated. Optional offline `pyttsx3` rendering and any installed operating-system voice have separate engine/voice terms that must be checked before redistributing rendered audio. Do not assume permission to bundle a provider-generated voice asset without its current contract.

## Release checklist for the dependency owner

1. Verify the committed `apps/api/uv.lock` with `uv sync --frozen` in the actual API image, and record the exact build/test environment result.
2. Run the frontend frozen install, typecheck/lint/build, and capture actual command results.
3. Produce a full Python/JS/container dependency inventory and retain required license notices. Confirm the source/redistribution terms for every bundled audio or visual asset.
4. Recheck provider model, STT/TTS, Google Calendar, and base-image terms before connecting customer accounts or quoting commercial use.

No commercial redistribution clearance is claimed while the pending items remain open.

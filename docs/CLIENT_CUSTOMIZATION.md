# Client customization guide

This pass turns the existing reception/booking pilot into a configurable workspace. Configuration is saved in the API database; it is not a browser-only preview. The operator studio remains an authenticated internal application, not a public customer booking widget.

## Safe local preview

Use the existing installed dependencies. From the VoiceDesk root, prepare the separate synthetic database once:

```powershell
.\scripts\preview_local.ps1 -Prepare
```

Then open two terminals in the same root:

```powershell
.\scripts\preview_local.ps1
```

```powershell
.\scripts\preview_local.ps1 -Web
```

Open <http://127.0.0.1:4315>. The API is on <http://127.0.0.1:8315/docs>. These commands explicitly select DEMO/local calendar mode and clear the process's OpenAI key. They bind to loopback. The preview database is `apps/api/voicedesk-upgrade-demo.db`, separate from existing demo databases. The default semantic SQLite checkpoint file is still project-local and uses unique session thread IDs.

The demo accounts use `DemoVoiceDesk2026!`:

| Account | Access |
| --- | --- |
| `admin@cedar.example.com` | Edit workspace configuration and operate bookings |
| `operator@cedar.example.com` | Operate bookings; read configuration |
| `viewer@cedar.example.com` | Read configuration and records |

No real messages, microphone permission or provider writes are needed to use this demo. Prepare seeds 24 synthetic customers and 36 fixture appointments. Subsequent seed runs preserve a customized business name, services and hours. An explicit DEMO reset removes those customizations too.

## Configure an existing customer workspace

1. Sign in as an admin and open **Workspace settings**.
2. Set the business name, welcome line, one of the three supported brand palettes and a valid IANA timezone. The brand palette is independent of the operator's Light/Dark/System appearance preference.
3. Set all seven opening days. A closed day has zero capacity. Open intervals must start before they end; overnight shifts and multiple daily intervals are not supported by this editor. Availability is the intersection of business hours, staff hours, eligibility, blackouts, occupied appointments and existing claims.
4. Edit existing service names/descriptions, duration in 15-minute increments, starting price in cents and whether the service is offered. At least one service must remain enabled. Starting-price currency and policy wording must be approved separately; the original fictional Cedar source uses USD. This editor does not collect payments.
5. Save. The API validates the complete configuration, verifies admin access and CSRF, checks service ownership, and advances a revision. A stale form receives HTTP 409; use **Reload saved settings** to replace its edits with the latest saved version.
6. Start a fresh conversation to use the new business timezone. Existing conversations retain their original timezone, and saved appointments retain their absolute times and durations. All pending proposals/holds are invalidated on a configuration save; review the current details again before booking.

The studio header and local assistant greeting/service clarification use the saved workspace name/catalogue. Disabled services disappear from new selection and local extraction. The booking timezone includes the configured zone. Studio form state resets between sessions, and catalogue zones are filtered by service eligibility.

## Policies are a separate approval step

The bundled knowledge base contains fictional Cedar policies. Changing a business name or any service definition sets a server-owned `policy_review_required` flag. Existing Cedar-specific policy answers are withheld; the assistant says an operator is needed rather than repeating obsolete prices or service promises. Theme/welcome-line changes alone do not invalidate policies.

This first pass does not include a policy-source management/approval UI. Before a real client pilot, replace or extend the approved, workspace-scoped policy source and its tests, then clear the review flag through a reviewed deployment migration/administrative procedure. Do not clear it merely to restore the old demo answers. Arbitrary new workspace IDs currently receive no verified policy source. Provider-backed extraction does not yet use a client-specific catalogue; that extension is outside the current pilot scope.

## Reuse for a new client installation

Keep the existing React/FastAPI/transactional-calendar/LangGraph boundaries. Provision the customer's workspace, admin, service zones, services, staff qualifications and staff weekly schedules in a reviewed bootstrap/catalogue import. IDs and staff/service/zone relationships are preserved by this editor; adding or deleting those entities is outside this first pass. Replace the Cedar login/demo copy and approved policy sources for the installation. Keep demo data and accounts out of CONNECTED installations.

Run `alembic upgrade head` before starting an older database. Migration `20261006_0002` adds workspace presentation JSON and preserves existing records. It tolerates a fresh initial migration that creates the current metadata. Previewing with SQLite does not establish PostgreSQL recovery/concurrency readiness. Workspace locks serialize configuration/proposal/confirmation transactions on PostgreSQL, and the revision update uses a database compare-and-swap for stale writers. PostgreSQL verification still requires an available authorized environment.

Configure real model/audio/calendar credentials separately, with an explicitly authorized payload/destination, spending limits and a sandbox calendar. A configured provider status is not evidence of accuracy or successful live operations. No external credentials, provider requests or publication were performed in this pass.

## Conversation recovery

- **Start a conversation** focuses the text composer. The first sent message creates a session; **New text session** starts a separate conversation.
- Text remains in the composer on an error. Resending unchanged text uses the same turn ID, including when the server saved it but its response was lost. Confirmation retries retain the same booking idempotency key for that proposal.
- Temporary refresh errors keep the saved session ID/transcript. Only a confirmed 404 offers a reset; reload resumes server-saved turns. Unsent drafts are component-local and are not guaranteed across page reload or navigation.
- Unexpected audio loss offers **Reconnect audio** in the same session or **Continue with text**. Reconnection never automatically requests microphone permission; the user initiates it. An interrupted, unfinalized audio turn may need repeating.
- Permission denied, missing microphone and busy-device failures have specific guidance. Audio connects have a 12-second handshake timeout; API requests have a 30-second timeout. Cancel/end/unmount release media and playback, and stale connection callbacks are ignored.

## Verification and evidence

See [UPGRADE_CHECKPOINT.md](UPGRADE_CHECKPOINT.md) for current results and the visual calibration status. Regression tests cover actual local confirmation-gated booking and simulated faults. They do not measure live speech/model accuracy, STT/TTS latency, Google Calendar behavior or Docker/PostgreSQL deployment.

The pre-existing user changes in README, .gitignore, IMPLEMENTATION_STATUS.md and teaser_assets were preserved. This guide and the checkpoint supplement those records.

## Appearance and portable hosting

The approved operations design offers **Dark**, **Light** and **System** on both sign-in and the authenticated workspace. A fresh installation uses Dark. Valid saved choices are honored; System alone follows live OS color changes. Preferences are browser-local (`voicedesk_appearance`, with the earlier `voicedesk_theme` key accepted on initial load). If storage is restricted, the choice still works in memory and the next full load safely defaults to Dark.

Switching appearance does not recreate the studio, interrupt its WebSocket, clear a transcript/draft/booking form, change the customer's branding, or call the API. Appearance is not a server workspace setting. The native selector works by keyboard, focus is visible, reduced motion is honored, and native inputs follow `color-scheme`.

Keep `public/theme-init.js` and `public/theme-base.css` in the built static distribution. The external bootstrap applies the saved choice before the application paints, without an inline-script CSP exemption; the external base stylesheet covers the loading canvas. Application CSS and semantic token overrides are in `src/styles.css` and `src/operations.css`. No global color inversion or image/media filters are used. New UI should use the semantic surface/text/status/accent roles in `operations.css` rather than adding hard-coded component colors.

Host the current distribution at the domain root, serve all built public assets, and proxy `/api` and WebSockets to the API. Subpath hosting requires an intentional Vite base/public-asset-path change and a fresh verification pass. The bootstrap's self-only CSP test covers the bootstrap, not a complete production CSP audit; existing inline waveform height styles and any chosen deployment policy should be reviewed together. See [THEME_ROLLOUT.md](THEME_ROLLOUT.md) for final rollout evidence and checks.

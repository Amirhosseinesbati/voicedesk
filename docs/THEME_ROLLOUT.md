# VoiceDesk appearance rollout — 2026-10-07

The approved A direction is implemented as a compact voice operations workspace, with equivalent Light, Dark and System modes. The earlier functional pass is retained: admin configuration, role/CSRF controls, confirmation-gated booking, idempotent retry, session recovery, configured timezones and policy review safeguards.

## Product changes

- Compact navigation and provider status, an audio control rack with distinct speech/text/reconnect states, a prominent saved transcript/composer and a booking inspector.
- Large introductory surfaces and the decorative audio orb were replaced with working controls. Workflow guidance is available in a disclosure rather than competing with the active conversation.
- Explicit semantic surface, text, border, accent, success, warning, error, info and focus roles. Both appearances support Forest/Ocean/Plum customer accents without recoloring source media.
- Dark fallback; persisted valid choices; initial legacy preference support; System-only live OS following; cross-tab preference updates; in-memory storage fallback. Theme changes update the root appearance and the selector, not the application/session tree.
- External prepaint bootstrap and critical loading stylesheet, native color-scheme, visible keyboard focus, reduced motion and tested 320/390/768/1024/1440px layouts.

## Evidence

Four representative synthetic local screenshots:

- [Studio — Dark desktop](screenshots/theme-rollout/studio-dark-desktop.png)
- [Studio — Light desktop](screenshots/theme-rollout/studio-light-desktop.png)
- [Operator calendar — Dark mobile](screenshots/theme-rollout/operator-dark-mobile.png)
- [Operator calendar — Light mobile](screenshots/theme-rollout/operator-light-mobile.png)

Capture command from the VoiceDesk root: `node scripts/capture_theme_rollout.mjs`. It uses installed headless Chrome, a 45-second capture deadline and same-origin request restrictions. All displayed people/appointments are synthetic. These are real local UI captures, not live-provider evidence.

## Verification

Final complete runs after the source edits:

- Frontend ESLint and TypeScript `tsc -b`: passed.
- Generated API contract check against local API 8315: passed.
- Production Vite build: passed, 1.13 seconds; JS 350.97 kB (104.96 kB gzip), CSS 66.69 kB (13.56 kB gzip). Public bootstrap/loading assets are present in `dist`.
- Playwright: **12/12 passed in 29.5 seconds**, one headless Chrome worker, 60-second overall bound. Includes the existing six product regressions and six appearance regressions.
- API Ruff (`src tests migrations`): passed. Full API pytest: **16/16 passed in 18.93 seconds**, within its 45-second bound.
- Sampled normal text/control/status contrast is at least 4.5:1 in both appearances; all three brand accent primary buttons also pass. This is a targeted computed-style check, not a complete WCAG conformance audit.
- Final owned-scope Git whitespace check: passed. Pre-existing user edits in README, `.gitignore`, IMPLEMENTATION_STATUS and teaser assets remain untouched.
- Four final screenshots refreshed after the last copy changes, visually inspected; capture reported no browser page errors.

The initial complete browser run found a transient button-color contrast issue; it was corrected, the focused six theme tests passed, and then the entire suite passed. Switching no longer crossfades foreground and background colors through an unreadable intermediate state.

The theme regressions cover preferences before the app bundle loads, both OS choices, invalid and legacy values, restricted storage, self-only script CSP bootstrap, System OS changes, explicit-choice isolation, keyboard/reduced motion, mid-conversation DOM/draft/field identity and zero appearance-triggered API requests. Existing replay recovery now checks theme switching while its synthetic WebSocket remains connected. The real local booking regression switches during an unsent request and checked confirmation review.

## Local preview and handoff

Use the existing installed dependencies and run `scripts/preview_local.ps1 -Prepare` once for the separate migrated synthetic database. Run `scripts/preview_local.ps1` for API 8315 and `scripts/preview_local.ps1 -Web` for frontend 4315 in separate terminals. See [CLIENT_CUSTOMIZATION.md](CLIENT_CUSTOMIZATION.md) for admin/operator demo access, migration and client provisioning guidance.

Docker deployment and live model/audio/calendar behavior were not verified in the local UI pass; no live AI accuracy or latency claim is made. The four final captures are committed repository evidence.

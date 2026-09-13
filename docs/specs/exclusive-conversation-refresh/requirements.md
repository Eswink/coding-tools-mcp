# Exclusive conversation and refresh requirements

Approved execution plan: [plan.md](plan.md). This spec describes intended behavior, not completed acceptance.

| ID | Requirement | Acceptance |
|---|---|---|
| R1 | Default one owner per workspace; first explicit authenticated chat request reserves 90s | Atomic competing claims; one pending record/event |
| R2 | Non-owner receives a stable non-OAuth locked error and no data/approval hint | 100 blocked requests; no pending/event/fingerprint; no login challenge |
| R3 | Local-only approval, nonempty subset, explicit fingerprint confirmation | IPC/HTTP negative tests; real component clicks; no public approve tool |
| R4 | Finite configurable lease, no implicit transfer/refresh renewal | Expiry/revoke/renew tests; idle defaults off |
| R5 | New owner waits for old admitted/async/interactive work to finish | Draining state with real child; durable crash fence; local generation-bound recovery |
| R6 | Global approval is reachable from all routes and tray | Foreground modal, background generic notice, tray badge/menu; snapshot resync and countdown |
| R7 | Authorization code with explicit offline consent yields refresh token | HTTP consent page, PKCE code exchange, scope normalization; legacy Actions unchanged |
| R8 | Rotation is atomic, replay revokes family, durable storage is authenticated and bounded | Reopen, wrong identity/resource/client, forged token, race, corruption and I/O failures |
| R9 | Access lifetime 5m..8h, refresh session 1..90d, chat lease 1h..30d, idle off or30m..24h | UI conversion plus Rust validation, migration, configuration restarts |
| R10 | Refresh family independent of chat/window identity | Same chat after actual refresh remains owner; B still locked with renewed credential |
| R11 | No secret or raw conversation metadata in approval UI/logs/notifications | Source inspection, synthetic canary scan, sanitized UI snapshot |
| R12 | Exact-revision full Windows/Ubuntu regression before release | Locked Rust build/tests/warnings, frontend check/build/tests, native/host gates separate |

## Limits that must stay visible

An MCP server cannot remove an app from ChatGPT's tool menu, observe a menu toggle as a session activation event, or dictate the client's exact refresh schedule. The trusted host supplies `openai/session`; that value is not cryptographic proof of an OpenAI origin. Real workspace files are shared, not an OS sandbox. A native notification is a hint only; some desktop implementations do not expose a portable notification-click callback. The tray "待审批聊天" menu and in-app inbox are the explicit local fallback; installed Windows/Linux click behavior is a separate acceptance item.

Strict refresh rotation can require relogin after a lost rotation response or simultaneous use. Keep no retry grace that silently makes a spent bearer token reusable. Old access-only tokens without a refresh family expire naturally; revoking refresh families does not retroactively convert those tokens into family-linked tokens.

# Exclusive Conversation and OAuth Refresh — Execution Plan

Status: APPROVED FOR IMPLEMENTATION; acceptance is not yet complete.
Date: 2026-09-13
Base: main @ a0551c447712104e2c2cb253d3d8a5a966518580
Base tree: 181e5353c38aa39fa72d8b96abedfe1f75e80982
Branch: feat/exclusive-conversation-refresh

## User authorization and scope

Latest instruction (verbatim):

> 按照推荐方案执行，先保存迭代执行方案为plan文件，然后开始循环迭代任务！

Implement the approved Single-Owner Exclusive Conversation Lease, event-driven desktop approval, and rotating OAuth refresh tokens. Save this plan before implementation. Keep PR #11 (public OAuth routing) separate; do not merge, modify deployment, or replace the existing v0.3.2 release as part of this feature branch.

## Baseline and constraints

Read AGENTS.md, the pinned mcp-probe-kit 4.0.1 skill, project-context documents, GitNexus skills, graph-insights/latest.md, and the actual Rust/Svelte code. The project-context index contains old scaffold-era descriptions; actual code and verified main-source tree take precedence.

Current behavior: exclusive mode defaults off and only revokes A when B is approved; B can still create a pending record. Grants are in memory with 90s pending, 30m idle and 8h absolute expiry. The workspace panel polls every 2.5s. OAuth supports authorization_code only, a maximum 8h JWT, mcp scope and PKCE S256. Remote history, task/session/CWD/Harness state is already keyed by the HMAC conversation binding; physical workspace files are shared.

The local source archive tree was recomputed and equals the live GitHub main tree. Native mcp-probe-kit/GitNexus plugins were not found in tool discovery. Pinned CLI installation was attempted and failed with registry DNS EAI_AGAIN; offline fallback reports ENOTCACHED. Preserve these failures. Manual source/call-chain and diff review is the declared fallback, NOT a successful graph/managed-plan validation. The container has no Rust toolchain or external DNS; compile/test in GitHub Actions if repository permissions allow, and use the existing verified offline JS compiler bundle for local frontend checks. Never turn an unavailable test into PASS.

## Product contract

1. Default to single-owner mode PER WORKSPACE/profile. Selecting an app in ChatGPT is not a server event: reservation begins on the first valid explicit request_chat_authorization, not tools/list or OAuth login.
2. States: FREE -> RESERVED(binding, request, 90s) -> ACTIVE(binding, scoped lease). Allocation and approval are atomic. Repeated owner requests are idempotent; they neither extend deadlines nor expand scopes.
3. While RESERVED/ACTIVE, every other binding is denied without a new pending record, owner fingerprint, modal, system notification, or owner replacement. Only trusted desktop controls release ownership. Do not claim to hide ChatGPT's app menu or all host-generated OAuth prompts.
4. Business refusal for an authenticated non-owner is a non-OAuth tool error EXCLUSIVE_CHAT_LOCKED, no WWW-Authenticate/login challenge, no retry/poll loop. Missing/invalid OAuth remains an authentication failure. Missing host metadata fails closed.
5. Desktop approval checks the fingerprint and allows a nonempty subset of requested scopes only. Approval is NEVER an MCP tool or an HTTP endpoint. Scope escalation requires a new local decision.
6. Lease expiry/revoke stops NEW admissions. It does not roll back completed effects. Existing tasks or interactive sessions must not overlap a successor in the same shared workspace: retain a DRAINING fence until admitted work is terminal, or explicitly cancel/resolve it from the desktop. Never auto-rerun interrupted work, guess that a process is dead, or silently give B ownership while A is still writing.
7. App restart clears grants. Refresh credentials may survive via authenticated encrypted application storage; that does not restore desktop approval. Recovery of ambiguous unfinished tasks must remain fail-closed.
8. OAuth refresh sessions bind client + issuer + subject + resource + approved OAuth scopes, NOT openai/session. Access JWT renewal preserves the existing conversation binding. Refresh does not renew a chat lease, acquire ownership, create pending grants, or emit approval notifications.
9. Settings: access_token_ttl_seconds=3600 (300..28800); refresh_session_ttl_seconds=2592000 (86400..7776000); chat_lease_ttl_seconds=86400 (3600..2592000); chat_idle_timeout_seconds=0 (off, otherwise 1800..86400); pending timeout stays 90s. Client timing of refresh is not server-controlled. Validate integer units/ranges at both UI and backend; migrate old configs safely.
10. Refresh rotation and reuse detection are mandatory. Store only keyed token digests and family metadata, never plaintext refresh tokens. Atomically persist rotation BEFORE returning credentials; fail closed on corrupt/missing keys, I/O failure, lock conflict, capacity or schema errors. Reuse revokes the affected family. Strict rotation can force relogin after a lost response or simultaneous refresh; document this instead of adding an unsafe grace bypass.
11. Preserve PKCE S256, exact redirect/resource/client checks, cache no-store and finite token lifetime. Parse OAuth scopes as a bounded set: allow mcp plus optional offline_access; reject unknown scopes; preserve the offline request through authorize GET/form/code exchange. Access JWT business scope stays mcp. Advertise refresh/offline capability only where implemented, not accidentally on legacy Actions.
12. Event-driven global approval host: foreground app modal, background/tray notification and pending indicator; countdown; navigation to the correct workspace; one notification per new candidate; no duplicate modal on retries. On event loss/WebView recreation obtain a bounded authoritative snapshot. OS notifications are best effort and never grant authority; Windows/Linux native validation is distinct from DOM tests.

## Architecture and impact review

Security-sensitive/high-risk change by manual assessment (graph execution unavailable): ChatAuthorizer::request/decide/permit is called through chat-domain intercept before every remote business dispatch and through privileged Tauri IPC. OAuthRuntime/token_exchange is used by both MCP and legacy Actions. JWT validation, listener construction and workspace configuration changes affect runtime restarts, shared secrets and existing HTTP tests. Global UI changes affect all routes and WebView recreation. Task admission/release affects async jobs and interactive sessions; keep lock ordering explicit and avoid calling executor locks while holding the authorizer lock.

Prefer small English-named modules: session_policy.rs, exclusive_lease.rs, oauth_refresh.rs, refresh_storage.rs, chat_events.rs, ChatAuthorizationHost.svelte, RemoteSessionSettings.svelte. Preserve existing public contracts where possible. No unrelated renames or edits to legacy old/ files. New files should remain under 500 lines each.

## Iteration schedule (12 main stages, up to 20 evidence-driven rounds)

| Round | Deliverable | Required evidence |
|---|---|---|
| 01 | Save plan/specs; pin baseline; failure-first exclusive tests | Recorded main/tree and pre-fix B-pending behavior; tooling failures |
| 02 | Typed owner state and defaults | FREE/RESERVED/ACTIVE lifecycle, config migration |
| 03 | Atomic first-request reservation | Concurrent A/B: exactly one candidate; retry idempotency |
| 04 | Silent non-owner gate | 100 B requests: zero additional pending records/events; no data leak |
| 05 | Lease, revoke, restart and draining semantics | Old work cannot coexist with successor; stale approval rejected |
| 06 | Bounded backend event delivery and snapshots | No lock-held UI callbacks; resync after lag/recreation |
| 07 | Global modal, notification/tray, countdown, navigation | Foreground/background and wrong-workspace flows; one prompt |
| 08 | Authorization-code/offline scope and refresh grant | Real HTTP code -> access+refresh -> new access+refresh |
| 09 | Durable atomic rotation/replay/revocation | Client/resource/issuer mismatch, replay, concurrency, I/O/key failure |
| 10 | Validated user-selectable TTL UI and lifecycle application | Bounds, units, old config defaults, no secret exposure |
| 11 | Combined lease/refresh/long-task regressions | Binding stable after renewal; non-owner still locked; task fence |
| 12 | Full Rust/frontend Windows+Ubuntu validation and review | Exact SHA evidence; separate public/real ChatGPT/native limits |
| 13–20 | Only newly reproduced failures or acceptance gaps | One hypothesis/change/test record per round, no rerun-until-green |

Rounds can share a commit, but each must have an evidence entry. A stage is not complete merely because code exists. Write iteration results in iterations.md, with command/run ID, revision, result and remaining blockers. Plan status remains partial until all applicable hard gates are satisfied.

## Test gates

- Unit/HTTP: simultaneous claims; 100 blocked requests; pending expiry; revoke/stale ID; scopes; isolation across profiles/identities; no host metadata; refreshed token same binding; no lock transfer from refresh; long-running work/draining.
- OAuth: auth code single-use; refresh issued only with supported offline consent; scope order/duplicates; unknown scopes; omitted refresh resource follows original binding only; wrong explicit resource/client/issuer; unsupported grant; token expiry; old token reuse; multi-thread rotation; persistent reopen; corrupted ciphertext/missing key; bounded records; shutdown during save; revocation behavior.
- UI: event deduplication; countdown expiry; focus/keyboard; no preapproved rights; stale async result after workspace switch; duplicate clicks; blocked-window silence; hidden/recreated WebView snapshot; settings validations and rollback.
- Full regression: existing cargo test, production warnings, Svelte/type/build and all frontend tests; real Windows and Ubuntu, no disabled security tests or sandbox. Installed desktop OS notification tests and real ChatGPT OAuth/host metadata are explicitly separate gates.
- No live production credentials in CI/logs/artifacts. Synthetic credentials are labelled. Do not use or retrieve user secrets for testing.

## Release and rollback

This task starts implementation on a feature branch; it does not authorize claiming a production deployment is complete. Open a Draft PR with evidence. Before any installer build, synchronize a new minor/prerelease version across the five existing version sources and verify internal/package versions. Do not overwrite v0.3.2. Do not build/publish macOS without an explicit request. Merge/public release only after applicable regression and acceptance gates, preserving PR #11 independently.

Rollback stops the candidate, revokes candidate grants/refresh families, and restores the prior binary and compatible configuration. Unknown refresh storage schemas must be preserved and rejected, not overwritten. Never migrate or delete workspace/history data just to clear authorization.

## Primary protocol references (checked 2026-09-13)

- https://www.rfc-editor.org/rfc/rfc6749.html — refresh grant, client binding, scope constraints and cache controls.
- https://www.rfc-editor.org/rfc/rfc9700.html — refresh rotation/replay detection and risk boundaries.
- https://developers.openai.com/apps-sdk/build/auth — OpenAI OAuth host/authentication contract.
- https://help.openai.com/en/articles/12584461 — refresh/offline configuration and real-host checks.
- https://v2.tauri.app/plugin/notification/ and https://v2.tauri.app/learn/system-tray/ — platform notification/tray limitations.

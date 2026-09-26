# ISSUE-013C / GitHub #42 — Runnable identity service

Parent #37 / Epic #32, PR #36. Base `5ad89711e67eeb907d496a32a1b54a3f82500c55`.
Status: LOCAL_RUNNABLE_IDENTITY_VERIFIED / BROWSER_BLOCKED / PUBLICATION_PENDING (round 4). This issue is not a real Agent or MCP execution implementation.

## Bounded increment and acceptance

- Add `coding-tools-gateway` executable; keep existing desktop and library contracts unchanged.
- Explicit commands: check-config, migrate, provision-owner, register-client, rotate-owner,
  serve. No HTTP admin/signup/direct code-issuance route and no automatic provisioning.
- Deny unknown config/secret fields. Immutable HTTPS origin, resource and owner/client
  binding come only from configuration, never forwarded headers or request input.
- No credentials in argv/environment defaults/errors. A bounded JSON secret packet is
  accepted from non-terminal stdin or an owner-only, regular, non-symlink file on Unix.
  Windows file ACL verification is not implemented: secret-file mode must reject on
  Windows, while explicit stdin mode remains supported. Do not claim mode bits prove ACLs.
- Unix protected files require matching effective UID, mode 0600/0400, one link, and
  non-writable-by-others containing directory. Files are opened with O_NOFOLLOW and
  O_NONBLOCK, metadata checked on the opened descriptor, and reads capped. Same-UID
  hostile processes / malicious ancestors are not a sandbox guarantee.
- Provisioning rejects duplicates; rotate requires a positive expected epoch. Serve
  rejects uninitialized schema, missing/mismatched owner/client/credentials, invalid key,
  or altered issuer/resource before binding. Repeated start does not reset DB state.
- Loopback-only bind (default 127.0.0.1:28880). HTTP/1 behind existing trusted TLS proxy.
  Bound connections, HTTP headers, body sizes, request rate, DB acquisition/statement/lock
  waits, and shutdown grace. No request/response/body/DSN logging. Global rate limiting is
  containment, not per-user anti-abuse; the ingress still requires audited source limits.
- Liveness is independent of Agent/DB; readiness checks expected provisioned identity
  and DB state. Health responses reveal only fixed statuses and reject foreign Host.
- Separate-process test: migrate -> provision -> start -> browser login -> consent ->
  code exchange -> stop/restart -> refresh without an Agent. Real Chromium on isolated
  HTTPS validates cookies/CSP/escaping/CSRF and negative flows. Do not bypass browser
  security except explicit trust of the ephemeral self-signed TEST certificate.
- Local tests, fmt/Clippy, regressions, pinned-source verification, and native CI are
  separate evidence gates. No remote CI or VPS claim without a successful actual run.

## Design and ownership

New `service/` modules wrap `IdentityStore`, `BrowserAuth` and `identity_routes`.
No existing OAuth transaction, browser flow or desktop interceptor is rewritten.
Trusted CLI operations are the only provisioning path. Client authentication mode
must match DB state, and serving secret packets cannot carry provisioning passwords.
The cloud process owns neither workspace paths nor an execution grant.

`migrate` applies additive embedded migrations and establishes immutable identity.
`serve` does not run migrations; it checks the migration ledger and bound store first.
This makes startup failure explicit and prevents an accidental binary rollback after
schema evolution. PostgreSQL connect/statement logging is disabled; errors are fixed
classes. An exclusive service supervisor and hardened TLS ingress remain deployment gates.

## Security review boundaries

Configuration is trusted local operator input, but it cannot select a public bind or
weaken Origin/Host checks. No HTTP lifecycle controls. Normal exit drains bounded
connections then closes the pool. Startup of a second instance cannot replace a
running listener. OAuth credentials remain in PostgreSQL as keyed digests.

The requested `/coding-tools` path preserves routing, NOT browser origin isolation.
Other applications on the same HTTPS origin share a trust boundary: HttpOnly/Path/CSRF
cannot defend against a compromised sibling same-origin application. A dedicated
origin, or an explicit audit of the entire shared origin, is a production prerequisite.
No existing site, WAF rule, DNS or certificate will be changed in this increment.
CentOS Stream 8 EOL and actual Docker Engine/port isolation remain #40 production gates.

## Pre-edit evidence

Restored exported checkpoint and invoked pinned resume_plan 4.0.1, which returned
mustContinue=true and implement. The actual base matches PR #36. GitNexus index:
9,057 nodes, 20,348 edges. Initial repository name mismatch corrected to the actual
registered `source.bundle`; original failed calls retained. FTS download unavailable;
query is degraded. Impact calls on identity_routes/register_client/provision_owner/
rotate_owner_password resolve but report no callers: manual source inspection finds
callers in HTTP/DB/browser tests. Treat auth boundary risk as HIGH, not proven LOW.
No existing target method is changed; new wrapper tests must exercise those contracts.
Generated index rule edits were captured then restored to the original baseline.

## Failure-first cases

Missing configuration/secret source; unknown args; overlarge/duplicate fields; public
bind; world-readable/symlink/FIFO/hardlink secrets; wrong identity key; duplicate owner
and client; stale rotation epoch; confidential/public mismatch; owner not provisioned;
DB lost while running; invalid Host; rate/concurrency/slow headers; wrong browser/CSRF;
login cookie rotation; deny; expired flow; concurrent duplicate consent; restart refresh.

## Rollback

Remove the new binary/adapter and use the previous library only in tests. No changes
to desktop or production state. Additive migration tables must not be dropped to
pretend a rollback succeeded. Never restore a DB backup as a means to undo revocations.

## Primary references inspected in round 4

- https://www.rfc-editor.org/info/rfc9700/ — exact callback matching and OAuth security.
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html —
  secure cookies, same-origin boundary, session rotation, no-store.
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- https://docs.rs/axum/0.8.4/axum/serve/index.html — server lifecycle (actual pinned source also inspected).

## Remaining gates

Standalone identity service is not a functional MCP Gateway. #38 grant projection,
#39/017-021 outbound channel and durable request journal, packaged native acceptance,
production ingress/host hardening and real ChatGPT acceptance are still required.

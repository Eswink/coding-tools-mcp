# Round 6 — Authenticated native Agent control channel

Date: 2026-09-22. Tracking: Issue #46 / ISSUE-017A, Epic #32, Draft PR #36.
Base: `ac816e0962a8211b071f63380777b7cef1124f87`.
Classification at local review: **CONTROL_CHANNEL_ENGINEERING_VERIFIED_LOCALLY / NOT_INTEGRATED / HOST_UNCONFIRMED**.
Native CI and exact-tree publication receipts are recorded on Issue #46; local tests below are not remote results.

## Delivered

A real opt-in Axum WebSocket control router, strict versioned Ed25519 proof contract, PostgreSQL session/generation/presence controller and device-signed projection relay. A real client initiates loopback TCP/WebSocket connections in tests using an enrolled device key; no mocked socket or unsigned fabricated authorization replaces these boundaries. Test keys, identities and sockets are isolated fixtures, not the user's machine or production credentials.

Authentication is scoped to the selected enrolled device, current registry epoch, configured issuer/resource, gateway boot and a fresh per-connection challenge. Reconnection replaces the generation only after successful proof; stale frames and delayed close cannot invalidate the replacement. Heartbeat cannot renew local grants. Submitted projection freshness is capped to the authenticated connection lease and revalidated under database locks. Disconnect, revocation, restore and activation preserve exclusive-owner/drain safety rather than transferring authority.

This is a **control-channel library**, not a shipped local Agent. The new router is NOT mounted into the existing identity-only `serve` command. The future integration must supply TLS/WSS, header deadlines, cancellation/supervision, protected local signing and final local execution admission. No cloud execution, tool request routing, mutation queue, request replay, remote local-approval endpoint or automatic desktop extraction was added.

## Actual local verification

| Test scope | Result |
|---|---|
| Full Rust suite with isolated real PostgreSQL 16 | 194 PASS, 0 failed, 0 ignored |
| Included new proof/shape contracts | 12 PASS |
| Included new PostgreSQL controller/race/restore contracts | 22 PASS |
| Included new TCP/WebSocket server/client contracts | 18 PASS |
| Independent identity binary/TCP/HTTP/database lifecycle | 30 PASS |
| Existing protocol laboratory | 32 PASS |
| Existing UI source contracts | 8 PASS |
| Existing Python fault proxy | 8 PASS |
| Existing deployment renderer | 13 PASS |
| Formatting and all-target Clippy | PASS |

The three new suites total 52 tests, included in 194, not additional to it. No full browser, WSS/TLS/certificate, real Windows workstation, VPS/WAF, installer or ChatGPT behavior was tested this round. The user explicitly deferred physical/Host testing; those gates are not blockers to coding and not silently marked PASS.

## Failures retained and targeted fixes

1. Initial compile exposed use of a SinkExt method without a production dependency. Replaced it with an explicit bounded Close-frame send; no unnecessary production futures dependency.
2. A new test initially expected WorkspaceOffline for an unreconciled existing owner. The prior contract correctly returned RecoveryRequired. Only the new expectation was corrected; existing security behavior was preserved.
3. A failure-first regression showed a valid signed snapshot could outlive the authenticated channel lease. Control now rejects that snapshot and advertises a bounded signing deadline. The unchanged regression passes.
4. The first complete regression failed because the new operational-session FK prevented an existing isolated grant-restore procedure. Unreleased migration 0004 now keeps presence independent of durable authority, without cascade; every operation still locks/validates projection/device/boot. A new restore test retains stale channel rows and proves reauthentication cannot revive authority without new signed local state. Existing projection restore assertions remain unchanged.
5. Clippy rejected a large test helper error type. The helper now boxes the client error. No warning suppression was added.

## Review / bounded guarantees

Lock order: enrolled device -> durable projection -> channel session. The controller serializes generation validation and projection calls, without holding locks across socket I/O. Other controller instances are excluded by the exact projection boot. A new crate-private read-only boot accessor prevents a concurrent activation from adopting another controller's boot. Existing projection/device/OAuth method bodies and all desktop code remain unchanged.

Session validation, snapshot deadlines and projection eligibility are admission prerequisites, NOT distributed exactly-once execution or local execution permits. The Agent must independently recheck its local grant/gate/recovery and mutation ledger in a later increment. Restore is supported only as an offline operator procedure followed by fresh controller activation; live database restore is unsupported.

Adapter bounds: 8 connections per router instance; 8 accepted upgrades/second; 16 KiB frame/message; 10-second proof deadline; 30-second presence; 1-hour maximum connection age; 8 control frames/second; 2-second writes; 3-second controller calls and periodic checks. Browser Origin, cookies, OAuth bearer headers, query strings, wrong Host/subprotocol and malformed control input are rejected. Proofs/payloads are not logged. Direct library callers must set their own deadlines and must not treat an error as permission to continue.

Fresh GitNexus analysis/impact was run, but FTS was unavailable and Rust caller coverage incomplete (known test calls missing). Path-qualified channel control/boot impacts are LOW in this index; manual callsite, lock-order, cancellation and source-diff review is the complementary evidence. Staged detect-changes reports MEDIUM risk / five inferred flows; several incorrectly connect old desktop functions to the test helper `sign`. Those name-resolution limits and the actual new-module callsites were reviewed, not treated as a zero-impact certificate. Automated review guidance is not an independent security audit.

## Scope / rollback / continuation

Changes are isolated to services/cloud-gateway, its new channel workflow and this spec. No existing src/, src-tauri/, root package/lock, AGENTS/CLAUDE rules, DNS, Nginx/WAF, VPS, installer, release or main changes. Dependency changes enable Axum's existing WS feature and pinned test-client dependencies; previous package versions remain locked.

Rollback stops all channel callers, uses the prior identity-only binary, and retains durable authority/tombstones. Do not remove migration history in place or restore old authorization to roll back code. The prior startup schema guard may deliberately reject a newer schema; deploy a forward-compatible rollback build or restore an isolated pre-channel test database without serving revoked authority.

Next increment: local Agent key/signing and WSS ingress integration, then bounded request multiplexing, execution tickets and durable no-replay reconciliation. Only after secure local dispatch is integrated should a separate real ChatGPT offline test be run. Keep Issue #46 open for these integration/release gates. **UNCONFIRMED_ON_REAL_HOST**.

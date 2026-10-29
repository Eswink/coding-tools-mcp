# ISSUE-017A — Authenticated outbound control channel

Tracking: GitHub #46; Epic #32 / PR #36; depends on enrollment #39 and projection #43.
Base: ac816e0962a8211b071f63380777b7cef1124f87. Date: 2026-09-22.
Status: DESIGN_FROZEN_FOR_BOUNDED_INCREMENT. Real workstation/VPS/ChatGPT tests deferred, not PASS.

## Deliverable and exclusions

Add a real Axum WebSocket control-channel library plus real loopback TCP/WebSocket and PostgreSQL tests. The local test client initiates the connection; it has no incoming listener. Reuse enrolled device keys and local signed snapshots. Existing identity-only service, desktop, root dependencies, DNS/WAF/ports remain unchanged. Installation, TLS ingress, the production device signer/UI, business request routing and mutation ledger remain later gates. There is no exec/file API, remote approval shortcut or queued offline work. This is transport control, NOT a complete deployed Gateway.

## Identity and handshake

A controller activates once per single active process; clones share one admission mutex and projection boot fence. Trusted code must have selected a device in the existing projection row before remote authentication. Activation resets cached eligibility, but preserves local owner and revoked-through epochs. Each upgrade gets a random attempt/challenge in memory (no preauth DB allocation), expires within 10 seconds and is consumed once. The device signs exact domain-separated bytes binding version, immutable issuer/resource/connector, device and registry epoch, gateway boot, attempt, challenge and expiry. Signature verification uses the locked enrolled key, never a payload key. Unknown/revoked/unselected devices, wrong socket nonce, stale boot and signature domains all fail without fencing an existing authenticated connection.

The adapter accepts only the exact versioned subprotocol and path. Reject Origin (this is a native agent-only endpoint), cookies, Authorization, query strings, malformed/duplicate critical headers and foreign Host. HTTPS/WSS termination is the responsibility of the future trusted ingress; tests deliberately use loopback WS only. No credentials in URL or HTTP headers; proof payloads and challenges travel only inside the protected channel, and must never be logged. Session debug output is redacted. A successful handshake does not grant tool permissions.

## Session, ordering and disconnect

One bounded PostgreSQL row per connector stores current boot, session ID, generation, registry epoch, connection lease, absolute lifetime, last sequence and connected flag. Every successful fresh proof creates a new session/generation and fences cached projection. Failed proofs cannot bump generation. Every authenticated control message is associated with its server-held session handle (not a caller-selected target). Sequence is exactly last+1. Only heartbeat extends presence; neither heartbeat nor WebSocket ping extends grant/snapshot expiry. Presence expires after 30 seconds, absolute connection lifetime is 1 hour, and expired sessions cannot heartbeat themselves back online.

All operations within one controller use a mutex across validation and the existing projection transaction, but never across network reads/writes. Across controllers the projection boot changes and invalidates old handles. SQL order is device -> projection row -> channel row, with bounded lock/statement waits and expiry recheck after waits. This avoids splitting generation checks from state mutation on parallel reconnection. Newer sessions survive delayed cleanup from old sockets. Disconnect and expiry make availability Offline/unreconciled but do NOT release the exclusive owner, acknowledge drain, renew grants or replay work.

## Projection and privacy

Authenticated actions are heartbeat, request projection challenge, and submit a device-signed snapshot. The snapshot remains signed by local authoritative state; the Gateway never signs cloud/model input as local approval. Reuse ProjectionStore validation for revision, original lease, scope, drain and tombstones. Assessment must validate conversation/scope before availability; foreign chats get the same non-disclosing result. Projection eligibility still is not a local execution permit. Uncertain mutations are NOT supported/replayed by this control channel.

## Resource limits and failures

At most 8 upgrade sessions/controller, 8 accepted upgrade attempts/second, 16 KiB frame/message, authentication 10 seconds, socket send 2 seconds, idle 30 seconds, periodic revocation/generation checks every 5 seconds, max 8 application frames/second and one control operation at a time. Reject binary/unknown/extra/duplicate-field messages. The WebSocket adapter bounds database/control calls (including mutex waits) to 3 seconds; direct library callers must supply their own deadline; failure closes the current socket and best-effort fences it. A database outage cannot become an authorization success. No payload logs and no secret-bearing WebSocket close reasons.

## Acceptance and source impact

Pure tests: exact proof binding/domain/time/JSON/size; seq and handle are not forgeable through JSON. PostgreSQL tests: failed auth no state change, selected-device restrictions, new-generation replace, stale-close race, revoke/epoch change, expired heartbeat, restart, signed reconciliation and authorization-before-presence. Actual TCP/WebSocket tests: handshake/heartbeat/snapshot/disconnect, header/Origin/cookie rejection, replay between connections, malformed/oversized frames and bounds. Run existing Rust/HTTP/protocol/deployment tests; portable Windows CI is not native workstation acceptance.

Only new channel module/migration and isolated tests/workflow plus gateway Cargo dependencies. Existing projection/device/OAuth method bodies are not modified; ProjectionStore gains one crate-private read-only boot accessor to avoid adopting another controller’s boot during concurrent activation. Fresh graph impact will be recorded before edits; incomplete Rust graph coverage is not proof of no callers. Full manual lock/cleanup/data-flow review is required. Rollback removes channel callers/export after stopping them; keep projection tombstones, do not restore old authority to roll back code.

## References checked 2026-09-22

- OWASP WebSocket Security: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- Axum pinned 0.8.4 source: WebSocketUpgrade bounds and masked client frames; dependency metadata.
- PostgreSQL row locking and consistent lock order: https://www.postgresql.org/docs/17/explicit-locking.html

No Codex code copied; local execution/PTY/policy/sandbox work remains after the secure routing foundation.


## Review amendments before publication

1. Snapshot `valid_until` must not exceed the authenticated session’s locked presence lease. The projection challenge includes `snapshot_valid_until` for this ceiling. The underlying projection transaction rechecks signed expiry after lock waits; a slow apply cannot commit after its channel lease expires. This deliberately requires periodic signed local-state refresh independently of heartbeats.
2. Presence is operational state, not a parent of durable authority. Migration 0004 deliberately omits an FK/cascade to `ctm_grant_projection` so isolated authority restore is not coupled to ephemeral channel rows. Every operation still requires the correct locked projection row, device binding and boot. Restore MUST stop callers and activate a fresh controller before serving; live restore is unsupported. A regression restores authority while retaining an old channel row and confirms reauthentication cannot restore eligibility.
3. Unreconciled existing owner reports `RecoveryRequired`, preserving the prior projection contract; it is not coerced to `WorkspaceOffline`. Foreign callers retain non-disclosing denials. Neither status is an OAuth challenge.
4. A successfully connected native test client is not a shipped local signer. The router is explicitly opt-in and is not mounted in the existing identity-only `serve` command. TLS ingress, request-header/slow-upgrade defenses, production client/supervision and secure device-key access are required before integrating this router into a public service. No unbounded direct-library call should be mounted without the adapter deadlines.

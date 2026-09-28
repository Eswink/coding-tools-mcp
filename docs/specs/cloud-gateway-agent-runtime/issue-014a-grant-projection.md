# ISSUE-014A — Durable local-authority projection

Tracking: GitHub #43, parent #38 / ISSUE-014, Epic #32, PR #36.
Base: `a06a48f24c2b45ba2bebb96a8f35f1542127f29a` (round4 local; preserves published `5ad8971`).
Status: DESIGN_FROZEN_FOR_BOUNDED_INCREMENT; physical/VPS/real-ChatGPT gates DEFERRED by user, not PASS.

## Contract and scope

FR-4 / agent-channel/2.1: add a PostgreSQL-backed projection of an enrolled device's local approval state. No HTTP approval route, transport, device signing service, local executor, existing desktop changes or rollout. The old grant-v1 primitive remains unchanged. New snapshots use a separate versioned domain and exact signed bytes; no cross-protocol signature reuse.

Cloud projection is only an eligibility filter. It is never a local execution permit. The future Agent must still compare its authoritative grant, scopes, epoch, atomic execution gate, request digest and request ledger at admission. OAuth alone never creates a grant.

## Data ownership and wire binding

A trusted operator binds exactly one registered device to each opaque connector. V1 refuses replacement; another device cannot claim it by presenting a valid enrollment. Issuer/resource come from immutable configured identity, never headers or claims. ConversationBinding is derived from a verified OAuth principal and trusted Host session (not model tool arguments) with a domain-separated keyed digest including connector/resource/subject/client. Raw session identifiers are not persisted or logged.

A device signs ProjectionClaims: version, issuer, resource, connector, device, device_epoch, gateway_boot, challenge, revision, authority_epoch, issued_at, valid_until, phase, execution, optional LocalLease and optional drained_grant. LocalLease contains only opaque grant ID, hashed conversation binding, scope list and original grant expiry. Snapshot freshness <=60 seconds; local grant expiry <=30 days. All arithmetic is checked. No source content, device path, command/output, raw OAuth/session or challenge plaintext is stored.

Persist one bounded row per connector, including last accepted revision/digest, revoked-through authority epoch, selected device, minimal typed state and a hashed challenge. No append-only unbounded snapshot history or pending notification/offline execution queue.

## Fencing and reconciliation

`ProjectionStore::activate` is a lifecycle operation, NOT a per-request constructor. It installs a fresh random gateway boot ID and sets reconciled=false. Clones share that boot. A later activation invalidates earlier handles in SQL; v1 is explicitly single-active-controller, not active-active HA. Existing cached grant state is retained only for comparing ownership/drain rules and non-disclosing denials.

Authenticated Agent channel code (future issue) may request a fresh single-use challenge. Challenging marks the projection unreconciled. Apply holds registry and connector locks, verifies the exact device key, boot, hash, expiry and signature, then requires a strictly newer revision. Exact duplicate payload after successful commit is idempotent only while still fresh/reconciled and never renews TTL. Conflicting/reordered revisions fail. A challenge supersedes prior in-flight responses. Time is checked after lock waits and again immediately before the final update.

Device revocation is checked transactionally on every update/assessment. Lock order: device FOR SHARE, then connector FOR UPDATE/SHARE; activate locks only connector. Bind locks device then connector. Use bounded statement/lock waits. No cloud signature can synthesize a device snapshot.

## Owner and drain state machine

Free -> Active requires a new local authority epoch above the durable revoked-through floor. Same Active lease may change execution Online/Offline, but cannot change owner, grant ID, scopes or grant expiry. Those changes need a new grant through drain. Active -> Draining retains exact prior lease. Draining -> Free requires the device-signed drained_grant equal to the prior grant ID; Free atomically raises the epoch floor. Active -> Free and Active/Draining -> another owner are forbidden. Expiry, Offline and cloud restart never imply drain or transfer. RecoveryRequired retains the previous lease and can exit only through explicit Draining/Free evidence, or remain blocked. All new/unknown state is fail-closed.

On a cloud restore, restart the controller and reconcile against fresh device state. A captured pre-restore signed snapshot cannot match the new boot/challenge. This is NOT a claim of magic monotonic storage across simultaneous rollback of both cloud and local state; recovery then requires a separate trusted epoch anchor or re-enrollment/reapproval. Device-registry rollback is also a separate recovery concern. Live DB rewind without stopping the controller is unsupported.

## Non-disclosure and decision order

Assessment takes an internal ConversationBinding and required scope. Check selected active registry device, owner equality, local grant expiry and scopes before exposing any availability category. A foreign or absent owner receives the same AuthorizationUnavailable value for every phase/presence/boot. An entitled owner can receive ScopeDenied, RecoveryRequired, WorkspaceOffline, or Eligible. Eligible still means no execution permit. No phase/owner/path/task is serialized as a foreign error. No mutation happens on denied assessment.

## Validation / failure-first matrix

Pure: signature/domain/duplicate JSON/bounds/version, strict resource/device/epoch/boot, fixed field types, no signed payload Debug leak, default-deny state transitions, no direct transfer, immutable grant, scopes and overflow.
PostgreSQL: install/bind, concurrent bind/apply, duplicate/reordered proofs, revoke race, expiry after lock wait, cancel/rollback, explicit drain -> new owner, restart fences, exact old snapshot/DB restoration -> challenge rejection, no pending/data leakage. Test pools are loopback disposable `coding_tools_identity_test` schemas only.
Regression: all current identity/browser/service tests, 30 separate-process HTTP cases, existing protocol/UI/fault-proxy/deploy-render tests, fmt and all-target Clippy. Native CI is distinct from installed/physical Host testing. Never rewrite historical blocked browser tests to PASS.

## Impact and rollback

Existing verify_grant/revoke_device graph impacts reported LOW/0 callers but known test callsites exist: graph is incomplete, so source inspection is authoritative. New ProjectionStore is not yet indexed, impact UNKNOWN for a new symbol. Existing methods are not modified; add a module export and additive migration only. Existing desktop/interceptor remains untouched. Remove new module/export and stop new callers to rollback; retain additive schema/tombstone floors, do not restore grants from a backup as a rollback shortcut. No change to production DNS/Nginx/WAF/ports.

## Primary references (read 2026-09-21)

- OWASP Authorization Cheat Sheet: deny-by-default, distinguish authentication/authorization, validate every request: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- PostgreSQL explicit row locking: https://www.postgresql.org/docs/17/explicit-locking.html
- Project source: services/cloud-gateway/src/device.rs, grant.rs, store.rs; current published commit 5ad8971. No direct Codex code copied in this increment.

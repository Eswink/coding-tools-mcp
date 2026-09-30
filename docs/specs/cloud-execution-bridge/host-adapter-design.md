# Host-owned Agent adapter (FR-4–FR-7)

The production host adapter is added to the existing authenticated Agent protocol.
Recovery-only CLI behavior remains supported, never relabelled as execution-capable.

## Trust and linearization

A `LocalHost` supplies a serialize-only snapshot and an opaque permit. Network
data cannot be deserialized into a local permit. Projection signatures are made
only from snapshots returned by this locally supplied host. Before executing,
the adapter rechecks the exact host epoch, authority revision, execution
generation, conversation, grant, scope, and deadline against the projected view.

A signature-verified local append-only journal commits an operation identity
before host admission/execution. Duplicate IDs, corrupt or truncated records,
uncertain operations, and capacity exhaustion fail closed. Projection revisions
reserve durable high-water blocks so a restart never reuses a signed revision.
No command text, path, result text, OAuth credential, or private key is persisted
in this journal. Complete multi-authority rollback remains outside its guarantee.

A live connection is not local authority. Heartbeat processing is independent of
tool execution. Disconnect cancels bounded workers without replay; unfinished
claims remain durable and require reconciliation. Revoked output is not released.

## Native attachment

The native desktop adapter must use existing `ChatAuthorizer`, execution gates,
native approval inbox, and the existing tool dispatcher. Cloud identity is kept
separate from local OAuth. Native integration and Windows/Linux end-to-end tests
remain mandatory; a test implementation of `LocalHost` is not their substitute.

## Scope retained

Issue81, Windows sandbox, Hooks, managed worktrees, snapshot rollback, deployment
preflight, and whole-product package gates are still required. No desktop-only
prerelease or main/production deployment is authorized by this increment.

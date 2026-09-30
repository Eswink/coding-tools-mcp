# Native work drainage — Issue #81 / FR-3, FR-5, FR-6, FR-7

## Contract

The managed Agent's journal lock outlives all actual native work, not merely its
WebSocket or the futures awaiting blocking callbacks. One process-local WorkDrain
belongs to one NativeLiveHost lifetime. It has at most 512 registered nodes. This
is resource accounting, never a grant, durable replay ledger or sandbox policy.

Register root callbacks before returning a future. Root start and permanent seal
share the same mutex. A queued root that loses to seal is removed without calling
its factory. A running parent may reserve descendants during drain, but a cloned
scope whose parent has retired cannot create new work. Cancelled waiters neither
abort workers nor remove their registrations. Dropping a running registration
without explicit completion irreversibly quarantines the drain. There is no
reset, forget, forced-success or automatic restart operation.

Every native blocking callback owns its registration on the actual blocking
thread. Execution snapshots retain an optional child scope. Asynchronous command
workers must reserve before publication and hold it until their callback returns;
child processes have separate registrations lasting through direct-child wait,
process-group completion and joined input/output tasks. Session join collectors
retain handles in the session until they have actually joined, so cancellation of
one collector cannot detach a live I/O task from a later collector.

Synchronous Git/Harness helpers inherit only a thread-confined scope from native
execution. The existing process manager receives an explicit opt-in requirement
for process-group completion; uncertain termination cannot produce a native drain
receipt. No saved PID is used for repeated kill operations. Observation failures
or identifier reuse retain uncertainty rather than acting on another process.

## Verification

Deterministic tests cover register/seal/start ordering, stale parent scope,
cancelled waiters, blocking callbacks, panic, capacity, many waiters and missing
completion. Native tests use real pipes and real child processes plus the actual
ChatAuthorizer/NativeLiveHost. WSS/PostgreSQL tests remain separate from physical
workstation and UI-click acceptance. Counts are taken only from completed logs.

## Risk and rollback

Existing context construction and Git helpers have CRITICAL inferred graph
impact; execution dispatch is HIGH. FTS/trait resolution limitations are retained.
Only optional process-local accounting is added; native grant checks, scope checks,
mandatory Linux sandboxing and durable no-replay state are not weakened. Existing
local-only paths default to no accounting. Windows cloud process execution remains
rejected until the Windows sandbox gate is implemented and validated.

Rollback keeps all authority, projection and execution journals. A failed drain
must not be bypassed by replacing the manager/host while the prior Agent holds its
lock. This increment does not complete application configuration/import/UI startup,
the full public catalog, Windows sandbox, Hooks, worktrees, snapshots, deployment
or full-package release requirements.

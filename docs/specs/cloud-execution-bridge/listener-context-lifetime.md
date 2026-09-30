# Issue81 — exact native listener context lifetime

Parent Epic #32 / Issue #81. This is an application-integration prerequisite, not the full bridge or a release. Existing saved drain work at local commit 229a1a41ab2215ede18588d13cc2110c2c5b3bb6 remains required; this increment is additive to the unchanged listener/supervisor in its published baseline 2c5d133eaa75d7fc084b8122350d7768ce5b2382.

## Requirements

1. A future managed Agent obtains the actual listener-owned ToolContext Arc, with the same WorkspaceExecutionGate, session store and durable task store. No second context or gate may be constructed for that Agent.
2. Context lifetime is not local execution authority. Existing native grant, scope, authority epoch, gate, journal and platform-isolation checks remain mandatory. Cloud input cannot deserialize or construct a lease.
3. Listener registration and permanent lease closure share one mutex. If close wins, the startup callback is not invoked. If registration wins, its work remains subject to the separately owned Agent drain lifecycle.
4. Supervisor begin_stop seals the lease before signalling HTTP shutdown. Task completion, error, abort and never-polled task cancellation also close it through a guard created before spawning. Keeping an Arc does not keep the lease open.
5. A cloned observer is non-owning. Dropping or cancelling an observer cannot close the service or consume the close signal. Late subscribers observe permanent closure. Each listener gets a new opaque generation.
6. Existing local accepted-job drain, port-bind ordering, origin/OAuth behaviour, argument policy and sandbox checks are unchanged. A closed lease does not claim the Agent/processes have drained.
7. Native Windows/Ubuntu compile/full regressions and actual bound-listener tests are required. Zero tests, skipped sandbox probes, source-only graphs and historical counts do not establish acceptance.

## Design and threat boundary

ListenerContextLease holds the exact context, an unguessable native generation, a close-state mutex and watch notification. Its constructor/close/owner guard are crate-private, with no remote endpoint or serialization. with_live is a short native registration callback only; it must not await, reenter the lease or perform blocking I/O. Panic seals the state, wakes observers and resumes unwinding. Callback results never constitute a local approval or execution permit.

Keep compatibility wrappers for all existing listener callers. New supervisor context access is available only for an actually live MCP entry; Actions has no MCP lease. The listener owns the guard, not consumers. Agent-specific cancellation, bounded stop, retained execution journal lock and unresolved-work fencing remain owned by the managed Agent implementation, not by this type.

## Pre-edit evidence and risk

Pinned GitNexus 1.6.9 run 36678640048, source 595a12ad6a29542dd89d180ffc8ffb81ea6f0ddb, examines unchanged existing production symbols against baseline 2c5d133. spawn_listener_with_binding: CRITICAL, 40 upstream nodes, 2 direct callers, 4 inferred flows. Existing public wrapper: HIGH, 37 upstream nodes, 6 direct callers, 3 flows. Supervisor start/begin_stop/finish_stop: LOW, 5 upstream nodes each; is_running: LOW/0 (not proof of no callers). Native Rust trait/name coverage remains limited.

Manual boundary review: preserve session-policy/config/storage/credentials/OAuth/bind ordering and existing test assertions; keep accepted local task semantics; seal new lease before stop; ensure guard exists before task first poll; do not mint local approval from callback results. Full original auth/origin/refresh/recovery and Ubuntu kernel-isolation tests remain hard gates. CRITICAL is retained, not re-labelled as safe or independent certification.

## Verification plan

- Fourteen deterministic lease unit tests: exact Arc/gate reuse, pause visibility, no local gate mutation on close, linearization, stale lease, cancelled waiters, late subscribers, task cancellation/panic and bounded non-disclosing Debug.
- Real loopback listener tests retain owned sockets, verify discovery and existing pause state, close observers on graceful stop/abort, and prove no closed lease survives listener completion.
- Supervisor tests prove begin_stop seals before network drain, absent/stopping/Actions entries cannot be acquired, and no accidental shutdown merely from observation.
- The candidate is canonicalized only for new source files, compared on both native platforms, then exported as exact content-addressed source. Transient CI assembly files are excluded from the clean product commit.

## Remaining engineering and rollback

Application configuration import and exclusive initialization, native managed-Agent start/stop/exit wiring, GUI controls, real cloud tool catalog, full WSS/PostgreSQL/native/UI integration, Windows sandbox, Hooks, worktrees, snapshots, deployment preparation and complete-package gates remain required. Physical workstation/VPS/ChatGPT observations remain deferred, not PASS. No new prerelease is authorized by this increment.

Rollback is an ordinary code revert retaining original APIs and all durable authority/task/projection/journal/migration state. Do not force-push shared history or delete unresolved work to make a workspace appear free.

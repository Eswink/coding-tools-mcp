# #81 — managed outbound Agent lifecycle

Status: implemented component; Linux validation recorded externally with exact
source hashes. Full Epic #32 and #81 are NOT completed by this increment.

## Recovery and scope

The recovery base is local commit
`5fb868d22cdb6f3a2f6abd12870f9700dbfb5e02`, plus the 56-file verified
`native-cloud-end-to-end.zip` source snapshot. Previously described later
application lifecycle/UI changes were not present in those recoverable bytes.
This implementation is new, not a claim that missing code was recovered.

Changes are in the database-free cloud Agent, managed-host integration tests,
and a read-only CI gate. No application startup or UI adapter is claimed here.

## Linearization and ownership

1. Registration reserves one workspace/generation under the lifecycle mutex.
2. The spawned task must acquire that SAME mutex and transition Queued -> Running
   before invoking its factory. Stop/shutdown winning this race yields NotStarted
   and drops the uncalled factory, including zeroized private startup input.
3. Running is the start-admission linearization point. A close after it waits for
   the factory and its work; it does not assert the factory never ran.
4. Stop signals cooperative cancellation. Expiry or cancellation of the wait
   future never aborts the worker, clears occupancy, reopens a manager, or grants
   a successor execution authority. Shutdown has one total timeout budget.
5. Only explicit Drained/FailedDrained releases the matching workspace slot.
   Panic, runtime cancellation after start, or explicit unknown termination
   quarantines it. No forget/retry-unconfirmed API exists.
6. Manager identity, workspace identity and monotonically checked generation
   fence old stop/completion events. Application shutdown is irreversible for
   that manager, including late queued registration and initialization.

These are process-local lifecycle guarantees. They do not replace durable
request tombstones, native grant epochs, recovery fences, or OS sandboxing.
Use one application-owned manager. Do not create another manager to bypass an
uncertain slot; a process crash requires the existing durable recovery workflow.

## Actual HostAgent startup and drain

AgentStart takes locally supplied, bounded config/key bytes and an absolute
journal filename. The startup key is zeroized on rejection, queued cancellation,
and after signer construction. No tool parameter can select this configuration.
Journal initialization remains explicit and exclusive; missing/corrupt existing
state never triggers initialization or overwrite.

The actual HostAgent remains alive after its WSS loop returns while the host's
`wait_for_drain` executes. Its OS journal lock is retained throughout. The trait
has no default implementation and no "abort means drained" fallback. Native
adapters must track detached/blocking work and subprocess cleanup even when the
corresponding async future is dropped. Successful connection shutdown alone is
NOT a drain receipt. On unknown drain, the slot remains quarantined.

## Executed tests and exact boundaries

- Shared Agent: 33 restored cases plus 25 lifecycle and 8 managed-start cases.
- Lifecycle races use ordered current-thread execution/oneshot signals and a
  128-iteration concurrent shutdown/start stress test; repeats are not extra cases.
- Removing the start-denial branch in an isolated mutation copy causes the exact
  close-before-first-poll test to fail (Drained vs NotStarted). This is a mutation
  sensitivity test, NOT a claim to have reproduced absent historical source.
- Five added real PostgreSQL/TLS/WSS cases use the real HostAgent with the clearly
  labelled FileHost fixture. They exercise real reads, persistent no-replay across
  restart, stale stop handles, cooperative stop, held journal lock during drain,
  unknown termination, foreign denial and close-before-initialization.
- These are NOT native desktop approval clicks, Windows execution, OS isolation,
  deployment, or the user's ChatGPT tests. The existing native source snapshot
  is preserved but is not newly compiled by this Linux component suite.

Retained failures: restored HostAgent's needless usize cast failed strict Clippy;
removed without disabling lint. A full gateway test failed before its target
assertion because its one-second grant expired during setup. The fixture now
admits once with a five-second margin and observes the real database deadline
before retaining the original post-expiry/renewal/drain assertions. No production
clock, expiry rule, or authorization check was changed.

## Next native integration requirements (not waived)

Wire a single application-owned lifecycle to the existing listener ToolContext,
not a freshly created alternate authorizer. Implement an exact native drain
receipt including pending blocking tasks. Bind locally imported connection
config/key material to the selected workspace and protect partial initialization.
Then connect native start/stop, listener closure, app exit and UI controls, and
verify the full published tool catalog, scopes, deadlines and cancellation.

Windows sandbox, Hooks, worktrees, snapshot rollback, deployment preparation and
complete-package gates remain required. No desktop-only release substitutes for
this plan. No main/release/production infrastructure or credentials are changed.

## Rollback

Use an ordinary revert of the actual future integration commit, not force push.
Preserve all request/grant/projection journals, tombstones, migrations and unknown
outcomes. Do not restore an old authorization database or delete recovery state
to make a workspace appear free. This additive local candidate is not deployed.

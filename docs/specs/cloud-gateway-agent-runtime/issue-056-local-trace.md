# ISSUE-056: local trace and read-only recovery projection

## Boundary and implementation plan

Continue #56 on Draft PR #36 after the bounded non-PTY process runtime #55.
Base: 4196b702b9c13debfd73fabe54c571c99bb14cd7. Add an opt-in adapter around
`ToolRegistry::invoke`, not another executor or admission provider. Existing
registry, policy, process and desktop method bodies remain unchanged. No new
dependency, transport endpoint, disk log or cloud upload.

A `TraceJournal` is bound to one locally supplied `LocalAdmission` conversation,
workspace and generation. Read and append check that exact scope and the caller's
local time/expiry before inspecting state. This is not a live revocation oracle:
callers must obtain current local admission from the authority provider. No public
admission constructor is introduced; trace cannot renew expiry. First poll, not
future allocation, starts observation.

## Data and failure contract

- Fixed-capacity ring: at most 4096 events and 64 in-flight invocations, with
  caller-selected smaller nonzero limits. Private scope strings are bounded.
- Exported events contain journal-local numeric IDs and typed phases only. No
  request IDs, tool names, inputs, outputs, paths, environment, credentials or
  arbitrary error messages, even as unkeyed hashes. Private scope is not Debugged.
- Adapter entry is not proof of executor dispatch. A returned error is not proof
  of non-execution or absent side effects. ReturnedOk is a return observation,
  not a durable or externally verified side-effect claim.
- Await exactly one existing registry call. Preserve its original success/error
  even if terminal diagnostics fail. Never retry. A private RAII guard records
  unknown on cancellation/unwind after entry. Never-polled futures do neither.
- Reserve terminal sequence capacity before admitting work. Overflow/poison fails
  closed for new calls and reads. No callback or await occurs under the lock.
- Count ring eviction. Active numeric IDs survive start-event eviction. Recovery
  projection is pure, read-only, non-authoritative and explicitly non-durable.
  Gaps, active work and unknown/errors require reconciliation, never auto replay.
- Process loss is not reconstructable from an in-memory journal. Existing durable
  request-ledger reconciliation remains mandatory. No production trace endpoint.

## Validation and impact

Before implementation, isolated run 35768151129 executed probe 4.0.1 resume_plan
(no recoverable Plan), GitNexus 1.6.9 query/context/impact and narrow diff at e789dd2.
`register` had six test callers, MEDIUM risk, zero flows. `invoke` had name
collisions; the registry candidate had one caller/LOW estimated risk, aggregate
UNKNOWN. No existing registry symbol body is edited. The helper failed its final
clean-tree check after tooling-generated files; do not call the whole job passing.

Seventeen new tests cover payload/identity/error/Debug redaction, original output
and error preservation, authorization/generation/expiry, cancellation/unwind,
never-polled futures, ring gaps, active capacity, sequence reservation, poisoning,
concurrency and a callback that poisons diagnostics after execution. Test modules
are split below the source-length limit. Exact native Windows/Ubuntu fmt, Clippy,
tests and check must pass before the issue/manifest is marked verified.

The local pinned Rust 1.98.1 toolchain was recovered with verified SHA-256, but the
execution environment subsequently timed out before a Rust result was available.
No local Rust PASS is claimed. Validation proceeds through native repository CI;
keep failed runs and formatting corrections in the evidence trail.

## Rollback and release

Remove the opt-in trace module and its reexports to roll back. No durable state,
authority, routing or production configuration changes. This library view contract
is not an installed desktop recovery screen, persistent audit trail, independent
security review or real ChatGPT acceptance. Existing release gates remain.

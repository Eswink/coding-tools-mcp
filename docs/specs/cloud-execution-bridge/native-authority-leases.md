# Native owner authority and restore quiescence (FR-3/FR-4/FR-6)

## Required boundaries

- A managed worktree becomes executable only after explicit native owner confirmation registers a separate workspace profile at its verified root. Never mutate the source profile root, inherit authorization/configuration/journals, auto-enroll a device or auto-start a listener. Shared Git metadata outside the selected root remains outside ordinary subprocess sandbox authority; a validated broker may perform its existing narrow metadata operations.
- Registration pins the managed target against remote removal. A missing/corrupt registration or changed mapping fails closed. The original cloud connection and durable no-replay ledger are unchanged.
- Hook preview creates a short-lived pending object for the exact canonical manifest and content digests on the current listener context. A second native command must show an actual owner confirmation dialog before consuming it into that same registry. Model/cloud arguments cannot approve; listener restart expires the context and registry. Hooks retain ordinary native authority, deadline/cancellation, ExecPolicy and mandatory sandbox boundaries.
- Snapshot restore consumes a server-retained plan, exact approval digest and validated managed target after actual native owner confirmation. It requires all registered target profiles' services stopped, cloud lifetimes proven drained, persistent task admissions fenced and actual native root work absent. A restore lease does not assert external-editor quiescence; conflict checks, rooted operations and retained backups remain mandatory.

## Actual root-work accounting

One registry per canonical root is shared by every ToolContext. The outer platform dispatcher starts and owns a root guard through actual synchronous work, independently of local/cloud authority. MCP registers before queuing spawn_blocking so cancellation of the waiter cannot make queued/running work disappear. Native drain adapters carry both the existing cloud scope and this root scope through detached jobs, Git, subprocesses and pipe/tree monitors. Existing underlying WorkDrain semantics are preserved: dropped running work is uncertain; completed callbacks alone retire registrations; process/tree/pipes must actually finish.

The registry holds an exclusive native AuthDocument namespace outside the workspace. Before work starts it persists busy state, and only known zero outstanding work clears it. Panic, lost native completion, malformed state or a busy/restore record after restart fails closed. Missing records in an existing namespace are never recreated. Capacity is bounded; this is not remote permission or a grant.

Restore admission seals only a clean zero-work tracker and persists restore state. It holds the existing native lifecycle transaction and task-admission guards throughout filesystem work. A lease callback revalidates exact plan/root/worktree binding before each destructive move. An engine-confirmed clean outcome permits a fresh work generation; uncertainty preserves the durable restore fence. There is no automatic replay, unsafe reset or unsandboxed fallback.

## Verification

Required tests cover synchronous file operations, prequeued and cancelled workers, detached native processes and pipes, scope propagation, uncertain guard drop, cross-context same-root sharing, exclusive ownership, busy-marker restart, restore/new-admission races, native plan digest substitution, listener replacement during hook approval, script replacement, and selected-root actual read/write/exec without parent-root authority. Existing authorization/cloud/no-replay suites remain mandatory. Dot kernel sandbox limits and Windows filesystem/sandbox gates must remain explicit until native CI proves them.

## Review scope

Shared ToolContext construction and native_drain adapters are high/critical blast-radius changes. GitNexus queries/context/impacts and exact-byte comparison precede edits. The canonical graph's missing-ID issue is documented; identical-source hook index receipts supply working symbol impacts. Route/alias omissions are supplemented by manual CRITICAL review, never treated as zero-risk.

# ISSUE-003 — Decouple connector control plane from workspace execution lifecycle

Status: IMPLEMENTATION IN PROGRESS  
Parent: [plan.md](plan.md)  
Design: [issue-002-workspace-availability-contract.md](issue-002-workspace-availability-contract.md)  
Round: 3 / 5  
Real ChatGPT host acceptance: DEFERRED TO ROUND 5

## Objective

Implement the provisional Level A architecture without changing OAuth identity, refresh-token policy, chat ownership, hard-stop behavior, or tunnel lifecycle.

A running MCP connector may be placed into an execution-offline state:

```text
Connector listener     Running
OAuth control plane    Running
Tunnel                 Running
Workspace execution    Offline
```

New admitted remote business work must fail with a typed non-OAuth `WORKSPACE_OFFLINE` result.

## Mandatory impact evidence

The repository-required GitNexus impact gate was executed in GitHub Actions because the current ChatGPT environment does not expose the native GitNexus/mcp-probe tool channel.

Run `35503567408`:

- `RuntimeSupervisor::start`: LOW, lower-bound
- `RuntimeSupervisor::status`: LOW, lower-bound
- `ToolContext::background_snapshot`: **HIGH**, lower-bound
- `chat_domain::intercept`: LOW, exact
- `RuntimeStatusDto`: LOW, exact

Run `35504005051` added the MCP listener public entrypoint:

- `spawn_listener_with_origin`: **CRITICAL**, exact
- impacted symbols: 31
- direct dependants: 11
- affected processes: 7
- affected modules: 4

The CRITICAL result was not ignored. The first implementation changed the existing listener return type and immediately produced broad compile breakage. The implementation was redesigned so the existing public pair-return `spawn_listener_with_origin` contract is preserved. A new crate-local gate-aware entrypoint is used only by the runtime supervisor and the new targeted regression.

## Implementation increments

### 3.1 Atomic execution gate

Added `src-tauri/src/runtime/execution_gate.rs`:

- `Online | Offline`
- mutex-protected `in_flight`
- `try_admit` linearization point
- RAII `ExecutionPermit`
- pause/resume snapshots
- concurrency unit tests

Invariant:

> Work admitted before pause commits may finish. Once pause returns, later gated admissions fail.

### 3.2 ToolContext propagation

`ToolContext` owns one shared execution gate per MCP listener generation. `background_snapshot` and chat-scoped contexts share the same Arc.

This touches the HIGH-risk snapshot path and therefore remains covered by full Rust regression and change-impact review.

### 3.3 Authorization-before-availability dispatch

Remote business dispatch remains:

```text
OAuth
 -> chat identity / owner / scope admission
 -> execution gate
 -> chat-scoped domain
 -> tool dispatch
```

Foreign/non-owner conversations therefore continue to receive authorization semantics before availability state.

Offline drain-control allowlist:

- `get_exec_task`
- `list_exec_tasks`
- `read_output`
- `cancel_exec_task`
- `kill_session`
- `write_stdin`

All other exposed remote business tools require Online.

### 3.4 Runtime lifecycle

`RuntimeEntry` owns:

- listener generation id
- optional MCP execution gate

New supervisor operations:

- `pause_mcp_execution(profile, expected_generation)`
- `resume_mcp_execution(profile, expected_generation)`

Stale generation requests fail rather than modifying a replacement listener.

Hard `stop_runtime` remains unchanged.

### 3.5 IPC and status

Added local Tauri IPC:

- `pause_mcp_execution`
- `resume_mcp_execution`

`RuntimeStatusDto` adds optional:

- `executionState`
- `runtimeGeneration`

Resume also refuses to clear or bypass an existing chat recovery fence.

### 3.6 HTTP regression

Added synthetic HTTP regression that proves:

- owner A business call succeeds Online;
- pause leaves HTTP/OAuth transport reachable;
- owner A business call returns `WORKSPACE_OFFLINE`, category `availability`;
- no `WWW-Authenticate` challenge is added;
- A's authorization id/status is unchanged;
- foreign B still receives `EXCLUSIVE_CHAT_LOCKED` and no grant metadata;
- resume restores A business dispatch.

This is synthetic HTTP evidence, not real ChatGPT-host acceptance.

## Failure-first iteration history

Early Round 3 validation intentionally remains recorded:

- public listener tuple widened from 2 to 3 elements;
- existing OAuth/HTTP fixtures failed compilation;
- GitNexus independently classified the listener entrypoint CRITICAL;
- implementation was narrowed to preserve the existing public API.

Later compile errors exposed the internal gate-aware function not being re-exported crate-wide and one stale triple destructure in the noauth fixture. Both were fixed without changing the preserved public contract.

## Remaining work in this issue

- obtain a green full source regression for the narrowed backend candidate;
- rerun clean GitNexus detect-changes without analyze-generated AGENTS/CLAUDE noise;
- add focused runtime generation/tunnel-invariance regressions;
- add a local UI surface for pause/resume after the Svelte impact-analysis limitation is documented/resolved;
- review exact diff;
- keep PR draft until Round 3 gates converge.

## Non-claims

This issue does not claim:

- that ChatGPT will not show reconnect UI;
- that desktop-process exit is survivable;
- that machine sleep/power-off is survivable;
- that real-host OAuth refresh while offline has been validated.

Those remain Round 5 acceptance boundaries.

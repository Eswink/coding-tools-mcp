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

Run `35504005051` first surfaced the listener entrypoint as **CRITICAL**. The CRITICAL result was not ignored: widening the existing listener tuple immediately broke OAuth/HTTP fixtures, so the implementation was narrowed.

Final focused impact run `35506436646` on the narrowed design reports:

- `spawn_listener_with_origin_and_execution_gate`: **CRITICAL**, exact — 33 impacted symbols, 4 direct dependants, 8 affected processes, 5 modules.
- legacy test-only `spawn_listener_with_origin`: **HIGH**, exact — 20 impacted symbols, 8 direct dependants, 4 affected processes, 3 modules.
- `RuntimeSupervisor::start`: LOW, lower-bound.
- `RuntimeSupervisor::status`: MEDIUM, lower-bound.
- `ToolContext::background_snapshot`: **HIGH**, lower-bound.
- `chat_domain::intercept`: LOW, exact.
- `RuntimeStatusDto`: LOW, exact.

The gate-aware listener therefore remains a critical change even after API narrowing. Review and validation stay mandatory; the impact classification is not downgraded because the source compiles.

GitNexus 1.6.12 cannot currently index the targeted Svelte page/component symbols. Run `35504168445` failed exact lookup for `applyMcpRuntime`, and run `35504745045` records both Svelte `Props` probes with exit code 1. This tooling limitation is preserved as evidence rather than relabeled PASS; Svelte edits are covered by source review, `svelte-check`, production build, and a focused Node UI contract regression.

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

### 3.6 UI state separation

The workspace page now renders an explicit MCP execution-availability panel:

- Connector lifecycle and execution availability are shown as separate concepts.
- `Pause remote execution` / `Resume remote execution` use the observed runtime generation.
- Existing `Stop` remains the hard connector+tunnel stop.
- Configuration/service switching is fenced while the availability mutation is in flight.
- A focused Node regression locks the distinction between pause/resume and hard stop.

### 3.7 HTTP regression

Added synthetic HTTP regression that proves:

- owner A business call succeeds Online;
- pause leaves HTTP/OAuth transport reachable;
- owner A business call returns `WORKSPACE_OFFLINE`, category `availability`;
- no `WWW-Authenticate` challenge is added;
- A's authorization id/status is unchanged;
- foreign B still receives `EXCLUSIVE_CHAT_LOCKED` and no grant metadata;
- resume restores A business dispatch.

A second synthetic HTTP regression also pauses execution, rotates an OAuth refresh token successfully, verifies the same chat authorization id remains active, observes `WORKSPACE_OFFLINE` for business dispatch, then resumes without re-login.

This is synthetic HTTP evidence, not real ChatGPT-host acceptance.

### 3.8 Observability

Availability transitions and offline tool rejection now emit sanitized local log records containing only non-secret workspace id, transition/rejection class, tool name, runtime generation and in-flight count. Tool arguments, raw session bindings and credentials are not logged.

## Failure-first iteration history

Early Round 3 validation intentionally remains recorded:

- public listener tuple widened from 2 to 3 elements;
- existing OAuth/HTTP fixtures failed compilation;
- GitNexus independently classified the listener entrypoint CRITICAL;
- implementation was narrowed to preserve the existing public API.

Later compile errors exposed the internal gate-aware function not being re-exported crate-wide and one stale triple destructure in the noauth fixture. Both were fixed without changing the preserved public contract.

## Remaining work in this issue

- obtain a green full source regression for the narrowed backend candidate;
- review the final full-source validation result;
- review final `detect-changes` critical blast radius and exact diff;
- record Round 3 evidence in `iterations.md`;
- update task/status files;
- keep PR draft until Round 3 gates converge.

## Non-claims

This issue does not claim:

- that ChatGPT will not show reconnect UI;
- that desktop-process exit is survivable;
- that machine sleep/power-off is survivable;
- that real-host OAuth refresh while offline has been validated.

Those remain Round 5 acceptance boundaries.

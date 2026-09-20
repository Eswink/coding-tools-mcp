# ISSUE-008 — Intent-aware offline-safe lifecycle UX

Status: OPEN — DESIGN READY; IMPLEMENT AFTER ISSUE-006  
Parent: [plan.md](plan.md)  
Depends on: ISSUE-003 backend contract  
Motivation: original reconnect UX can still be triggered by the current prominent hard-stop action

## Problem

Round 3 intentionally preserved the backend meaning of `stop_runtime` and added explicit:

- `pause_mcp_execution`;
- `resume_mcp_execution`.

That was the correct compatibility-first backend change.

However, the current desktop UI still exposes the running MCP service's primary power action as:

```text
停止
```

and `ServicePanel` explicitly tells the operator that the tunnel stops together with the service.

The separate `ExecutionAvailabilityPanel` offers Pause/Resume, but the operator must already understand the architectural distinction.

Therefore the original problem can still be reproduced by normal UI usage:

```text
operator clicks prominent Stop
 -> listener stops
 -> tunnel stops
 -> connector becomes unreachable
 -> ChatGPT may present reconnect UI
```

Real-host UI behavior remains unconfirmed, but the local product intent is still too easy to express as the unsafe lifecycle action.

## Objective

Make **pause execution** the normal workspace-level operator action while keeping **hard stop connector** available as an explicit advanced/destructive action.

Do not change backend hard-stop semantics.

## Proposed MCP UI state model

### Connector stopped

Primary action:

```text
启动 Connector
```

Execution action is unavailable because no control plane exists.

### Connector running + execution Online

Primary workspace action:

```text
暂停远程执行
```

Secondary advanced/destructive action:

```text
停止 Connector
```

### Connector running + execution Offline

Primary workspace action:

```text
恢复远程执行
```

Secondary advanced/destructive action remains:

```text
停止 Connector
```

## Hard-stop confirmation

Hard stop must require an explicit confirmation when a public MCP connector is running.

The warning should state facts, not host predictions:

- MCP listener will stop;
- configured tunnel will stop;
- remote MCP/OAuth endpoint will become unreachable until restarted;
- active workspace execution stops accepting new work;
- this is different from Pause remote execution.

Because real ChatGPT behavior is not yet validated, do not claim the UI definitely will or will not show a reconnect card.

Suggested operator wording:

```text
停止 Connector 会关闭 MCP/OAuth 监听器和公网隧道。
如果只是暂时不允许远程操作，请使用“暂停远程执行”。
```

## Close-window / tray behavior

Existing desktop behavior already intercepts ordinary main-window close and can keep the process running in the tray.

ISSUE-008 must preserve:

- close window != quit process;
- explicit tray/app Quit remains a real process exit;
- UI WebView recreation must not take MCP/FRP down;
- no hidden auto-stop when navigating away from a workspace page.

## Delete workspace

Deleting a workspace is destructive and may hard-stop/remove its connector.

This is not the same intent as temporarily leaving or pausing a workspace.

The delete confirmation should not be replaced by Pause.

## Actions service

Do not apply the MCP pause semantics to ChatGPT Actions automatically.

Actions has a separate runtime/auth model and must remain unchanged unless a dedicated availability contract is designed for it.

## Component direction

Current layers:

```text
ExecutionAvailabilityPanel
ServicePanel
WorkspaceServiceView
workspace/[id]/+page.svelte
```

Preferred first implementation:

1. keep backend APIs unchanged;
2. make MCP running primary action use `pauseMcpExecution/resumeMcpExecution`;
3. move hard `stopRuntime` into a clearly named secondary action;
4. remove duplicated/conflicting controls so there is one obvious normal action;
5. keep connector lifecycle/status visible separately from execution state.

Do not overload the generic Actions `ServicePanel` contract if doing so would make it impossible to express the MCP-specific split cleanly. A dedicated MCP lifecycle control component is acceptable.

## Failure-first UX contract

Before editing components, add source/UI contract tests proving the current problem:

- running MCP primary ServicePanel action is `停止`;
- that action is wired to `stopRuntime`;
- Pause exists separately and is not the primary service action.

Then implement the new contract:

| MCP state | Primary | Secondary |
|---|---|---|
| stopped | Start Connector | none |
| running + Online | Pause remote execution | Stop Connector |
| running + Offline | Resume remote execution | Stop Connector |
| starting/stopping | disabled progress state | disabled |

## Required regressions

1. Primary running action never calls hard stop.
2. Pause keeps listener/tunnel/runtime generation unchanged.
3. Resume keeps OAuth/chat owner unchanged.
4. Hard stop still calls existing `stop_runtime`.
5. Hard-stop confirmation is required.
6. Actions start/stop behavior is unchanged.
7. Workspace navigation does not stop/pause services.
8. Main-window close-to-tray does not stop services.
9. Delete workspace behavior remains explicit/destructive.
10. Existing offline-safe UI and backend tests remain green.

## Impact gate

Before changing existing Svelte components:

- use GitNexus where symbols are indexed;
- preserve the known Svelte indexing limitation if it remains;
- supplement with exact source call-site review and focused Node/Svelte tests.

Likely targets:

- `src/lib/components/ServicePanel.svelte`;
- `src/lib/components/workspace/ExecutionAvailabilityPanel.svelte`;
- `src/lib/components/workspace/WorkspaceServiceView.svelte`;
- `src/routes/workspace/[id]/+page.svelte`;
- `src/lib/api/workspaces.ts`.

No Rust production edit should be required unless UI review exposes a missing backend status field.

## Acceptance

SOURCE/UX PASS:

- the common MCP workflow uses Pause/Resume, not hard Stop;
- hard Stop remains available and clearly named;
- no backend auth/tunnel semantics are weakened;
- no Actions regression;
- cross-platform frontend/source checks pass.

HOST VALIDATED remains separate:

Only the eventual real ChatGPT test can determine whether this operator mapping eliminates the observed reconnect prompt in the actual host.

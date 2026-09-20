# Round 3 Impact Preflight

Status: MANUAL PREPARATION ONLY — NOT A SUBSTITUTE FOR REQUIRED GITNEXUS IMPACT

Date: 2026-09-20

## Purpose

Prepare the exact symbol set and expected execution flows for the mandatory impact-analysis gate before ISSUE-003 edits production code.

## Candidate symbols

### Runtime lifecycle

- `RuntimeEntry`
- `RuntimeSupervisor::start`
- `RuntimeSupervisor::status`
- `RuntimeSupervisor::begin_stop`
- `RuntimeSupervisor::finish_stop`
- `RuntimeSupervisor::public_origin_handle`
- `RuntimeSupervisor::active_tunnel_service_keys`

Expected callers/flows from source inspection:

```text
Tauri runtime commands
 -> RuntimeSupervisor
 -> MCP listener generation
 -> tunnel route synchronization
 -> frontend RuntimeStatus
```

### Tool context

- `ToolContext::from_workspace_with_harness_root`
- `ToolContext::background_snapshot`
- `ToolContext` struct construction sites

Expected flows:

```text
mcp::new_state
 -> ToolContext
 -> listener request snapshot
 -> chat domain scoped context
 -> tool dispatch / async task stores
```

### Remote authorization / dispatch

- `chat_domain::intercept`
- `ChatAuthorizer::admit`
- `ChatAuthorizer::permit`

Expected flows:

```text
MCP tools/call
 -> call_tool
 -> chat_domain::intercept
 -> authorization admission
 -> per-chat domain
 -> recursive call_tool
 -> dispatch
```

The design intends to avoid modifying `ChatAuthorizer` unless the mandatory impact result proves that a separate execution gate cannot safely linearize pause/admission.

### Status/API/UI

- `RuntimeStatusDto`
- TypeScript `RuntimeStatus`
- `src/lib/api/workspaces.ts` runtime wrappers
- workspace status controls and stores consuming RuntimeStatus

## Expected risk

Manual classification: **HIGH**.

Reasons:

- runtime lifecycle is shared with tunnel synchronization;
- remote tool admission is security-sensitive;
- ToolContext snapshots are shared by async execution paths;
- status DTO changes propagate to frontend polling and UI;
- incorrect ordering can leak availability to a foreign chat or allow a tool to slip through after pause.

This risk level must be confirmed/replaced by the repository-required GitNexus output before implementation.

## Required GitNexus targets

At minimum run upstream impact for:

```text
RuntimeSupervisor::start
RuntimeSupervisor::status
ToolContext::background_snapshot
chat_domain::intercept
RuntimeStatusDto
```

Then review affected execution processes and run `gitnexus_detect_changes` before any production commit.

## Implementation ordering after gate

If impact analysis does not reveal a stronger coupling:

1. add standalone `WorkspaceExecutionGate` module + unit tests;
2. thread gate through ToolContext/new_state/listener generation;
3. integrate one top-level gate acquisition in chat-domain remote dispatch;
4. add pause/resume RuntimeSupervisor methods;
5. expose Tauri IPC;
6. add RuntimeStatus execution-state field;
7. add TypeScript wrapper/type;
8. integrate UI last;
9. run full regression + exact change detection.

Do not combine tunnel redesign, OAuth changes or chat-lease changes into the same first implementation increment.

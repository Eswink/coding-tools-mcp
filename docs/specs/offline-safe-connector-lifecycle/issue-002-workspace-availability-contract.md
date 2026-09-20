# ISSUE-002 — Workspace availability contract and error taxonomy

Status: DESIGN FROZEN — PRODUCTION EDITS BLOCKED ON REQUIRED GITNEXUS IMPACT  
Parent plan: [plan.md](plan.md)  
Round: 2 / 5  
Production implementation: BLOCKED until repository-required impact analysis is available

## Inputs

Round 1 produced a cross-platform validated fault harness, but real ChatGPT host behavior is intentionally deferred to Round 5. Therefore all host-facing conclusions in this issue are **provisional**.

Verified architectural input:

- MCP transport and OAuth endpoints share the same per-workspace listener.
- `stop_mcp_service` tears down that listener and then the tunnel.
- chat authorization runs inside the tool-dispatch path after requests already reached the service.
- `chat_domain::intercept` is the existing remote-authorization gate before actual tool dispatch.
- `ToolContext::background_snapshot` already shares service-owned task/session resources across request snapshots.
- `RuntimeSupervisor` owns listener lifecycle state and the current public origin handle.

## Design decision

Adopt **Level A** as the provisional implementation target:

> Keep the connector control plane reachable while independently pausing new workspace execution.

This is intentionally the smallest reversible design. It does not claim to solve desktop-process exit, machine sleep, power-off or full network loss.

## State ownership

Do not overload the existing `RuntimePhase`.

### Existing control-plane phase

```text
Stopped
Starting
Running
Stopping
Error
```

This continues to mean listener/process lifecycle.

### New workspace execution availability

```text
Online
Offline
```

Round 3 may add a transient `Pausing` state only if required by actual async-task handling. Do not introduce speculative states into persistence or public contracts.

The first implementation should keep availability ephemeral and service-generation-bound. Starting a new listener generation explicitly starts Online unless the product UI later introduces a persisted pause policy.

## Atomic execution gate

Source review of `chat_domain::intercept` shows that a plain availability flag would leave a TOCTOU race: a request could observe Online, then a local pause could commit before actual dispatch begins.

Use an explicit admission gate instead.

Proposed internal model:

```text
WorkspaceExecutionGate
  └─ Mutex<GateState>
       ├─ generation
       ├─ availability: Online | Offline
       └─ in_flight: usize

ExecutionPermit
  └─ RAII guard that decrements in_flight on drop
```

Atomic operations:

```text
try_admit()
  lock
  if Offline -> WORKSPACE_OFFLINE
  if Online  -> in_flight += 1; return ExecutionPermit
  unlock

pause()
  lock
  availability = Offline
  snapshot in_flight
  unlock
  return success

resume(expected_generation)
  lock
  reject stale generation / stopped replacement
  availability = Online
  unlock
```

The linearization rule is:

> If `try_admit` acquired a permit before `pause` committed, that operation was already admitted and may finish. Once `pause` returns, every later `try_admit` must fail.

Ownership:

```text
RuntimeEntry
  ├─ listener shutdown
  ├─ listener handle
  ├─ public origin
  └─ Arc<WorkspaceExecutionGate>
            │
            └── ToolContext / background_snapshot / chat-scoped copies
```

Requirements:

1. A replacement listener receives a new gate/generation.
2. A stale pause/resume action cannot mutate a replacement listener.
3. The gate lock is never held during tool execution, filesystem I/O, executor locks, auth locks or tunnel I/O.
4. `background_snapshot` and chat-scoped copies share the same gate instance.
5. Gate acquisition occurs only once for a top-level remote business call; recursive chat-scoped dispatch must not double-count admissions.

## Dispatch ordering

Security ordering is mandatory.

For a remote business tool:

```text
HTTP OAuth verification
  -> tool name validation
  -> chat_domain::intercept
       -> identity / exclusive-owner / scope admission
       -> availability check
       -> per-chat runtime-domain scoping
       -> actual tool dispatch
```

The availability check must occur **after** the existing chat authorization/admission check and **before** side effects.

Reason:

- a foreign/non-owner chat must continue to receive `EXCLUSIVE_CHAT_LOCKED`, not learn that the workspace is offline;
- an unauthorized chat must continue to receive the existing authorization-required semantics;
- only an already-admitted conversation may receive `WORKSPACE_OFFLINE`.

For already chat-scoped recursive/background dispatch, availability must still be checked before a new externally initiated business operation. Existing asynchronous work that was already admitted may continue to terminal state; pausing does not retroactively kill processes.

## Tool classes while Offline

| Surface | Offline behavior |
|---|---|
| OAuth discovery / authorize / token | unchanged |
| MCP initialize / ping | unchanged |
| `tools/list` | unchanged; stable tool catalog |
| `auth_status` | unchanged authorization semantics |
| `request_chat_authorization` | initially unchanged; Round 4 may suppress new pending requests while offline |
| already admitted business tool call | typed `WORKSPACE_OFFLINE` tool error |
| existing async task execution | continues; no automatic kill |
| task polling/cancel | design review required: may remain available if needed to safely drain existing work |

The exception for task polling/cancel is important. A blanket offline gate over every business tool could prevent the current owner from observing or cancelling work that started before pause.

Therefore Round 3 uses an explicit classification:

```text
auth_control
  auth_status
  request_chat_authorization

drain_control_allowed_offline
  get_exec_task
  list_exec_tasks
  read_output
  cancel_exec_task
  kill_session
  write_stdin

requires_online_execution
  every other exposed business tool
```

`write_stdin` is allowed only because it targets an already-existing interactive session; it must not be able to create a new process.

Do not infer this classification from `readOnlyHint` or mutating-tool annotations.

## Error taxonomy

### Authentication errors

Remain transport/authentication failures and may legitimately trigger OAuth UI.

Examples:

- missing/invalid bearer token;
- expired token with failed refresh;
- invalid OAuth grant.

They keep existing HTTP/OAuth semantics and may carry `WWW-Authenticate` where protocol requires it.

### Conversation authorization errors

Remain MCP tool/business permission errors:

- `CHAT_AUTHORIZATION_REQUIRED`
- `EXCLUSIVE_CHAT_LOCKED`
- `CHAT_WORK_DRAINING`
- `CHAT_RECOVERY_REQUIRED`
- `INSUFFICIENT_CHAT_SCOPE`

They must not be converted into OAuth login challenges.

### Workspace availability errors

New typed MCP tool result:

```json
{
  "ok": false,
  "error": {
    "code": "WORKSPACE_OFFLINE",
    "category": "availability",
    "retryable": false,
    "message": "Workspace execution is paused locally."
  },
  "requires_local_action": false
}
```

MCP wrapping should keep this as a normal tool result with `isError=true`, not an HTTP 401/403/503 transport response.

Do not include:

- workspace path;
- project name;
- owner;
- active task details;
- machine name;
- local port;
- tunnel URL.

## Pause/resume command contract

Do **not** silently redefine existing `stop_runtime` in Round 3.

Add explicit local IPC operations:

```text
pause_mcp_execution(workspace_id)
resume_mcp_execution(workspace_id)
```

Semantics:

### pause

- requires the MCP listener to be Running;
- atomically prevents new admitted execution;
- does not revoke OAuth;
- does not revoke active chat authorization;
- does not transfer exclusive ownership;
- does not stop the tunnel;
- does not kill already admitted async tasks/sessions;
- returns current runtime status plus execution availability.

### resume

- requires the same live listener generation;
- restores new execution admissions;
- does not recreate OAuth/chat grants;
- does not restart the listener or tunnel;
- fails closed if runtime is stopped/error or recovery fence blocks execution.

### hard stop

Existing `stop_runtime` keeps its current hard-stop meaning:

- stop listener;
- stop tunnel;
- connector becomes unreachable.

The UI must clearly distinguish **Pause remote execution** from **Stop connector**. The final UX wording belongs to ISSUE-003 implementation/review.

## Runtime status DTO

Do not encode availability into the existing `state` string.

Proposed additive field:

```text
execution_state: "online" | "offline"
```

Compatibility:

- existing `state` remains `running/stopped/...`;
- old frontend/API consumers that ignore the new field keep working;
- new UI can render:
  - Connector: Running
  - Workspace execution: Paused

If serialization compatibility makes an additive field risky, introduce a new dedicated DTO rather than reusing `state`.

## Async task policy

Pause is an **admission fence**, not a process kill.

Required invariant:

> No new remote side-effecting or workspace-reading operation begins after pause commits, while work admitted before the commit may finish or be explicitly cancelled.

To preserve safe draining, the offline-allowed set is frozen for the first implementation:

- `get_exec_task`
- `list_exec_tasks`
- `read_output`
- `cancel_exec_task`
- `kill_session`
- `write_stdin`

No other business tool is allowed while Offline in the first implementation. The required impact analysis may identify a safety reason to shrink this set; expanding it requires a new design review.

Starting new work remains blocked:

- `exec_command`
- `start_exec_task`
- file read/write;
- Git;
- history writes/reads;
- Harness task mutation;
- cwd mutation/read.

## Recovery interaction

Existing `CHAT_RECOVERY_REQUIRED` remains stronger than availability.

If recovery fence is not ready:

```text
recovery required
  > offline
  > online
```

Do not let resume clear a recovery fence.

## OAuth and refresh interaction

Pause/resume must not mutate:

- access token lifetime;
- refresh-session lifetime;
- refresh family;
- OAuth subject/client/resource binding;
- chat lease deadline.

A refresh while execution is Offline should succeed exactly as it would Online if the OAuth control plane is healthy.

This is a core synthetic/integration regression for Round 3.

## Tunnel interaction

Level A requires the MCP tunnel to follow **control-plane lifecycle**, not execution availability.

Therefore:

- pause => tunnel unchanged;
- resume => tunnel unchanged;
- hard stop => tunnel stops as today;
- listener error => existing orphan cleanup behavior remains.

No FRP/Cloudflare process policy change is required merely to represent Offline.

## Observability

Add only non-secret transition metadata:

```text
event=workspace_execution_availability
workspace_id=<internal id>
from=online
to=offline
reason=local_pause
runtime_generation=<non-secret generation>
```

For rejected tool calls:

```text
event=remote_tool_rejected
class=availability
code=WORKSPACE_OFFLINE
tool=<canonical tool name>
```

Never log raw session binding or tool arguments.

## Compatibility

### Backward compatible

- tool list remains stable;
- OAuth contract unchanged;
- existing stop/start runtime behavior remains;
- existing chat authorization error codes remain;
- existing tunnel start/stop behavior for hard stop remains.

### New behavior

Only callers using the new pause/resume operations observe the split state.

This allows rollout without forcing the existing Stop button to change semantics in the first backend commit.

## Threat review

Primary risks:

1. **Authorization ordering leak** — availability checked before owner/scope reveals state to foreign chats.
2. **TOCTOU admission** — pause races with tool dispatch and a new operation slips through after pause reports success.
3. **Generation race** — delayed pause/resume mutates a replacement listener.
4. **Drain lockout** — offline gate blocks task cancellation/observation.
5. **State conflation** — frontend reports connector stopped when only execution is paused.
6. **OAuth coupling regression** — pause accidentally restarts listener or refresh runtime.
7. **Tunnel coupling regression** — pause stops FRP/cloudflared.

Round 3 tests must be failure-first for all seven.

## Impact-analysis gate

Likely production symbols include:

- `RuntimeEntry`
- `RuntimeSupervisor::start`
- `RuntimeSupervisor::begin_stop`
- `RuntimeSupervisor::status`
- `ToolContext::from_workspace_with_harness_root`
- `ToolContext::background_snapshot`
- `chat_domain::intercept`
- runtime IPC command registration / frontend API wrappers

These are security-sensitive and cross-cutting. Repository rules require GitNexus impact analysis before editing them.

Current ChatGPT tool access does not expose GitNexus/mcp-probe-kit and the local CLI fallback is unavailable in this environment. Therefore ISSUE-002 may freeze design, but ISSUE-003 production edits remain BLOCKED until that required impact step can be executed or the repository rule is explicitly revised by the maintainer.

## Exit criteria

ISSUE-002 reaches DESIGN_FROZEN when:

- state ownership is frozen;
- authorization/availability ordering is frozen;
- error taxonomy is frozen;
- async drain-control exceptions are frozen;
- pause/resume/hard-stop semantics are frozen;
- migration/compatibility scope is frozen;
- Round 3 impact targets are listed;
- no claim is made that real ChatGPT host behavior has been validated.


## Source-review refinement — 2026-09-20

`chat_domain::intercept` currently performs remote scope/owner admission before recursively dispatching through a chat-scoped `ToolContext`. This confirms the intended integration point:

1. existing `ChatAuthorizer::admit` succeeds;
2. acquire one `WorkspaceExecutionGate::try_admit` permit for tools that require Online;
3. build/reuse chat domain;
4. execute recursive `call_tool`;
5. drop execution permit, then existing chat admission guard unwinds.

For drain-control tools, step 2 is skipped, but existing conversation authorization remains mandatory.

This keeps availability out of OAuth and avoids changing `ChatAuthorizer` merely to implement workspace pause.


## Design freeze — 2026-09-20

Round 2 design inputs are frozen for the first implementation increment:

- provisional architecture: Level A;
- control listener lifecycle remains separate from execution admission;
- atomic `WorkspaceExecutionGate` is the pause/admission linearization point;
- authorization precedes availability;
- existing hard stop keeps current semantics;
- explicit pause/resume IPC is additive;
- RuntimeStatus receives an additive execution-state surface;
- OAuth/refresh/chat lease/tunnel configuration are not modified by pause/resume;
- offline drain-control allowlist is fixed to existing-task observation/control tools.

Remaining blocker is procedural and safety-critical, not a design ambiguity: repository-required GitNexus impact must run before editing existing production symbols.

Real ChatGPT host acceptance remains deferred to Round 5 and therefore no reconnect-UX PASS is claimed.

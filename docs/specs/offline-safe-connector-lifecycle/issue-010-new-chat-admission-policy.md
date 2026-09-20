# ISSUE-010 — Explicit new-chat admission policy and single-use local approval window

Status: OPEN — DESIGN FROZEN; FAILURE-FIRST IMPLEMENTATION GATE NEXT  
Parent: [plan.md](plan.md)  
Depends on: ISSUE-003, ISSUE-004, ISSUE-008, ISSUE-009  
Scope: shared-account / first-contact governance for **new** chat approvals

## Problem

ISSUE-009 suppresses fresh local approval noise while workspace execution is intentionally Offline.

One remaining shared-account case exists while execution is Online:

```text
connector reachable
execution Online
no active/pending local chat owner
unapproved conversation invokes request_chat_authorization
```

The current backward-compatible behavior immediately creates a 90-second pending local approval.

For a personal account this is reasonable. For a company-shared ChatGPT account it still means an unrelated coworker can make the local desktop show an approval request simply by invoking the installed connector.

The server cannot hide an installed connector from another person sharing the same ChatGPT account. It **can** control whether an unknown conversation is allowed to create new local approval work.

## Design goal

Add a workspace-level **new chat admission policy** independent from:

- OAuth authentication;
- connector reachability;
- execution Online/Offline;
- existing pending/active chat grants;
- exclusive ownership;
- chat lease TTL.

The policy controls only creation of a **brand-new pending chat grant**.

## Persistent policy

Add a serialized enum to `SessionPolicy`:

```text
new_chat_admission

review       # current behavior; backward-compatible default
local_window # new grant only while locally armed
deny_new     # never create a new grant
```

Rust wire format:

```json
{
  "new_chat_admission": "review"
}
```

Backwards compatibility:

- missing field => `review`;
- unknown value => configuration validation failure;
- existing workspace files deserialize safely without migration;
- OAuth/token/chat TTL defaults stay unchanged.

### Why default remains review

Changing the default to deny/window would silently break existing users and current ChatGPT onboarding.

Shared-account users can opt into `local_window` after understanding the behavior.

## Ephemeral local approval window

`local_window` does **not** persist an “armed” boolean in workspace configuration.

Instead the local authorization service keeps an in-memory, per-workspace, single-use admission window:

```text
arm_new_chat
  -> valid for 90 seconds
  -> permits at most ONE new pending grant
  -> consumed only after a new pending record/event commits
```

Properties:

- local desktop IPC only;
- never exposed as an MCP tool;
- lost on app-process restart;
- cleared when the persistent admission policy changes;
- can be explicitly disarmed;
- countdown is presentation state, not authorization identity;
- arming does not revoke or modify an existing grant;
- arming does not restart listener/tunnel;
- arming does not change OAuth.

### Why single-use

With `exclusive=true`, the first pending request already reserves the workspace, but the single-use contract remains explicit.

With `exclusive=false`, an unlimited 90-second window would permit multiple unrelated conversations to create pending approvals. A single-use ticket keeps the local operator's intent narrow.

## Admission ordering

Required order for `request_chat_authorization`:

```text
OAuth identity
 -> chat identity
 -> recovery fence
 -> exclusive/draining owner
 -> validate request shape/scopes
 -> existing pending/active grant
 -> persistent new_chat_admission policy
 -> local single-use window check (only local_window)
 -> workspace execution Online guard
 -> capacity check
 -> allocate pending grant
 -> consume local window if used
 -> emit pending event
```

The new policy must **not** change:

- malformed request precedence;
- scope validation precedence;
- recovery/exclusive semantics;
- existing pending/active idempotency.

## Interaction with ISSUE-009 Offline behavior

Execution Offline is always a stronger practical admission fence for new allocation.

Remote error remains generic:

```text
CHAT_AUTHORIZATION_UNAVAILABLE
```

The caller cannot distinguish whether new approval is blocked because:

- execution is Offline;
- local_window is not armed;
- deny_new is configured.

This avoids leaking local workspace/admission state.

### Window + Offline race

If a local window is armed and execution becomes Offline before a new grant commits:

- no pending grant/event is created;
- the window is **not consumed** merely by the failed remote attempt;
- the window remains usable until its deadline;
- Resume may allow one new grant if the deadline has not passed.

## Local commands

Extend the local-only `chat_authorization_control` actions:

```text
arm_new_chat
disarm_new_chat
```

No new command surface is required.

### arm_new_chat

Allowed only when persistent policy is `local_window`.

Result snapshot includes:

```json
{
  "admission": {
    "mode": "local_window",
    "armed": true,
    "expires_at": 1234567890,
    "single_use": true
  }
}
```

### disarm_new_chat

Clears the in-memory window idempotently.

No grant is revoked.

## Snapshot contract

Local desktop snapshot gains a non-secret `admission` object:

```json
{
  "mode": "review | local_window | deny_new",
  "armed": false,
  "expires_at": null,
  "single_use": true
}
```

This object is only returned through privileged local UI IPC, not remote `auth_status`.

Remote `auth_status` continues to reveal only the current conversation's grant state.

## Persistent configuration behavior

The policy lives inside existing `SessionPolicy`.

Saving `SessionPolicy` currently:

- revokes current chat grants;
- persists config;
- restarts the running MCP listener.

ISSUE-010 keeps that existing transaction for the persistent mode change. It does **not** broaden this issue into a configuration hot-reload refactor.

The ephemeral arm/disarm action is specifically separate so routine shared-account use does not restart the listener or revoke grants.

A future issue may make selected session-policy fields hot-reloadable, but that is not required for the reconnect/shared-account fix.

## UI

### Remote Session Settings

Add a “新聊天申请” selector:

- `自动进入本机审批` → review
- `仅在本机临时开放时接受` → local_window
- `禁止新聊天申请` → deny_new

Shared-account hint:

> 多人共用同一 ChatGPT 账号时，建议选择“仅在本机临时开放时接受”。这不会隐藏插件，但可以阻止陌生聊天自动制造本机审批请求。

Saving follows the existing warning/restart/revoke flow.

### Chat Authorization Panel

When mode = `local_window`:

- show admission status;
- primary local action: `允许下一条新聊天申请（90 秒）`;
- while armed: show countdown and `关闭新聊天申请`;
- after one pending allocation: automatically returns to closed.

When mode = `deny_new`:

- show “新聊天申请已关闭”;
- do not render Arm button.

When mode = `review`:

- show “新聊天申请：自动进入本机审批（兼容模式）”.

Existing grant approval/revoke UI remains unchanged.

## Failure-first matrix

| ID | Persistent mode | Window | Execution | Existing state | Request | Expected |
|---|---|---|---|---|---|---|
| A1 | review | n/a | Online | none | request auth | pending + one event |
| A2 | review | n/a | Offline | none | request auth | generic unavailable; no record/event |
| A3 | local_window | closed | Online | none | request auth | generic unavailable; no record/event |
| A4 | local_window | armed | Online | none | request auth | one pending + one event; window consumed |
| A5 | local_window | armed | Online | second conversation after A4 | request auth | existing exclusive rule or generic closed; no second new event |
| A6 | local_window | armed | Offline | none | request auth | generic unavailable; window remains until deadline |
| A7 | local_window | expired | Online | none | request auth | generic unavailable; no record/event |
| A8 | local_window | armed | Online | existing pending A | A retries | same grant; window not consumed by retry |
| A9 | local_window | armed | Online | active owner A | A retries | same active grant |
| A10 | local_window | armed | Online | owner A | foreign B | EXCLUSIVE_CHAT_LOCKED |
| A11 | deny_new | n/a | Online | none | request auth | generic unavailable; no record/event |
| A12 | deny_new | n/a | Online | existing active A | A retries | same active grant |
| A13 | any | any | any | recovery required | request auth | CHAT_RECOVERY_REQUIRED |
| A14 | local_window | closed | Online | none | malformed args | existing validation error, not unavailable |
| A15 | local_window | closed | Online | none | auth_status | unauthorized; no policy/window disclosure |
| A16 | local_window | arm -> config change | Online | none | request auth | old window cleared |
| A17 | local_window | armed | Online | none | concurrent 2 requests | exactly one new pending allocation/event |
| A18 | local_window | armed | Online -> Pause race | none | concurrent auth/pause | linearizable: either allocation commits before Pause or Pause returns first and no allocation commits after it |
| A19 | local_window | armed | Resume before expiry | none | request auth | pending if ticket still valid |
| A20 | review/local_window/deny_new | any | any | valid OAuth | refresh | unchanged OAuth behavior |

## Concurrency / linearization

ISSUE-009 already establishes lock order:

```text
chat authorization state -> execution gate
```

ISSUE-010 must keep it.

The admission window is stored under the existing chat authorization state mutex, so policy/window decision and consumption are serialized with grant allocation.

For `local_window`:

1. verify ticket exists and is unexpired under auth mutex;
2. acquire ISSUE-009 Online execution hold;
3. allocate pending record;
4. consume ticket;
5. emit pending event;
6. release execution hold/auth mutex.

This ensures a single-use ticket cannot produce two grants under concurrent requests.

## Open-source comparison

### MCPMate

MCPMate models first-contact governance separately from transport:

```text
deny   -> suspended
review -> pending
allow  -> approved
```

It also exposes profile/server enablement separately from service process lifecycle.

Relevant principle:

> first-contact policy is an explicit governance setting, not an incidental transport failure.

ISSUE-010 intentionally differs by **never auto-approving a ChatGPT conversation**. Even `review` still requires local fingerprint approval.

### Cloudflare Agents

Authentication is explicit connection lifecycle state; it is not automatically spawned by every unrelated state transition.

### MCPJam / Inspector

Connection and per-conversation server participation are distinct.

### Coder

Worker availability is distinct from chat authorization state.

## Non-goals

ISSUE-010 does not:

- hide connector installation from ChatGPT UI;
- identify individual employees behind a shared OpenAI login;
- auto-approve any remote conversation;
- change OAuth scopes/token TTL/refresh rotation;
- persist the armed window;
- hot-reload the persistent session policy;
- change execution Pause/Resume semantics;
- change ChatGPT Actions.

## Impact gate

Before production edits run GitNexus impact for at least:

- `SessionPolicy`;
- `ChatAuthorizer::configure`;
- `ChatAuthorizer::request_guarded`;
- `ChatAuthorizer::snapshot`;
- local `chat_authorization_control`;
- `RemoteSessionSettings`;
- `聊天授权面板v1.svelte`;
- workspace configuration `changed_services` / update path.

Known Svelte indexing gaps must be retained and supplemented with exact call-site review.

## Acceptance

SOURCE PASS requires:

- A1–A20 deterministic coverage;
- backward-compatible default = review;
- single-use ticket under concurrency;
- window is ephemeral and cleared on policy reconfiguration;
- arm/disarm never restart listener/tunnel;
- existing active/pending grant remains stable;
- no remote admission-policy/window disclosure;
- no OAuth challenge for policy denial;
- Offline and policy denial share the same generic remote error;
- Windows + Ubuntu full source regression green;
- packaged revalidation green;
- exact diff/impact evidence recorded.

Real ChatGPT visibility/reconnect behavior remains `UNCONFIRMED_ON_REAL_HOST`.

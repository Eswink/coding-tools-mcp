# ISSUE-009 — Suppress new chat-authorization noise while execution is paused

Status: OPEN — FAILURE-FIRST DESIGN READY  
Parent: [plan.md](plan.md)  
Depends on: ISSUE-003, ISSUE-004, ISSUE-008  
Scope: shared-account / unrelated-chat ergonomics without weakening authorization

## Motivation

The original product problem is not only connector reachability.

With a company-shared ChatGPT account, another person may see the installed connector and invoke it without knowing the local project.

Existing protections already guarantee:

- an active foreign owner receives `EXCLUSIVE_CHAT_LOCKED`;
- foreign calls do not reveal workspace/project/path/task metadata;
- blocked foreign owner requests create no pending grant/event;
- Pause keeps the connector reachable without allowing business execution.

One remaining edge exists when:

```text
workspace execution = Offline
no active/pending local chat owner exists
unapproved conversation calls request_chat_authorization
```

Today `request_chat_authorization` bypasses the execution gate and may allocate a new pending approval, which can create a local tray/desktop notification even though the local operator intentionally paused remote execution.

ISSUE-009 reduces that notification/noise surface.

## Objective

While workspace execution is Offline:

- preserve existing active/pending authorization state;
- preserve `auth_status`;
- preserve existing exclusive/recovery precedence;
- do **not** allocate a brand-new chat authorization request for an unapproved conversation;
- do **not** emit a pending authorization event/notification;
- do **not** reveal that the reason is specifically execution Offline.

After Resume, new authorization requests work exactly as before.

## Error contract

For an unapproved/no-owner conversation attempting a new authorization request while execution is paused:

```json
{
  "ok": false,
  "error": {
    "code": "CHAT_AUTHORIZATION_UNAVAILABLE",
    "category": "permission",
    "retryable": false,
    "message": "Workspace authorization requests are not currently accepted. Do not retry."
  },
  "requires_local_action": false
}
```

The response must not say:

- Offline;
- paused;
- owner identity;
- project/workspace name;
- path;
- execution state;
- whether a tunnel exists.

This is intentionally a permission/admission result, not OAuth and not `WORKSPACE_OFFLINE`.

## Ordering

Required ordering for `request_chat_authorization`:

```text
OAuth identity
 -> chat identity
 -> recovery fence
 -> exclusive/draining owner
 -> existing grant state
 -> execution availability for NEW allocation only
 -> validate requested scopes
 -> allocate pending grant/event
```

This means:

- foreign owner still gets `EXCLUSIVE_CHAT_LOCKED` even when Offline;
- recovery-required still gets `CHAT_RECOVERY_REQUIRED`;
- an existing active/pending caller can inspect its existing grant while Offline;
- only a **new** pending allocation is suppressed.

## Failure-first matrix

| Case | Execution | Chat state | Operation | Expected |
|---|---|---|---|---|
| N1 | Online | unapproved, no owner | request authorization | pending record/event created |
| N2 | Offline | unapproved, no owner | request authorization | `CHAT_AUTHORIZATION_UNAVAILABLE`; no record/event |
| N3 | Offline | active owner A | A requests again | same active grant, no new event |
| N4 | Offline | pending owner A | A requests again | same pending grant, no new event |
| N5 | Offline | active owner A | foreign B requests | `EXCLUSIVE_CHAT_LOCKED`; no record/event |
| N6 | Offline | recovery required | request | `CHAT_RECOVERY_REQUIRED` |
| N7 | Offline | unapproved | auth_status | unchanged unauthorized status; no Offline disclosure |
| N8 | Resume | previously suppressed C | request authorization | normal pending record/event created |
| N9 | Offline | unapproved | business tool | existing `CHAT_AUTHORIZATION_REQUIRED`, not `WORKSPACE_OFFLINE` |
| N10 | Offline | valid OAuth refresh | token refresh | unchanged OAuth behavior |

## Implementation boundary

Prefer keeping workspace availability policy in the chat-domain dispatch layer.

Do **not** modify OAuth or make `ChatAuthorizer` globally aware of workspace execution state unless failure-first evidence proves the dispatch layer cannot preserve existing grants safely.

Candidate flow:

1. call existing `ChatAuthorizer::status` to preserve recovery/exclusive semantics and observe only this conversation's grant state;
2. if the caller already has pending/active state, use existing `request` behavior;
3. if unauthorized and the execution gate is Offline, return generic `CHAT_AUTHORIZATION_UNAVAILABLE` without calling `request`;
4. otherwise call existing `request`.

This avoids allocating a record/event while keeping authorization ownership logic in one place.

## Open-source alignment

### Cloudflare Agents

Its MCP client lifecycle treats authentication as an explicit connection state. A 401 transitions a live connection into `AUTHENTICATING`; authentication is not merely an automatic side effect of every unrelated state.

Reusable principle:

> an unavailable execution/connection state should not automatically spawn fresh human authorization work.

### MCPJam / Inspector family

Server connection and per-conversation enablement are separate controls. This reinforces the idea that a server being installed/reachable does not imply every conversation should initiate authorization.

### Coder

Stopped/unreachable workspace execution surfaces as an execution/connectivity problem, not as a reason to mutate authorization state.

These are design analogies, not protocol requirements.

## Non-goals

ISSUE-009 does not:

- hide the installed connector in ChatGPT UI;
- identify which employee is using a shared ChatGPT account;
- change OAuth login/refresh;
- revoke existing chat grants on Pause;
- change exclusive-owner semantics;
- change the hard Stop Connector path;
- claim real ChatGPT host behavior.

## Impact gate

Before production edit, run focused GitNexus impact for:

- chat-domain `intercept`;
- chat-domain `denied`;
- `ChatAuthorizer::status`;
- `ChatAuthorizer::request`;
- `WorkspaceExecutionGate::snapshot` or any availability helper used;
- chat notification event/inbox path.

Retain lower-bound/UNKNOWN findings.

## Acceptance

SOURCE PASS requires:

- N1–N10 deterministic tests;
- zero pending record/event for N2;
- existing active/pending state preserved while Offline;
- no Offline wording/state leak in the suppression response;
- authorization/exclusive/recovery ordering preserved;
- OAuth refresh tests unchanged;
- Windows + Ubuntu full Rust regression green;
- exact diff and impact review recorded.

Real host / shared-account connector visibility remains `UNCONFIRMED_ON_REAL_HOST`.

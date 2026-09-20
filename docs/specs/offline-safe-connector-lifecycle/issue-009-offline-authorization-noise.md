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
 -> validate request shape/scopes (existing behavior)
 -> existing pending/active grant
 -> execution availability for NEW allocation only
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

Workspace availability policy stays in the chat-domain dispatch layer. OAuth is unchanged, and `ChatAuthorizer` does not gain knowledge of the concrete execution-gate type.

Final flow:

1. chat-domain calls the generic `ChatAuthorizer::request_guarded`;
2. the authorizer resolves identity, recovery, exclusive/draining and the existing request-validation contract under its own mutex;
3. an existing pending/active grant returns without consulting execution availability;
4. only a **new** pending allocation invokes the caller-provided guard;
5. chat-domain acquires a short `WorkspaceExecutionGate::hold_online()`;
6. the hold remains alive through pending record/event commit;
7. Offline maps to generic `CHAT_AUTHORIZATION_UNAVAILABLE`.

The original snapshot-before-request candidate was rejected after TOCTOU review; see the repair iteration below.

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

## Failure-first evidence

Focused validation run `35519244700`: **FAIL as expected before production repair**.

The first test reached the real chat-domain tool dispatch and observed the current behavior while execution was Offline:

```text
request_chat_authorization
expected: CHAT_AUTHORIZATION_UNAVAILABLE
observed: ok=true + a new pending authorization grant
```

The response contained a newly allocated grant id/fingerprint and the local-approval next step, proving the pause state still generated fresh authorization work.

The workflow stopped on that failure before the existing-state ordering test ran. This is retained as failure evidence, not a test-environment failure.

## Impact evidence

GitNexus run `35519175912`: tooling PASS.

Focused results:

- chat-domain `intercept`: LOW, exact — 9 impacted symbols, 1 affected process;
- chat-domain `denied`: LOW, exact — 9 impacted symbols, 2 affected processes;
- `ChatAuthorizer::request`: LOW, **lower-bound** — 5 impacted symbols; 4 receiver-typing call sites dropped;
- `ChatAuthorizer::status`: UNKNOWN/ambiguous; no caller result is not treated as unused;
- `WorkspaceExecutionGate::snapshot`: UNKNOWN, **lower-bound** — 2 receiver-typing call sites dropped.

Exact source review confirms `request_chat_authorization` is dispatched directly in chat-domain `intercept`, and that pending events feed the local notification/inbox path.

Implementation remains bounded to the chat-domain dispatch/error mapping unless compilation or tests prove a gate API change is necessary.

## Repair iteration and atomicity correction

The first bounded repair used a read-only execution-state snapshot before calling the existing authorization allocator. Focused tests passed, but review exposed a pause-vs-allocation TOCTOU:

```text
request observes Online
pause commits and returns
request allocates pending approval afterward
```

That would violate the intended post-pause guarantee.

The repair was therefore strengthened before full acceptance:

1. `ChatAuthorizer` now exposes a generic guarded-new-allocation path while keeping the existing unguarded `request` API for all existing callers.
2. Existing recovery/exclusive/pending/active state is resolved under the authorization mutex first.
3. Only when a **new** grant would be allocated does the caller acquire a short-lived Online hold from the execution gate.
4. The authorization mutex and Online hold remain alive through pending-record insertion and event publication.
5. `pause()` cannot commit until that short allocation finishes; after `pause()` returns, no later pending grant can be created.

The lock order is:

```text
chat authorization state
 -> execution availability gate
```

No path introduced by ISSUE-009 acquires those two locks in the reverse order. The hold never wraps tool execution or blocking I/O.

A runtime regression verifies that Pause cannot commit while the short Online allocation hold is alive.

### Request-validation compatibility

Manual diff review caught a second semantic-risk before acceptance: the first guarded allocator draft returned an existing pending/active grant **before** validating the new request arguments, while the pre-ISSUE-009 behavior validated request shape/scopes first.

That ordering was restored.

Regression coverage now compares the same malformed authorization request before and during Offline for an existing pending grant and requires byte-for-byte equivalent structured output. Pause must suppress only **new allocation**, not weaken or reorder the existing request-validation contract.

## Full-suite diagnostic — test-owned mutex deadlock

Final-candidate full run `35525452120` reached `Full Rust checks` on both Ubuntu and Windows and stopped making progress. The run was later cancelled when the bounded correction was pushed.

Source review found a deterministic deadlock in the **new regression test**, not in the production request path:

```text
test thread
  hold_online()
    -> owns execution gate mutex
  gate.snapshot()
    -> attempts to lock the same non-reentrant mutex again
    -> self-deadlock
```

The production ISSUE-009 path never calls `snapshot()` while holding `OnlineExecutionHold`.

The test was corrected to assert the blocked pause through the synchronization channel, drop the Online hold, then inspect the gate state afterward. The product locking contract was not weakened.

Correction commit:

```text
c1a89c08d812f70527eb61e5e25bd3c492ab854a
fix(issue009): avoid reentrant execution-gate test deadlock
```

A dedicated focused workflow now runs the gate linearization regression itself before the authorization matrix so this class of test bug cannot silently stall the full suite again.

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


## Focused final-candidate verification

Focused workflow run `35524230919`: **SUCCESS**.

Four isolated regressions passed on the final source candidate:

- `offline_unapproved_authorization_request_is_suppressed_without_pending_noise_until_resume`;
- `offline_preserves_existing_pending_active_and_exclusive_ordering`;
- `recovery_required_precedes_offline_authorization_suppression`;
- `offline_new_authorization_is_a_non_oauth_tool_error_and_resumes_cleanly`.

The HTTP regression verifies the suppression result remains:

```text
HTTP 200
WWW-Authenticate absent
error.category = permission
error.code = CHAT_AUTHORIZATION_UNAVAILABLE
requires_local_action = false
```

and that Resume restores the normal pending-approval path without re-running OAuth.

### OAuth challenge reference check

Current MCP Inspector and TypeScript SDK documentation confirms that HTTP `401` or `403 insufficient_scope` plus `WWW-Authenticate` is deliberately interpreted as OAuth re-authorization / step-up.

Therefore keeping local workspace/chat admission states as MCP tool-level results instead of HTTP OAuth challenges is not merely cosmetic: using a challenge here would actively instruct capable clients to start re-authentication.

### Final change-impact candidate

Graph job from full run `35524220691`: PASS.

```text
Changes: 10 files, 51 symbols
Affected processes: 4
Risk level: medium
```

Affected flows are limited to the chat-domain intercept/error path and the guarded authorization request's busy/event/fence paths.

This aggregate result does not erase the focused lower-bound/UNKNOWN findings from the pre-edit GitNexus review.

Full Windows/Ubuntu source validation and packaged revalidation remain the final gates before merge.

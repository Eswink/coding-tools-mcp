# ISSUE-004 — Non-disclosing multi-user boundary

Status: OPEN — FAILURE-FIRST PRIVACY MATRIX REQUIRED  
Parent: [plan.md](plan.md)  
Depends on: [issue-003-control-execution-decoupling.md](issue-003-control-execution-decoupling.md)  
Round: 4 / 5  
Real ChatGPT host acceptance: DEFERRED TO ROUND 5

## Objective

Harden the Level A control/execution split so conversations that do not own the local workspace cannot learn project-specific state, even when they share the same connector installation or a valid OAuth identity.

The boundary is conversation-scoped. It does **not** claim that the ChatGPT product can hide an installed connector from other users of the same account. That host-level visibility/entitlement question remains outside the local MCP server and must be documented separately.

## Threat model

Actors:

- **A — owner**: valid OAuth + active local chat grant for the workspace.
- **B — foreign authenticated conversation**: valid OAuth, different `openai/session`, while A owns the workspace.
- **C — authenticated but unapproved conversation**: valid OAuth, no active local grant.
- **D — local desktop operator**: trusted local UI/IPC, not a remote ChatGPT conversation.

Workspace states:

- execution Online;
- execution Offline;
- chat work Draining;
- recovery required.

Remote surfaces:

1. OAuth discovery / authorize / token control plane;
2. MCP `initialize`, `ping`, `tools/list`;
3. `auth_status`;
4. `request_chat_authorization`;
5. business tools such as `server_info`, files, git, history and execution;
6. existing-task drain-control tools;
7. remote error envelopes.

## Non-disclosure contract

Before successful conversation authorization, remote responses must not disclose:

- workspace path;
- workspace display/project name;
- workspace/profile id;
- owner binding or owner fingerprint;
- another conversation's grant id/fingerprint/scopes/timestamps;
- task/job/session ids or output;
- current default cwd;
- git/file/history contents;
- whether execution is Online vs Offline when a stronger authorization/ownership denial applies.

Allowed pre-authorization information is application-level and static enough to operate the connector:

- product/server identity and protocol version;
- OAuth metadata needed to authenticate;
- generic tool catalog/schema;
- generic error class and stable non-secret error code.

## Error precedence

Required precedence:

```text
OAuth identity
  -> conversation identity
  -> recovery / exclusive owner / grant / scope
  -> workspace execution availability
  -> business dispatch
```

Examples:

- B + Offline + A owns => `EXCLUSIVE_CHAT_LOCKED`, not `WORKSPACE_OFFLINE`.
- C + Offline => `CHAT_AUTHORIZATION_REQUIRED`, not `WORKSPACE_OFFLINE`.
- A + Offline => `WORKSPACE_OFFLINE` for gated business tools.
- A + Offline + existing task control => existing task-control semantics, subject to the existing local grant/scopes.
- recovery required => `CHAT_RECOVERY_REQUIRED` remains stronger than execution availability.

## Failure-first matrix

| Case | Actor | Workspace state | Operation | Expected |
|---|---|---|---|---|
| P1 | B | Online | `auth_status` | exclusive generic denial; no owner/grant metadata |
| P2 | B | Offline | `auth_status` | same generic exclusive denial; no Offline disclosure |
| P3 | B | Offline | `server_info` | `EXCLUSIVE_CHAT_LOCKED`; no path/profile/offline metadata |
| P4 | B | Offline | `request_chat_authorization` | no pending grant, no event/notification, no fingerprint |
| P5 | C | Offline | `server_info` | `CHAT_AUTHORIZATION_REQUIRED`; no Offline disclosure |
| P6 | C | Offline | `list_exec_tasks` | authorization denial; no task summaries |
| P7 | A | Offline | `server_info` | typed `WORKSPACE_OFFLINE` only |
| P8 | A | Offline | `list_exec_tasks` | only A's chat-domain tasks |
| P9 | B | Draining | business tool | `CHAT_WORK_DRAINING`; no work/task detail |
| P10 | B | recovery required | business/auth tool | `CHAT_RECOVERY_REQUIRED`; no recovery generation/path/task detail |
| P11 | any OAuth client | any | `initialize/tools/list/ping` | application metadata only; no workspace-specific values |
| P12 | B | Online/Offline | repeated blocked auth requests | zero new pending grants and zero profile pending events |

## Focused impact evidence

GitNexus workflow run `35507344111` completed successfully after explicit function-kind disambiguation.

Current impact results:

- `ChatAuthorizer::status`: **UNKNOWN**, lower-bound; no callers resolved and 3 receiver-typing call sites were dropped.
- `ChatAuthorizer::request`: LOW, lower-bound; 5 impacted symbols with 4 receiver-typing call sites dropped.
- `ChatAuthorizer::admit`: **UNKNOWN**, lower-bound; no callers resolved and 1 receiver-typing call site was dropped.
- chat-domain `intercept`: LOW, exact; 9 impacted symbols.
- MCP `handle_request`: LOW, exact; 3 impacted symbols.
- MCP `initialize_result`: LOW, exact; 6 impacted symbols.
- `server_info`: LOW, exact; 9 impacted symbols.

The UNKNOWN/lower-bound results are evidence limits, not safety evidence. If the privacy matrix exposes a production defect in those functions, text review and full regression remain mandatory in addition to GitNexus.

Round 4 currently changes tests, documentation and validation workflows only; no production authorization/runtime semantics have been modified.

## Existing evidence inherited from Round 3

Round 3 already proves:

- authorization is evaluated before Offline for an unapproved conversation;
- a foreign conversation remains `EXCLUSIVE_CHAT_LOCKED` while the owner is paused;
- blocked foreign authorization requests allocate no `authorization` response object;
- OAuth refresh does not transfer owner state;
- availability errors contain only generic availability semantics.

Round 4 must expand this from selected examples to a systematic non-disclosure matrix.

## Source review observations

Current code already provides several useful boundaries:

- `ChatAuthorizer::status/request/admit` runs owner/grant checks before business dispatch.
- `request` rejects a foreign owner before scope validation/allocation, preventing fingerprint and pending-event creation.
- `chat_domain::intercept` checks chat admission before the execution gate.
- `server_info` contains workspace path/default cwd and is therefore intentionally sensitive; it must remain unreachable to B/C.
- `initialize`, `ping`, and `tools/list` are control-plane methods and currently expose product/tool metadata rather than workspace contents.

These observations are not sufficient for PASS until encoded as regressions.

## Mandatory impact targets before production edits

If the failure-first matrix exposes a production defect, run GitNexus impact before modifying any of these existing symbols:

- `ChatAuthorizer::status`
- `ChatAuthorizer::request`
- `ChatAuthorizer::admit`
- chat-domain `denied`
- chat-domain `intercept`
- MCP `handle_request`
- MCP `initialize_result`
- `server_info`
- task list/get/cancel paths if a task metadata leak is found

A test-only hardening pass may proceed without production edits. A failing privacy case must be recorded before repair.

## Shared-account limitation

Two different problems must not be conflated:

1. **Local workspace confidentiality** — enforceable here. A foreign conversation must not receive project/workspace data.
2. **Connector visibility in ChatGPT UI / account installation** — host/account behavior. The local MCP server cannot make an installed connector disappear from another user who shares the same ChatGPT account.

Round 4 can guarantee the first boundary at the server. Round 5 real-host testing must characterize the second.

## Acceptance criteria

Round 4 source/synthetic PASS requires:

- P1-P12 covered by deterministic tests or an explicitly recorded unreachable case;
- no blocked response contains path/project/profile/owner/grant/task/session metadata;
- Offline never overrides a stronger authorization/exclusive/recovery denial;
- blocked foreign authorization calls create no pending record/event;
- task domains remain conversation-isolated Online and Offline;
- static control-plane responses contain no workspace-specific runtime data;
- no production auth/OAuth semantics weakened;
- any production fix receives focused GitNexus impact analysis and full source regression;
- exact diff reviewed.

Real ChatGPT account/connector visibility remains a Round 5 acceptance item.

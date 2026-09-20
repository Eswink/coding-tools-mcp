# Offline-safe Connector Lifecycle — Engineering Completion Record

Date: 2026-09-21  
Project branch: `plan/offline-safe-connector-lifecycle`  
Completion class: **ENGINEERING_COMPLETE / HOST_VALIDATION_DEFERRED**

## Scope completed

The engineering work requested for the offline-safe connector lifecycle is complete within the explicitly approved non-real-host scope.

Delivered:

1. **Control plane / execution plane separation**
   - MCP/OAuth listener and tunnel remain available while workspace execution is intentionally paused.
   - Workspace execution is fenced by an atomic admission gate.
   - Pause/Resume is generation-bound and does not mutate OAuth/chat lease state.

2. **Chat authorization and privacy**
   - authorization/exclusive/recovery checks precede workspace availability;
   - foreign/unapproved conversations do not learn workspace/project/path/task metadata;
   - task/session domains remain conversation-isolated;
   - Offline business failures are non-OAuth tool results.

3. **Shared-account noise reduction**
   - while execution is Offline, a brand-new unapproved conversation cannot create a pending local approval;
   - no pending record/event/tray notification is created;
   - existing pending/active grants and recovery/exclusive precedence remain unchanged;
   - Resume restores normal authorization allocation.

4. **Operator intent UX**
   - stopped -> Start Connector;
   - running/Online -> Pause remote execution;
   - running/Offline -> Resume remote execution;
   - hard Stop Connector remains a separate confirmation-gated infrastructure action.

5. **HTTP security hardening**
   - present Origin is validated before MCP/OAuth handlers;
   - missing Origin remains compatible for non-browser MCP clients;
   - localhost-class browser Origin remains supported;
   - current managed PublicOrigin is matched by scheme + host + effective port;
   - stale/foreign/malformed/opaque/duplicate Origins are rejected generically.

6. **Cross-platform package acceptance**
   - Windows NSIS build/install/executable/uninstall verification;
   - Ubuntu DEB build/install/executable/purge verification;
   - no production release/tag/signing/publication was performed.

## Principal evidence

| Area | Evidence |
|---|---|
| Round 3 control/execution split | run `35506548418` — source/synthetic PASS |
| Round 4 privacy boundary | run `35507366052` — source/synthetic PASS |
| Round 5 packaged engineering acceptance | run `35509843023` — Windows + Ubuntu package lifecycle PASS |
| Windows strict compile | run `35510062552` — PASS |
| Origin hardening | run `35516677404` — full cross-platform PASS |
| Origin packaged revalidation | run `35516447042` — Windows + Ubuntu PASS |
| Intent-aware UX | run `35517763406` — cross-platform Svelte/build/contracts PASS |
| Offline auth-noise final source | run `35527951732` — cross-platform PASS |
| Offline auth-noise final focused | run `35527951725` — PASS |
| Offline auth-noise final packaged | run `35527951727` — Windows + Ubuntu PASS |
| Central PR pre-finalization checks | runs `35530593397`, `35530593428`, `35530593435`, `35530593415` — PASS |

Failures found during development are retained in `iterations.md`; they are not rewritten as PASS.

## Final architecture

```text
ChatGPT / MCP client
        |
        v
MCP + OAuth control listener       <- connector lifecycle
        |
        +-- chat identity / owner / scope
        |
        +-- WorkspaceExecutionGate <- execution lifecycle
        |      Online / Offline
        |
        +-- scoped tool/task domain
        |
        v
Local workspace / processes / files
```

The important invariant is:

> **Workspace execution Offline is not Connector authentication/transport disconnected.**

## Final security ordering

```text
OAuth identity
 -> conversation identity
 -> recovery / exclusive / scopes
 -> availability / new-allocation admission
 -> business dispatch
```

This prevents execution state from becoming a side channel for foreign conversations.

## Rollback

The bounded rollback procedure is recorded in:

`round5-rollback.md`

No destructive persistence migration was introduced by the offline-safe feature.

## Deferred external gates

### Real ChatGPT host

Explicitly deferred by the user because the dedicated connector/tunnel test setup is operationally expensive.

Still unverified:

- actual reconnect-card behavior;
- C1–C10 host classification;
- real host OAuth refresh UX while workspace execution is Offline;
- connector visibility for another person sharing the same ChatGPT account.

Exact truth label:

```text
UNCONFIRMED_ON_REAL_HOST
```

Procedure:

`round5-host-deferred-procedure.md`

### ISSUE-007 live tunnel topology

Host / HTTP2 authority / Fetch-Metadata enforcement remains intentionally blocked until live FRP/Cloudflare forwarding is observed.

Prepared:

- source topology analysis;
- sanitized `tunnel_header_probe` example;
- cross-platform compile workflow;
- live-observation procedure.

This follow-up is not required to merge the offline-safe engineering candidate because Origin validation is already active and Host enforcement without topology evidence could break supported reverse tunnels.

## Merge/release decision

Engineering merge: **ready**.

Release claim:

- allowed: “offline-safe engineering candidate completed and validated on Windows/Ubuntu packages”;
- not allowed yet: “ChatGPT reconnect issue definitively fixed”.

The latter requires the deferred real-host acceptance.

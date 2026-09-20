# Round 2 Design Decision Record

Date: 2026-09-20  
Decision status: PROVISIONAL LEVEL A  
Real-host validation: DEFERRED TO ROUND 5

## Decision

Separate connector control-plane lifecycle from workspace execution admission without introducing a cloud broker.

```text
MCP/OAuth listener + tunnel
        |
        +-- remains Running
        |
WorkspaceAvailabilityHandle
        |
        +-- Online  -> admitted remote business tools may dispatch
        +-- Offline -> admitted remote business tools receive WORKSPACE_OFFLINE
```

Hard stop remains available and retains today's listener+tunnel shutdown behavior.

## Why Level A

Level A is preferred provisionally because:

- it directly addresses the verified lifecycle coupling;
- it does not change OAuth identity/token contracts;
- it does not require a new daemon or remote service;
- it can be introduced additively;
- it is reversible if Round 5 host validation shows that keeping the local control plane alive is insufficient.

This is an engineering minimization choice, not proof of ChatGPT UI behavior.

## Gate placement

The availability gate belongs after conversation admission and before actual dispatch.

```text
OAuth -> conversation permit/admit -> availability -> dispatch
```

This preserves non-disclosure for foreign/non-owner chats.

## API compatibility

First backend increment should add explicit pause/resume IPC and an additive execution-state field. It should not silently redefine existing hard stop.

## Release boundary

No stable release should advertise this as fixing the reconnect UX until Round 5 real ChatGPT acceptance is performed.

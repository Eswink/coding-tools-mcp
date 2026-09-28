# ISSUE-012 production MCP control-plane increment

Tracking: GitHub #35, Epic #32, Draft PR #36. Baseline for implementation: feature branch after ISSUE-020A local-authority bridge. Real VPS/workstation/ChatGPT acceptance remains deferred and is not engineering evidence.

## Boundary

This increment moves the cloud gateway from a synthetic wire laboratory to a Rust MCP control-plane adapter backed by the existing production OAuth identity, enrolled Agent channel, local-authority projection and durable request-admission ledger. It deliberately stops before local tool side effects.

The explicit `coding-tools-mcp-gateway` binary combines the existing identity/OAuth routes, authenticated native Agent route, stable MCP resource path and health checks on one loopback listener. It requires the same protected config/secrets boundary and an already-selected enrolled device. The old identity-only and control-only binaries remain valid explicit modes.

## Security ordering

For every MCP business request:

```text
Host/Origin/header/body bounds
  -> OAuth bearer authentication
  -> MCP version/header mirror validation
  -> Host-provided openai/session binding
  -> local grant/conversation/scope/recovery assessment
  -> Agent presence/availability
  -> durable request admission
  -> STOP (no local dispatch in this increment)
```

OAuth failures remain HTTP 401 with `resource_metadata` challenge. Local authorization or availability failures are HTTP-success MCP tool results and never attach an OAuth challenge. Tool arguments cannot supply the Host session or mint owner/grant/scope state.

When the authenticated conversation has a preserved grant but the Agent is disconnected, an unreconciled projection plus absent current channel presence is classified as `WORKSPACE_OFFLINE` for the public MCP surface. This does not make it execution-eligible: `ChannelController` and `AdmissionStore` still fail closed until the device reconnects and reconciles. A connected-but-unreconciled controller remains `CHAT_RECOVERY_REQUIRED`.

## Wire subset

Modern `2026-07-28` requests require the protocol-version/method/name header mirrors and matching `_meta` version/capabilities. `server/discover`, `tools/list` and `tools/call` return complete results with server metadata. Legacy `2025-11-25` and `2025-06-18` retain headerless `initialize` only, initialized notification, ping/list/call, and reject mixed modern metadata.

The stable catalog contains `auth_status`, `request_chat_authorization`, and `workspace_probe`. Cloud `request_chat_authorization` never allocates a local approval: it reports an existing local grant or a bounded unavailable result. `workspace_probe` is read-only and never reads a file; eligible calls are inserted once into the durable ledger and immediately cancelled before dispatch, returning `EXECUTION_NOT_CONNECTED`. This proves no-replay integration without claiming local execution.

## Rollback

Remove the new MCP module/binary/workflow and stop the explicit MCP service mode. Preserve OAuth families, device registry, projection/drain state, local authority epochs and request ledger. Rollback must not delete migrations or revive revoked authority. Existing identity-only and control-only service modes remain independent fallbacks.

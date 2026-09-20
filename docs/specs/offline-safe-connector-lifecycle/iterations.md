# Iteration evidence

## 00 — Planning baseline

Date: 2026-09-20  
Base: `main@823cbdeba68bbdd832d93f4636f701ddb98474f1`  
Branch: `plan/offline-safe-connector-lifecycle`  
Result: PASS for planning only; no product fix claimed.

### Repository evidence reviewed

- `src-tauri/src/mcp/listener.rs`: per-workspace MCP listener also hosts OAuth discovery, authorize and token endpoints.
- `src-tauri/src/commands/runtime.rs`: `stop_mcp_service` stops listener and then stops MCP tunnel.
- `src-tauri/src/auth/session_policy.rs`: chat lease/access/refresh durations are explicit and separate.
- `src-tauri/src/auth/聊天授权v1.rs`: chat authorization/exclusive owner/draining logic only applies after a request reaches the local service.
- `src-tauri/src/mcp/server.rs`: authorization and business-tool semantics are tool-layer behavior.
- Existing spec style in `docs/specs/exclusive-conversation-refresh/` uses plan/tasks/iterations with evidence-gated completion.

### Initial classification

Observed architectural coupling is sufficient to explain why an intentional local stop removes the remote protocol surface, but it is NOT sufficient to conclude exactly which ChatGPT host condition produces the reconnect card.

Therefore:

- root cause class: control-plane availability coupled to workspace execution lifecycle;
- exact host trigger: UNCONFIRMED;
- implementation choice: BLOCKED on Round 1;
- production change: NONE.

### Next gate

Execute ISSUE-001 C1/C2 first. Do not implement token-TTL or authorization changes as a speculative fix.

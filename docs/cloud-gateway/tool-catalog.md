# Cloud tool catalog and native admission

The public MCP catalog is static and available while the Agent is offline. It exposes the two conversation authorization controls and the explicit business contracts in `services/cloud-agent/src/catalog/`. It does not enumerate a device's directories, workspaces, identities, grants, running jobs, or native capability state. OAuth authenticates the caller; it does not authorize a native operation.

## Contract ownership

The database-free shared catalog supplies tool names, closed argument schemas, native scopes and conservative mutation classes. Unknown tools and unknown arguments fail closed at the gateway and the native live adapter. It is not a generic forwarding route. Native schema and scope parity tests cover the public contracts against the real existing tool registry and chat-domain interceptor.

The `LocalHost::required_scope` contract includes immutable request arguments. `history_session_validate` needs `history.read` for the default/read-only mode and `history.write` only when `repair=true`. `write_stdin` requires both `task.manage` and `exec.run`; binding its primary scope never substitutes for the second scope. Both gateway and native host verify all applicable scopes. The native authorizer and execution gate still mint and commit the opaque admission ticket immediately before real dispatch.

## Bounds and request identity

Arguments are limited to 4096 bytes and results to 8192 bytes. Gateway materialization of advertised schema defaults precedes the existing canonical digest and durable admission. The host receives the exact immutable admitted arguments; no post-admission default or scope rewrite occurs. Native execution, request/peer/grant/epoch binding, expiry, output suppression, cancellation, actual-work drainage and durable uncertain-outcome tombstones remain in force.

The synchronous command schema bounds execution to 20 seconds within the existing 30-second request deadline. Asynchronous tasks retain their separate native execution budget and managed lifetime. Page/output controls are narrowed where compatible with native APIs. A large result is suppressed as an unknown outcome, never truncated into a fabricated successful response or automatically replayed.

Paths supplied through cloud schemas are workspace-relative. Cloud schemas exclude workspace-root and host/sandbox/environment overrides. Existing native canonical containment and tool-specific validation remain required; lexical validation is not a replacement for them. Read-only catalog annotations are hints, not security grants. Tools that can mutate are conservatively marked destructive; native policy still applies.

Offline business calls are not queued. Missing approval or scope is reported before device availability. After uncertain submission, inspect an existing asynchronous task when possible; do not automatically resubmit. Existing request IDs bind tool, canonical arguments, scope, class and the original deadline, and changed submissions conflict.

## Release evidence

This catalog increment must pass shared Agent regression, gateway protocol/real PostgreSQL, direct native admission and real native Agent/WSS/HTTP/PostgreSQL tests. Its passing tests alone do not close application lifecycle, Windows sandbox, managed worktree, Hooks, snapshot, deployment or packaging gates.

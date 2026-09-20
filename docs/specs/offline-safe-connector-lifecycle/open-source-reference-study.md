# Open-source Reference Study — Offline-safe MCP Lifecycle

Date: 2026-09-20  
Scope: post-Round-5 architecture/security review  
Project truth state entering study: `ENGINEERING_CANDIDATE_PASS`, `UNCONFIRMED_ON_REAL_HOST`

## Purpose

Compare the offline-safe connector implementation against current open-source MCP/workspace systems and the current MCP reference implementation. The goal is to identify patterns worth adopting without reopening already validated architecture speculatively.

## 1. Coder — pin context/tool definitions, resolve execution lazily

Reference:

- repository: `coder/coder`
- inspected revision family: `9661661ba6d1008eb1f75f5a8933c8101001e0b3`
- `coderd/x/chatd/context_prompt.go`
- `coderd/x/chatd/chattool/mcpworkspace.go`

Observed pattern:

1. Workspace context and MCP tool metadata are pinned into chat context resources.
2. The pinned context remains usable even when the workspace agent cannot currently be resolved.
3. Model-facing tool wrappers keep stable tool definitions.
4. Actual tool execution obtains a live workspace-agent connection lazily at call time.
5. Connection failure becomes a tool execution error instead of deleting the model-facing tool.

Relevant source comments explicitly state that an unresolved agent does not blank pinned context and that the pin keeps working when the workspace is unreachable.

### Decision for coding-tools-mcp

**ADOPT / already aligned.**

Our Round 3 decision to keep a stable tool catalog while gating execution is consistent with this pattern:

```text
stable connector/tool surface
        |
        +-- runtime availability checked at execution
```

Do not switch to dynamic empty `tools/list` while Offline.

Further useful idea: if future chats need durable context independent of live workspace reachability, treat that context as an explicit snapshot rather than as evidence the workspace is live.

## 2. Cloudflare Agents — durable control-plane lifecycle and explicit connection state

Reference:

- repository: `cloudflare/agents`
- inspected revision family: `c076e4c9ff6cfb72931085226edfd3ee7965ac48`
- `packages/agents/src/mcp/client/index.ts`
- `packages/agents/src/mcp/client/do-oauth-client-provider.ts`
- `docs/agents/mcp-client.md`

Observed pattern:

1. `MCPClientManager` is installed as a lifecycle capability.
2. `onStart()` restores persisted MCP connections before the host handles work.
3. Connection/discovery work has explicit states rather than being inferred from tool-call failure.
4. OAuth token/provider state lives in durable storage, separate from transient object execution.
5. Restore/reconnect operations can be awaited explicitly.
6. Persisted stale transport/session state is not blindly replayed; newer code discards unsafe legacy session identifiers and reconnects.
7. In-flight interactive work that cannot be reconstructed safely is not automatically resumed.

### Decision for coding-tools-mcp

**DEFER to Level B/C, but adopt the invariants now.**

Round 3 already preserves the important safety rule:

> persistent control/authorization state must not imply that uncertain in-flight execution can be resumed.

If we later introduce a background daemon or remote broker, use an explicit state machine such as:

```text
Disconnected
Connecting
Authenticating
Discovering
Ready
Degraded
```

and persist only reconstructible control-plane state.

Do not persist a boolean named `connected` as a substitute for a recoverable lifecycle model.

## 3. mcp-remote — proactive OAuth expiry and refresh single-flight

Reference:

- repository: `punkpeye/mcp-remote`
- inspected revision family: `8ba22bdb4e73b818abf22b5e0c8fb5d96e90203b`
- `src/lib/node-oauth-client-provider.ts`

Observed OAuth hardening:

- persisted absolute `expires_at`;
- expiry safety margin before sending a token that may expire in flight;
- process-local `refreshInFlight` single-flight;
- host-level refresh lease so multiple processes do not redeem a rotating refresh token concurrently;
- token-exchange storm brake;
- repeated browser-authorization storm brake;
- concurrent authorization attempts coalesced into one flow.

### Decision for coding-tools-mcp

**NO immediate server-side copy.**

Our application is currently the OAuth resource/authorization surface rather than a general outbound MCP OAuth client. Round 3 also proves OAuth refresh does not extend the local chat lease.

Adopt these patterns only if Level B/C adds an outbound MCP client or multiple processes can redeem the same upstream refresh token.

The reusable principle is:

> token refresh concurrency is a credential-lifecycle problem, not a workspace-availability problem.

## 4. Supergateway — explicit stale-session and child-process failure semantics

Reference:

- repository: `supercorp-ai/supergateway`
- inspected revision family: `bb0be1980f3eabe314c61be4db628c3843c761ad`
- `src/gateways/stdioToStatefulStreamableHttp.ts`

Observed pattern:

- stateful HTTP transports are held in a real `Map` keyed by session id;
- optional idle timeout explicitly closes/reaps sessions;
- an unknown/stale MCP session id receives HTTP 404 so a compliant client creates a fresh session;
- child-process failure first fails outstanding JSON-RPC calls, then closes the transport;
- shutdown owns and drains child processes.

### Decision for coding-tools-mcp

**ADOPT conceptually; no session layer required now.**

Our current server does not depend on a protocol-level MCP session id for the offline-safe feature, which reduces state coupling.

If future compatibility code adds sessionful Streamable HTTP:

- stale session state needs a protocol-correct explicit signal;
- transport teardown must not be used as the only error response for known in-flight requests;
- session timeout must be independent of OAuth/chat lease TTL.

## 5. MCP specification and TypeScript SDK — Origin validation is a current gap

Reference:

- repository: `modelcontextprotocol/modelcontextprotocol`
- revision: `24efd6e7cbd7a074e6b3b781eb370891df40afad`
- `docs/specification/2025-06-18/basic/transports.mdx`
- `docs/specification/2026-07-28/basic/transports/streamable-http.mdx`

Reference implementation:

- repository: `modelcontextprotocol/typescript-sdk`
- revision family: `60321700871029401a2e3bed8fdf4f02c9ec3331`
- Origin/Host validation middleware under `packages/server` and `packages/middleware/*`

The 2025-06-18 Streamable HTTP specification requires servers to validate the `Origin` header to prevent DNS rebinding.

The current TypeScript SDK implements the practical compatibility rule:

- no `Origin` header: allow, because non-browser MCP clients commonly omit it;
- present and allowed Origin: allow;
- malformed, opaque `null`, or non-allowlisted Origin: reject with HTTP 403;
- localhost-class hosting also uses Host validation, with explicit allowlists required for non-localhost exposure.

### Current repository observation

`src-tauri/src/mcp/listener.rs` currently:

- binds only to `127.0.0.1` — good;
- exposes the listener through FRP/Cloudflare — expected;
- installs `CorsLayer::permissive()`;
- does not explicitly validate a present `Origin` header before MCP/OAuth routes.

This is an adjacent security-hardening gap, independent of the reconnect bug.

### Decision

**OPEN FOLLOW-UP ISSUE.**

Do not silently change this on the already accepted Round 5 candidate.

Use failure-first tests and focused impact analysis, then add an Origin validation guard compatible with:

- non-browser clients that send no Origin;
- local localhost Origins;
- the configured public Origin used through the tunnel;
- OAuth callback/control routes;
- FRP/Cloudflare reverse-proxy requests.

Host-header validation requires separate design because the loopback listener may receive a public tunnel Host value. Do not blindly copy a localhost-only Host allowlist.

## 6. MCP 2026-07-28 — protocol-level session reduction

Reference:

- `modelcontextprotocol/modelcontextprotocol`
- `docs/specification/2026-07-28/basic/transports/streamable-http.mdx`
- 2026-07-28 changelog

Observed direction:

- protocol-level Streamable HTTP sessions are removed;
- GET stream endpoint is removed;
- SSE resumability/message redelivery is removed;
- a broken response stream loses the in-flight request rather than implying transparent continuation;
- each client JSON-RPC message is sent as a new HTTP POST;
- standardized MCP HTTP metadata expands.

### Decision for coding-tools-mcp

**DEFER protocol upgrade until real-host compatibility is known.**

This direction fits our architecture because it reduces transport-session coupling and favors explicit application-level state.

However, changing the advertised protocol from `2025-06-18` now would combine an interoperability migration with the still-unverified ChatGPT reconnect fix.

Keep:

```text
protocolVersion = 2025-06-18
```

until a dedicated compatibility issue validates the actual ChatGPT host.

## Adopt / defer summary

| Pattern | Source | Decision |
|---|---|---|
| Stable pinned tool/catalog surface while execution is unreachable | Coder | Adopted in Round 3 |
| Lazy live connection/execution check | Coder | Adopted conceptually |
| Explicit persisted connection state | Cloudflare Agents | Future Level B/C |
| Do not unsafe-resume unknown in-flight work | Cloudflare Agents | Adopted invariant |
| OAuth refresh single-flight/storm brakes | mcp-remote | Future outbound client/broker |
| Stale-session explicit protocol signal | Supergateway | Future sessionful compatibility only |
| Present Origin allowlist + missing-Origin compatibility | MCP spec / TS SDK | **Immediate follow-up** |
| Host allowlist | MCP TS SDK | Design separately for tunnel topology |
| 2026-07-28 stateless transport direction | MCP spec | Defer until host compatibility |

## Architectural conclusion

The open-source comparison reinforces the core project design:

```text
stable control plane
+ stable tool identity
+ explicit execution availability
+ fail-closed authorization
+ no unsafe in-flight replay
```

The study does **not** indicate that a cloud broker is currently necessary.

The clearest new actionable item is HTTP Origin hardening. The clearest future architecture signal is that, if Level B/C is later required, connection lifecycle should be explicit and reconstructible rather than inferred from workspace execution state.

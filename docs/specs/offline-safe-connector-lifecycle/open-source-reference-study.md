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


## 7. Official Rust SDK — exact public Origin and default Host defense

Reference:

- repository: `modelcontextprotocol/rust-sdk`
- inspected revision family: `dbd238275534c3a8da4d91b7220655e878216988`
- `crates/rmcp/src/transport/streamable_http_server/tower.rs`

Observed pattern:

- Streamable HTTP config has explicit `allowed_hosts` and `allowed_origins`.
- Default Host policy admits loopback only.
- Origin comparison is defined as RFC 6454 origin equality: scheme + host + effective port.
- Missing Origin can remain compatible.
- Public deployments must explicitly widen the host/origin boundary.
- 2026-07-28 traffic is stateless even when legacy session mode is available.

### Decision

**ADOPT the stronger public-Origin equality rule.**

ISSUE-006 was refined after this review:

- localhost-class browser Origins remain flexible for developer UI ports;
- the managed/public Origin must match scheme + host + effective port;
- same hostname with another scheme/port is rejected.

This is stricter than the earlier hostname-only draft and does not affect normal non-browser ChatGPT/MCP clients that omit Origin.

## 8. mcp-gateway — CORS is not a DNS-rebinding control

Reference:

- repository: `MikkoParkkola/mcp-gateway`
- inspected revision family: `d10e1fc53fc5ef6fc306b0775ee3abc71e206f9a`
- `src/gateway/router/origin_guard.rs`
- `docs/design/origin-validation-anon-admin.md`

Observed pattern:

1. CORS is explicitly treated as insufficient for DNS rebinding defense.
2. Browser Origin is checked as a canonical full origin.
3. Public URL is read live per request rather than snapshotted at listener startup.
4. Host / HTTP2 authority is validated to stop rebound names when Origin is absent.
5. `Sec-Fetch-Site` is checked because browsers can issue navigation/GET requests without Origin.
6. One live public configuration snapshot is used for related checks so a config reload cannot split the security decision across two generations.

### Decision

**ADOPT now:**

- full current public-Origin comparison;
- live `PublicOrigin` lookup per request;
- keep CORS and security validation conceptually separate.

**DEFER to ISSUE-007:**

- tunnel-aware Host / `:authority` validation;
- `Sec-Fetch-Site` policy.

The Host design must account for FRP/Cloudflare forwarding rather than blindly assuming every inbound Host is localhost.

## 9. PMCP / chuk-mcp-rs — reverse-proxy caution and conformance discipline

References:

- `Consiliency/pmcp@1683c515ede0308fec84dc13be4d0428b3e32bdf`
- `IBM/chuk-mcp-rs@c1b874a84c465a492812f26d142f67278a148c31`

PMCP's useful distinction:

- Origin validation is default-on for browser requests.
- Host validation is deliberately topology-sensitive because reverse proxies may forward arbitrary public Host values.
- OAuth audience/canonical resource identity is operator-configured rather than derived from the incoming Host.

chuk-mcp-rs adds a separate lesson:

- Host/Origin hardening is tested as part of HTTP transport behavior;
- protocol-era compatibility is a first-class concern;
- cross-implementation conformance tests are treated separately from application behavior.

### Decision

For coding-tools-mcp:

- never derive OAuth issuer/resource identity from untrusted Host/forwarded-host;
- design Host enforcement only after measuring FRP/Cloudflare forwarding behavior;
- keep the real ChatGPT compatibility gate separate from source/security conformance;
- consider official MCP conformance tooling in a future protocol-upgrade issue, not inside the reconnect fix.

## Updated adopt / defer summary

| Pattern | Source | Decision |
|---|---|---|
| Exact scheme+host+effective-port public Origin | official Rust SDK / mcp-gateway | Adopt in ISSUE-006 |
| Live public URL in security decision | mcp-gateway | Adopt in ISSUE-006 |
| CORS is not DNS-rebinding validation | mcp-gateway | Adopt as invariant |
| Host / HTTP2 authority validation | official Rust SDK / mcp-gateway / PMCP | ISSUE-007, topology-aware |
| `Sec-Fetch-Site` defense | mcp-gateway | ISSUE-007 |
| Canonical OAuth audience independent of request Host | PMCP | Preserve existing invariant |
| Dual protocol-era / conformance discipline | chuk-mcp-rs | Future protocol compatibility issue |


## 10. Microsoft MCP Gateway — what a real Level C would look like

Reference:

- repository: `microsoft/mcp-gateway`
- inspected revision family: `3594c4eee36308ac131aad1c946ea14140b4353d`
- `README.md`

Observed architecture:

- separate data plane for MCP request routing;
- separate control plane for deploy/update/delete lifecycle;
- metadata store independent of individual MCP server processes;
- session-aware routing/affinity;
- multiple router/server instances behind the gateway;
- explicit deployment status/log surfaces;
- enterprise auth/observability as gateway concerns rather than workspace-process concerns.

### Decision

**Do not adopt now; use as a Level C reference architecture only.**

The original reconnect problem does not yet justify Kubernetes, a remote metadata plane, or session-affinity infrastructure.

If real-host validation eventually proves that the connector endpoint must survive desktop-process exit or machine/network loss, Level C should not be implemented as “keep one desktop listener alive harder.” The correct shape would instead resemble:

```text
always-on connector/control endpoint
        |
        +-- durable auth / metadata
        +-- workspace availability state
        +-- route to local/remote worker only when available
```

The server endpoint and workspace worker would become different failure domains.

This reinforces the current sequencing:

1. Level A local control/execution separation first;
2. real-host evidence;
3. only then decide whether Level B local daemon or Level C remote broker is required.



## 11. Inspector UX — transport connection is not the same operator intent as availability

References:

- `MCPJam/inspector@c8501f47c06bde36794a8010e5573d40d0deb43c`
  - `docs/inspector/playground.mdx`
- `modelcontextprotocol/inspector@2e90a628e6296c62e4bef942afbb43d3faa4baf4`
  - `clients/web/README.md`
  - `clients/web/src/hooks/useConnectionLifecycle.ts`

Observed UI/lifecycle patterns:

### MCPJam Inspector

The Playground explicitly distinguishes:

- **connect / disconnect** a server;
- **toggle a server on/off for the current conversation**.

The tool surface can aggregate multiple connected servers while conversation selection is a separate choice. This is a direct product precedent for not forcing a transport disconnect merely because the user does not want that server active for the current work.

### Official MCP Inspector

The Inspector models transport lifecycle explicitly:

```text
disconnected
 -> connecting
 -> connected / error
```

Explicit disconnect is a real session-lifecycle operation and performs session-scoped cleanup. Mid-session transport failure is also a disconnect event, rather than being conflated with tool availability.

### Decision for coding-tools-mcp

**Adopt in ISSUE-008.**

The desktop should expose two different operator intents:

```text
temporary workspace intent
  Pause remote execution
  Resume remote execution

connector infrastructure intent
  Start Connector
  Stop Connector
```

The common running-state action should be Pause/Resume. Hard Stop remains available and explicit because it changes transport reachability, OAuth reachability and tunnel lifetime.

This supports the backend split already implemented in Round 3 and avoids teaching operators that “temporarily stop work” means “disconnect the connector”.


## 12. Authorization work should follow lifecycle state, not merely endpoint reachability

References:

- `cloudflare/agents@c076e4c9ff6cfb72931085226edfd3ee7965ac48`
  - `packages/agents/src/mcp/client/connection.ts`
- `MCPJam/inspector@c8501f47c06bde36794a8010e5573d40d0deb43c`
  - `docs/inspector/playground.mdx`
- `coder/coder@9661661ba6d1008eb1f75f5a8933c8101001e0b3`
  - `coderd/x/chatd/chatd.go`

### Cloudflare Agents

The MCP client has an explicit connection state machine:

```text
AUTHENTICATING
CONNECTING
CONNECTED
DISCOVERING
READY
FAILED
```

A 401 is treated specially: authentication work is represented by the `AUTHENTICATING` state and the transport that produced the challenge is retained so the OAuth continuation is completed against the correct resource metadata.

Useful principle for this project:

> human authorization is lifecycle state with explicit entry conditions; it should not be spawned merely because an endpoint is reachable.

### MCPJam Inspector

The Playground distinguishes a connected server from whether that server is enabled for the current conversation. The tool surface can stay connected while conversation-level participation changes.

Useful principle:

> installed/reachable does not imply every conversation should initiate new authorization work.

### Coder

Chat execution distinguishes workspace-agent availability from chat authorization. A stopped/disconnected workspace produces an execution/connectivity condition rather than mutating authorization state.

Useful principle:

> execution unavailability should not create new approval work as a side effect.

### Decision for coding-tools-mcp

**ADOPT in ISSUE-009 with a narrower local rule.**

When local execution is intentionally Offline:

- existing active/pending chat authorization remains observable and stable;
- existing exclusive/recovery denials keep precedence;
- an unapproved conversation cannot create a new pending approval;
- the denial is generic and non-disclosing;
- OAuth refresh and connector reachability remain unchanged.

Resume re-enables normal authorization requests.

This keeps three concerns separate:

```text
connector reachability
chat authorization
workspace execution availability
```

and prevents a paused workspace from generating fresh local approval noise solely because an unrelated conversation probes the installed connector.


## 13. Cloudflare Tunnel and FRP — Host forwarding is configurable, so ISSUE-007 must measure the deployed mode

References:

- `cloudflare/cloudflared@be3ac1270217f6ad257f9232052abefbf71835c2`
  - `ingress/origin_proxy.go`
  - `ingress/origin_service.go`
- `fatedier/frp@d20a232996007dfe6ab425abc0a39a3ae9a0889b`
  - `server/proxy/http.go`
  - `pkg/util/vhost/http.go`

### cloudflared

The local HTTP origin proxy rewrites the request URL to the configured local origin, but it rewrites `Request.Host` **only when** `originRequest.httpHostHeader` is configured.

When that override is configured, cloudflared:

1. copies the incoming Host into `X-Forwarded-Host`;
2. sets the origin-facing `Request.Host` to the configured `httpHostHeader`.

Therefore “Cloudflare Tunnel always preserves the public Host” is not a safe invariant. It depends on the deployed `httpHostHeader` setting.

For ISSUE-007 this also reinforces an existing security decision:

> `X-Forwarded-Host` may be useful diagnostics, but must not become an authorization source.

### FRP

FRP's HTTP proxy carries `HostHeaderRewrite` into the vhost route as `RewriteHost`.

In the reverse-proxy rewrite path:

- when `RewriteHost` is non-empty, FRP sets `req.Host` to that configured value;
- otherwise it leaves the incoming request Host intact while changing the internal URL host used for backend routing/connection reuse.

Therefore FRP can also operate in either:

```text
public Host preserved
or
configured Host rewritten
```

mode.

### Decision for coding-tools-mcp

**Do not enforce Host/:authority from assumptions.**

ISSUE-007's topology probe is mandatory because both supported tunnel families have explicit Host-rewrite controls.

The probe should classify the effective listener-facing target into one of these forms:

```text
direct loopback Host
current public Host
operator-configured rewritten Host
other / unsupported
```

Then enforcement can be derived from the actual supported configuration rather than from tunnel brand.

The source review narrows the likely design:

- direct localhost: allow loopback authority;
- tunnel with preserved Host: allow exact current managed public host;
- tunnel with an intentional configured rewrite: allow only that known local/operator-derived target if the application itself owns that setting;
- never accept arbitrary `Forwarded` / `X-Forwarded-Host` as proof of identity.

This remains a pre-implementation finding. Real project tunnel-mode observations are still required before ISSUE-007 code changes.


### Current project tunnel configuration implication

The current coding-tools-mcp tunnel builders narrow the expected topology further:

- Quick Tunnel launches `cloudflared tunnel --url http://127.0.0.1:<port>` and does not set `--http-host-header` / `TUNNEL_HTTP_HOST_HEADER`.
- The generated FRP TOML defines HTTP/HTTPS route/domain/local-target settings but does not emit `hostHeaderRewrite`.

Combined with the upstream implementations above, the default application-generated routes are expected to preserve the incoming/public Host at the local listener.

That is still a **source-derived expectation, not runtime proof**:

- named Cloudflare tunnels may have remotely managed ingress/origin-request settings not visible in the local command line;
- an independently managed FRP server/client configuration can differ from this application's generated TOML;
- HTTP/2 authority representation at Axum/hyper still needs observation.

ISSUE-007 should therefore use this finding to make the probe smaller, not to skip it.


## 13. MCP OAuth challenge semantics — keep local approval suppression out of HTTP auth

References:

- `modelcontextprotocol/modelcontextprotocol@24efd6e7cbd7a074e6b3b781eb370891df40afad`
  - 2025-06-18 authorization specification;
  - protected-resource metadata / RFC 9728 alignment;
  - Inspector authorization documentation.
- `modelcontextprotocol/typescript-sdk@60321700871029401a2e3bed8fdf4f02c9ec3331`
  - resource-server bearer-auth middleware;
  - authorization documentation.

Observed protocol boundary:

- missing, malformed, expired or otherwise invalid bearer credentials use HTTP `401` and may carry a `WWW-Authenticate` challenge;
- OAuth scope step-up uses HTTP `403 insufficient_scope` with `WWW-Authenticate`;
- those HTTP challenge responses are specifically what tells an MCP client to enter/re-enter OAuth authorization.

### Decision for coding-tools-mcp

**Preserve the distinction already used by ISSUE-003/009.**

`CHAT_AUTHORIZATION_UNAVAILABLE` is a local desktop/conversation admission condition, not an OAuth credential defect and not an OAuth scope step-up.

Therefore it must remain:

```text
HTTP/MCP transport: healthy
OAuth bearer identity: valid
MCP tool result: isError=true
structured error: CHAT_AUTHORIZATION_UNAVAILABLE
WWW-Authenticate: absent
```

Do not encode the paused local-approval condition as HTTP 401/403 with an OAuth challenge. Doing so would invite exactly the wrong host behavior: re-login / reconnect for a credential that is still valid.

This open-source/spec comparison strengthens the project's existing three-way separation:

```text
OAuth authentication
conversation/local approval
workspace execution availability
```


## 14. MCPMate — enable/disable profiles without restarting the local core

Reference:

- `loocor/MCPMate@dc80b32f64788bf9513ccf241dd19708b25cce87`
- `board/README.md`
- desktop/operator/settings UI strings and audit event definitions.

Observed product architecture:

- a long-lived local core/service is managed separately from profile/server activation;
- profiles choose which servers/tools are active;
- profiles can be enabled/disabled without restarting the service;
- management UI distinguishes local core service start/restart from profile/server enable/disable;
- audit vocabulary separately records core-service lifecycle and profile-server enable/disable operations.

### Decision for coding-tools-mcp

**Confirms the Round 3 + ISSUE-008 product split.**

The useful pattern is not the exact MCPMate process architecture; it is the explicit operator vocabulary:

```text
core / connector lifecycle
    !=
profile / workspace activation
```

For this project:

```text
Start/Stop Connector
    !=
Pause/Resume remote workspace execution
```

This is particularly important in a shared ChatGPT installation: temporarily disabling workspace execution should not imply that the connector identity itself must disappear or restart.

It also supports ISSUE-009's rule that a paused workspace should not create new local approval work: “reachable core” and “currently accepting this profile/conversation” are separate states.


## 15. mcp-hub — dynamic server enablement, health and recovery are separate controls

Reference:

- `ravitemer/mcp-hub@9c7670a4c341ed3cf738a6242c0fde1cea40bccf`
- project README / changelog.

Observed design:

- one hub endpoint fronts multiple MCP servers;
- servers can be started/stopped and enabled/disabled dynamically;
- configuration changes can reconnect affected servers without restarting the whole hub;
- server health is tracked independently from whether it is enabled;
- local STDIO and remote HTTP/SSE servers share the same management model.

### Decision for coding-tools-mcp

This reinforces a recurring pattern across MCPMate, MCPJam and gateway-style projects:

```text
front-door / hub health
server or workspace enabled state
underlying worker health
```

are separate dimensions.

For this project the closest mapping is:

```text
MCP/OAuth connector reachability
workspace execution Online/Offline
local worker/tunnel health
```

The important lesson for ISSUE-009 is that an enabled/reachable front door should not automatically create new authorization work for a workspace that is intentionally unavailable.

Future observability should continue to report these dimensions separately rather than collapsing them into one “connected” boolean.


## 16. MCPJam connection requests — pending human work is explicit and cancelable, not silently rewritten

Reference:

- `MCPJam/inspector@c8501f47c06bde36794a8010e5573d40d0deb43c`
- `mcp/README.md`

Relevant management tools are separated explicitly:

```text
connect_project_server
get_project_server_connection_status
cancel_project_server_connection
diagnose_server
```

When a human must finish authorization in a browser, the connection request is represented as a pending operation that can be observed or explicitly cancelled.

### Decision for coding-tools-mcp

This supports ISSUE-009's choice to suppress only **new** approval allocation while execution is paused.

Do not silently revoke or erase an already-existing pending/active local chat grant merely because execution becomes Offline.

The local lifecycle remains:

```text
existing pending/active authorization
  -> preserved across Pause

new authorization request while Offline
  -> refused without allocation/event

explicit local revoke/deny
  -> changes authorization state
```

That avoids surprising authorization mutation while still preventing a paused workspace from generating fresh approval noise.


## 17. Tunnel Host forwarding — source evidence narrows ISSUE-007 before live probing

References:

- local repository FRP config builder:
  - `src-tauri/src/tunnel/frp/mod.rs`
- local Cloudflare launcher:
  - `src-tauri/src/tunnel/cloudflare.rs`
- `fatedier/frp@d20a232996007dfe6ab425abc0a39a3ae9a0889b`
  - `server/proxy/http.go`
  - `pkg/util/vhost/http.go`
  - `pkg/plugin/client/http_common.go`
- `cloudflare/cloudflared@be3ac1270217f6ad257f9232052abefbf71835c2`
  - `ingress/origin_service.go`
  - `ingress/origin_proxy.go`
  - `config/configuration.go`

### FRP source evidence

The product FRP TOML builder does **not** emit either:

```text
hostHeaderRewrite = ...
plugin.hostHeaderRewrite = ...
```

for ordinary HTTP routes or the `https2http` plugin path.

Upstream FRP behavior is explicit:

- server-side HTTP reverse proxy changes `req.Host` only when `RouteConfig.RewriteHost` is non-empty;
- client HTTP bridge plugins change `req.Host` only when `hostHeaderRewrite` is non-empty.

Therefore, with the configuration generated by this product, FRP source behavior predicts that the original routed Host is preserved to the local listener.

This is strong source evidence, but not a substitute for a real FRP route observation.

### Cloudflare source evidence

The product launches:

```text
quick tunnel:
  cloudflared tunnel ... --url http://127.0.0.1:<port>

named tunnel:
  cloudflared tunnel ... run
```

and does not set an `httpHostHeader` override itself.

Upstream cloudflared changes `Request.Host` only when `OriginRequestConfig.HTTPHostHeader` is non-empty; otherwise it rewrites the origin URL target but leaves the request Host field intact.

For Quick Tunnel, this strongly predicts that the `*.trycloudflare.com` Host reaches the local listener.

For a named tunnel, one additional uncertainty remains: the remotely managed Cloudflare tunnel/ingress configuration can itself define an `httpHostHeader` override. A token-only local launch cannot prove that remote setting is absent.

### ISSUE-007 consequence

The Host/authority problem is now narrower:

| Mode | Source-level expected local Host | Remaining uncertainty |
|---|---|---|
| direct localhost | localhost / 127.0.0.1 | none beyond HTTP parser behavior |
| FRP HTTP | routed public FRP hostname | live deployment confirmation |
| FRP HTTPS + https2http | routed public hostname | live deployment confirmation |
| Cloudflare Quick | current trycloudflare hostname | live deployment confirmation |
| Cloudflare Named | public hostname **unless remote HTTPHostHeader override exists** | remote config / live probe required |

Do not trust `X-Forwarded-Host` to close the remaining uncertainty.

The next safe step for ISSUE-007 is therefore a sanitized runtime topology probe, not speculative Host enforcement.


## 13. OAuth challenge semantics must stay separate from local workspace authorization

References:

- `modelcontextprotocol/modelcontextprotocol@24efd6e7cbd7a074e6b3b781eb370891df40afad`
  - `docs/docs/2026-07-28/tools/inspector/authorization.mdx`
- `modelcontextprotocol/typescript-sdk@60321700871029401a2e3bed8fdf4f02c9ec3331`
  - `docs/serving/authorization.md`

Observed protocol/client behavior:

1. HTTP `401` plus `WWW-Authenticate` starts or restarts the MCP OAuth flow.
2. HTTP `403 insufficient_scope` plus `WWW-Authenticate` starts step-up authorization.
3. The current Inspector handles a mid-session 401/403 by re-authorizing and retrying the refused request without dropping the underlying connection.
4. The TypeScript SDK intentionally formats 401/403 challenges so clients discover protected-resource metadata and enter OAuth/step-up.

### Decision for coding-tools-mcp

**Preserve the Round 3 / ISSUE-009 distinction.**

Local desktop chat approval is **not** OAuth.

Therefore the following server-side states must remain normal MCP tool results over HTTP 200 and must not carry `WWW-Authenticate`:

- `CHAT_AUTHORIZATION_REQUIRED`;
- `EXCLUSIVE_CHAT_LOCKED`;
- `CHAT_WORK_DRAINING`;
- `CHAT_RECOVERY_REQUIRED`;
- `CHAT_AUTHORIZATION_UNAVAILABLE`;
- `WORKSPACE_OFFLINE`.

Only actual bearer-token/authentication failures should use the HTTP OAuth challenge path.

ISSUE-009's HTTP regression explicitly verifies that the paused-workspace suppression response is:

```text
HTTP 200
MCP tool result error
WWW-Authenticate absent
CHAT_AUTHORIZATION_UNAVAILABLE
```

This matters directly to the original reconnect problem: reusing an HTTP OAuth challenge for a local workspace/admission condition would actively tell capable MCP clients to start re-authentication, which is the opposite of the intended offline-safe behavior.


## 14. MCPMate — separate desktop shell, core service, and profile activation

Reference:

- `loocor/MCPMate@dc80b32f64788bf9513ccf241dd19708b25cce87`
- `board/README.md`
- `board/src/pages/settings/i18n/index.ts`

Observed architecture:

1. The management UI is a frontend that talks to a separate local backend service over REST/WebSocket.
2. The product distinguishes the **desktop shell** from the **local core service**.
3. Local runtime mode can be:
   - OS service; or
   - desktop-managed lifecycle.
4. Profiles can be enabled/disabled dynamically **without restarting the service**.
5. The UI separately exposes:
   - profile/server enablement state;
   - core-service start/restart/stop state;
   - backend health/connectivity.
6. The desktop copy explicitly distinguishes:
   - “the local core is running”;
   - “Desktop is managing the local core”;
   - “service manager reports core running but health checks fail”.

### Decision for coding-tools-mcp

This is strong evidence for the same separation already emerging here:

```text
Desktop shell
  != Connector/control service
  != Workspace/profile execution availability
```

Round 3/ISSUE-008 already implement the third distinction inside one process:

- Connector running;
- workspace execution Online/Offline;
- explicit hard Stop Connector.

If eventual real-host testing proves that closing/quitting the desktop process must not remove connector reachability, MCPMate's core-service split is a credible Level B reference:

```text
desktop UI shell
     |
     +-- IPC/HTTP -> local background core
                      |
                      +-- MCP/OAuth control listener
                      +-- tunnel supervisor
                      +-- workspace execution gates
```

This would be preferable to hiding more lifecycle behavior inside the WebView/Tauri window process.

### Important non-decision

**Do not implement Level B yet.**

Current evidence still shows Level A is sufficient to build a coherent engineering candidate, and the user explicitly deferred real ChatGPT host testing.

A background core should be justified by one of these observed requirements:

- app process exit must preserve connector reachability;
- OS login/startup persistence is required;
- multiple desktop shells must attach to one local control plane;
- host tests prove UI-only close/reopen is insufficient.

Until then, keep the Level B idea as an architecture option rather than introducing a new service manager, installer responsibility, and IPC security boundary.


## 15. MCPMate first-contact governance — installed endpoint does not imply automatic approval

Reference:

- `loocor/MCPMate@dc80b32f64788bf9513ccf241dd19708b25cce87`
- `backend/src/core/proxy/server/gateway.rs`
- `backend/src/clients/service/state.rs`
- `board/src/pages/settings/i18n/index.ts`

Observed pattern:

MCPMate treats a previously unknown MCP client as a governance decision with an explicit first-contact policy:

```text
deny   -> suspended
review -> pending
allow  -> approved
```

The policy is enforced during MCP initialization rather than assuming that endpoint reachability implies client approval.

The dashboard exposes this as a deliberate operator setting instead of hiding the state transition inside transport handling.

### Decision for coding-tools-mcp

**Adopt the governance principle, not MCPMate's identity model.**

Our server already has a different security identity:

- OAuth authenticates the remote client;
- `openai/session` binds a conversation;
- local chat authorization grants workspace capability.

ISSUE-009 applies the same first-contact principle to a paused workspace:

```text
connector reachable
+ OAuth valid
+ unknown/unapproved conversation
+ execution intentionally paused

=> do not create a new human approval task
=> return a generic admission denial
=> preserve existing grants and recovery/exclusive state
```

This further supports keeping `CHAT_AUTHORIZATION_UNAVAILABLE` as a local permission/admission result instead of translating it into OAuth or automatically creating a pending approval.

### Possible future operator policy

If shared-account deployments become common, a later issue could expose a workspace-level first-contact mode:

```text
review       current Online behavior
deny-new     never create new remote pending approvals
allow-review only when local UI has explicitly armed an approval window
```

Do not add this policy in ISSUE-009. The current task has a narrower deterministic trigger: suppress only new approvals while execution is intentionally Offline.


## 13. MCPMate first-contact governance — explicit policy before approval state

Reference:

- repository: `loocor/MCPMate`
- inspected revision family: `dc80b32f64788bf9513ccf241dd19708b25cce87`
- `backend/src/clients/models.rs`
- `backend/src/clients/service/state.rs`
- `backend/src/system/settings.rs`
- `backend/src/core/proxy/server/gateway.rs`

Observed pattern:

MCPMate models first-contact governance as a persisted setting rather than inferring it from transport state:

```text
FirstContactBehavior::Deny
FirstContactBehavior::Review
FirstContactBehavior::Allow
```

The behavior is translated into explicit approval state:

```text
deny   -> suspended
review -> pending
allow  -> approved
```

and also maps to a separately named onboarding policy.

Unknown clients are therefore handled by governance rules before normal capability use. Profile enable/disable is likewise separate from the core-service lifecycle.

### Decision for coding-tools-mcp

**Adopt the explicit-governance shape, not automatic approval.**

ISSUE-010 adds:

```text
review
local_window
deny_new
```

but even `review` produces only a local **pending** chat grant. No remote ChatGPT conversation is auto-approved.

`local_window` is intentionally stricter than MCPMate's review mode:

- local desktop action only;
- 90-second lifetime;
- single use;
- in-memory only;
- does not restart connector;
- does not change OAuth;
- does not reveal its state remotely.

This is the preferred shared-account posture because connector installation/reachability and new-human-approval admission become separate controls.


## 13. Persisted-policy evolution needs an explicit downgrade story

Reference:

- `cloudflare/agents@c076e4c9ff6cfb72931085226edfd3ee7965ac48`
- `packages/agents/src/state/index.ts`
- `design/sessions.md`

Observed pattern:

- persisted capability state owns an explicit schema version;
- migrations are scoped to the capability rather than hidden in unrelated runtime state;
- a migration is not stamped complete until source rows have been verified;
- old/recoverable state is either preserved for retry or transformed deliberately rather than silently discarded.

### Decision for coding-tools-mcp

ISSUE-010 adds one persisted admission-policy field but the pre-ISSUE-010 `SessionPolicy` is intentionally strict about unknown fields.

To preserve a bounded downgrade path without adding a new data-schema migration:

- the backward-compatible `review` value is omitted when serialized;
- `local_window` / `deny_new` remain explicit while enabled;
- before installing an older binary, the operator must return every workspace to `review` and save;
- a regression locks that the Review default produces the old serialized shape.

This is not a general schema-versioning replacement. If future authorization policy grows beyond one optional field, move it behind an explicit versioned capability/storage boundary rather than accumulating downgrade rules ad hoc.


## 14. Keep local chat policy denials out of OAuth challenge semantics

References:

- `modelcontextprotocol/modelcontextprotocol@24efd6e7cbd7a074e6b3b781eb370891df40afad`
  - authorization / Protected Resource Metadata guidance
  - Inspector authorization documentation
- `modelcontextprotocol/typescript-sdk@60321700871029401a2e3bed8fdf4f02c9ec3331`
  - resource-server authorization middleware
  - client step-up authorization flow

Observed protocol behavior:

- missing/invalid resource-server bearer credentials use HTTP 401 and may carry `WWW-Authenticate`;
- insufficient OAuth scope uses HTTP 403 `insufficient_scope` and can also carry a `WWW-Authenticate` challenge;
- current Inspector/client implementations can treat those responses as signals to start or repeat OAuth authorization without dropping the underlying connector.

### Decision for coding-tools-mcp

**Preserve the existing separation.**

Local conversation governance is not OAuth scope negotiation.

Therefore all of these remain MCP tool/business results rather than HTTP OAuth challenges:

```text
CHAT_AUTHORIZATION_REQUIRED
CHAT_AUTHORIZATION_UNAVAILABLE
EXCLUSIVE_CHAT_LOCKED
CHAT_WORK_DRAINING
CHAT_RECOVERY_REQUIRED
WORKSPACE_OFFLINE
```

They must not gain `WWW-Authenticate` merely because the host can use that header for reauthorization.

Only actual bearer-token/resource-server failures belong on the OAuth 401/403 path.

This distinction is directly relevant to the original reconnect problem: a local policy or availability denial must not accidentally tell the host that the connector's OAuth relationship needs to be repaired.

# ISSUE-007 — Tunnel-aware Host / authority and Fetch Metadata hardening

Status: SOURCE TOPOLOGY EVIDENCE READY — BLOCKED ON LIVE TUNNEL OBSERVATION  
Source: [open-source-reference-study.md](open-source-reference-study.md)  
Scope: HTTP control-plane hardening after Origin validation

## Motivation

ISSUE-006 closes the present-`Origin` gap required by MCP Streamable HTTP, but browsers can make some navigation/GET requests without an Origin header.

Current open-source MCP gateways therefore commonly add a second boundary:

- validate the request target Host / HTTP2 `:authority`;
- optionally reject browser requests reported as cross-site by `Sec-Fetch-Site`.

This repository cannot copy a localhost-only Host policy blindly because FRP and Cloudflare legitimately proxy a public hostname to the loopback listener.

## Threat model

Potential browser paths after ISSUE-006:

1. DNS rebinding where the browser's request target carries an attacker-controlled hostname.
2. Browser GET/navigation requests that omit Origin.
3. HTTP/2 requests where authority is represented on the URI rather than a classic Host header.
4. Stale public tunnel hostnames after Quick Tunnel replacement.
5. Reverse-proxy topology where a valid public Host must continue to work.

## Reference patterns

### modelcontextprotocol/rust-sdk

Default Streamable HTTP Host allowlist admits only loopback names/addresses. Public deployments explicitly widen it.

### MikkoParkkola/mcp-gateway

- resolves HTTP/2 URI authority before HTTP/1.1 Host;
- compares Host against loopback/current live public host;
- reads one live public URL snapshot per request;
- rejects `Sec-Fetch-Site: cross-site` / `same-site`;
- treats CORS as unrelated to DNS-rebinding security.

### Consiliency/pmcp

Host validation is topology-sensitive and may stay off when a reverse proxy forwards arbitrary public Hosts unless the operator has configured a canonical public origin/audience.

## Repository invariants

Already present:

- listener binds `127.0.0.1`;
- managed `PublicOrigin` is validated before publication;
- OAuth issuer/resource derivation does not trust Host / X-Forwarded-Host while managed identity is pending;
- ISSUE-006 reads current `PublicOrigin` live for Origin checks.

Must preserve:

- FRP/Cloudflare public routes;
- Quick Tunnel live URL replacement;
- local development;
- non-browser MCP clients;
- OAuth discovery/token behavior;
- offline-safe pause/resume semantics.

## Source topology evidence

ISSUE-006 is merged, and source review has narrowed the remaining Host-forwarding uncertainty without claiming live deployment evidence.

### Product FRP configuration

`src-tauri/src/tunnel/frp/mod.rs` does not emit either:

```text
hostHeaderRewrite
plugin.hostHeaderRewrite
```

for normal HTTP routes or the `https2http` plugin path.

Upstream FRP `d20a232996007dfe6ab425abc0a39a3ae9a0889b` confirms:

- the server HTTP reverse proxy modifies `req.Host` only when `RouteConfig.RewriteHost` is non-empty;
- the client HTTP bridge plugins modify `req.Host` only when `hostHeaderRewrite` is non-empty.

Source-level expectation:

```text
FRP HTTP/subdomain/custom-domain
  -> local listener sees the routed public Host

FRP HTTPS + https2http
  -> local listener sees the routed public Host
```

Live confirmation is still required.

### Product Cloudflare configuration

`src-tauri/src/tunnel/cloudflare.rs` launches:

```text
Quick:
  cloudflared tunnel --url http://127.0.0.1:<port>

Named:
  cloudflared tunnel run
```

The local launcher does not configure `httpHostHeader`.

Upstream cloudflared `be3ac1270217f6ad257f9232052abefbf71835c2` confirms `Request.Host` is rewritten only when `OriginRequestConfig.HTTPHostHeader` is non-empty.

Source-level expectation:

```text
Quick Tunnel
  -> local listener sees current *.trycloudflare.com Host

Named Tunnel
  -> local listener sees public Host unless remote tunnel ingress config
     explicitly sets httpHostHeader
```

The named-tunnel remote configuration is the important unresolved case: a token-only local launch cannot prove the account-side setting is absent.

### Updated topology table

| Mode | Source-level expected target | Live uncertainty |
|---|---|---|
| direct localhost | localhost / 127.0.0.1 | parser/runtime confirmation only |
| FRP HTTP | routed public FRP host | live route confirmation |
| FRP HTTPS + https2http | routed public host | live route confirmation |
| Cloudflare Quick | current trycloudflare host | live route confirmation |
| Cloudflare Named | public host unless remote `httpHostHeader` override | remote config / live observation |

This is enough to design a sanitized probe, but not enough to enforce Host in production yet.

## Required topology probe before implementation

Do not edit production Host logic until synthetic/integration evidence records what each tunnel mode forwards.

For each supported tunnel path:

```text
FRP fixed domain
FRP subdomain
Cloudflare named tunnel
Cloudflare Quick Tunnel
direct localhost
```

record sanitized:

- request HTTP version;
- URI authority as seen by Axum/hyper;
- Host header hostname only;
- whether Host equals current public-origin host;
- whether any trusted proxy rewrites Host;
- whether `X-Forwarded-Host` is present.

Do not record query strings, authorization headers, cookies, session bindings or workspace paths.

## Proposed Host policy

Only after the probe confirms topology.

Candidate allowlist:

```text
localhost
127.0.0.1
::1
current PublicOrigin hostname
```

Rules:

1. Resolve target from HTTP/2 URI authority first, HTTP/1.1 Host second.
2. Missing/unparseable target fails closed only when the underlying HTTP stack can actually deliver such a request.
3. Loopback names/addresses pass.
4. Current public hostname passes.
5. Stale previous managed public hostname fails.
6. Never trust `X-Forwarded-Host` or `Forwarded` as an authorization source.
7. Do not use incoming Host to construct OAuth issuer/resource identity.
8. Compare normalized hostname/authority according to actual proxy behavior measured above.

If a supported proxy rewrites Host to loopback, public hostname validation must not be invented from forwarded headers; instead document and validate the loopback target plus existing `PublicOrigin` identity separately.

## Fetch Metadata policy

Candidate:

```text
Sec-Fetch-Site absent       -> allow (non-browser / older clients)
same-origin                 -> allow
none                        -> allow (user navigation)
cross-site                  -> 403
same-site                   -> 403 by default
invalid/unreadable          -> 403
```

The exact `same-site` decision needs route-specific review. Do not add it without tests showing legitimate OAuth/browser flows remain functional.

## Failure-first matrix

| Case | Target Host/authority | Sec-Fetch-Site | Expected |
|---|---|---|---|
| H1 | localhost | absent | allow |
| H2 | current public host | absent | allow |
| H3 | stale public host | absent | 403 |
| H4 | attacker name -> loopback | absent | 403 |
| H5 | current public host via HTTP/2 authority | absent | allow |
| H6 | attacker authority via HTTP/2 | absent | 403 |
| H7 | current public host | same-origin | allow |
| H8 | current public host | none | allow |
| H9 | current public host | cross-site | 403 |
| H10 | current public host | invalid UTF-8/value | 403 |
| H11 | direct non-browser request | header absent | preserve MCP/OAuth behavior |
| H12 | each supported tunnel mode | observed real forwarded target | allow exactly measured legitimate target |

## Error contract

Rejected target/fetch metadata should use the same generic non-disclosing HTTP 403 family as ISSUE-006.

Do not echo:

- Host;
- authority;
- Sec-Fetch-Site;
- public tunnel host;
- workspace id/path;
- OAuth client/principal.

## Impact gate

Before production changes, run GitNexus impact for:

- listener `serve`;
- ISSUE-006 security middleware;
- `PublicOrigin::snapshot`;
- tunnel route publication/synchronization;
- FRP route generation;
- Cloudflare route discovery/publication.

Treat lower-bound/UNKNOWN as uncertainty, not safety.

## Acceptance

SOURCE PASS requires:

- tunnel topology probe recorded;
- H1-H12 deterministic coverage;
- existing Origin matrix remains green;
- OAuth/offline/privacy suites remain green;
- Windows + Ubuntu full regression green;
- packaged smoke remains green;
- no public identity is derived from attacker-controlled forwarding headers.

HOST VALIDATED remains separate and still requires the deferred real ChatGPT environment.

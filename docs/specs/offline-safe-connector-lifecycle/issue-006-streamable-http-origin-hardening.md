# ISSUE-006 — Streamable HTTP Origin boundary hardening

Status: OPEN — FAILURE-FIRST DESIGN READY  
Source: [open-source-reference-study.md](open-source-reference-study.md)  
Scope: post-Round-5 security follow-up  
Protocol advertised by product: `2025-06-18`

## Problem

The MCP listener binds to `127.0.0.1`, but is intentionally exposed through FRP/Cloudflare.

Current router setup uses:

```text
CorsLayer::permissive()
```

and does not explicitly validate a present HTTP `Origin` header before the MCP/OAuth routes.

The MCP 2025-06-18 Streamable HTTP specification requires Origin validation to mitigate DNS rebinding.

The current MCP TypeScript SDK uses a compatibility-friendly policy:

- missing Origin passes for non-browser MCP clients;
- present allowed hostname passes;
- malformed / opaque `null` / non-allowlisted Origin fails closed with HTTP 403.

## Security objective

Add an Origin boundary without breaking:

- server-to-server clients that omit Origin;
- localhost development;
- configured fixed public tunnel origins;
- dynamic managed public origins such as Quick Tunnel URLs;
- OAuth discovery / authorize / token endpoints;
- the offline-safe control-plane lifecycle.

## Important repository-specific constraint

`PublicOrigin` is a live shared handle.

A managed Quick Tunnel may start with an empty identity and publish the public Origin later. Therefore the Origin allowlist must read the current `PublicOrigin::snapshot()` per request or otherwise observe publication updates.

Do not capture one static public hostname when the listener starts.

## Failure-first matrix

| Case | Origin header | Public origin state | Expected |
|---|---|---|---|
| O1 | absent | any | allow |
| O2 | `http://localhost:<any>` | any | allow |
| O3 | `http://127.0.0.1:<any>` | any | allow |
| O4 | exact current configured public Origin | published | allow |
| O4b | same public hostname, wrong scheme/port | published | 403 |
| O5 | stale previous Quick Tunnel Origin | replaced/cleared | 403 |
| O6 | attacker hostname | any | 403 |
| O7 | malformed Origin | any | 403 |
| O8 | literal `null` | any | 403 |
| O9 | current public hostname after live `publish()` | changed after listener start | allow without listener restart |
| O10 | missing Origin OAuth token request | any | preserve existing OAuth behavior |
| O11 | invalid Origin OAuth token request | any | 403 before token processing |
| O12 | missing Origin MCP POST | any | preserve current ChatGPT/server-client compatibility |

## Allowlist semantics

The implementation uses two compatibility classes:

```text
localhost / 127.0.0.1 / ::1
  -> allow HTTP(S) browser Origin on any local UI port

current managed PublicOrigin
  -> require exact RFC-6454-style scheme + hostname + effective port
```

This was tightened after reviewing the official Rust SDK and another Rust MCP gateway. A public hostname alone is not enough: `http://mcp.example`, `https://mcp.example`, and `https://mcp.example:8443` are different browser origins.

The public value is read from the live `PublicOrigin` handle per request so a managed Quick Tunnel rotation does not require listener restart.

Do not trust:

- incoming `Host`;
- `X-Forwarded-Host`;
- `Forwarded`;

as sources of the Origin allowlist.

## Response contract

For a rejected present Origin:

```text
HTTP 403
Content-Type: application/json
Cache-Control: no-store
```

Body should be generic and non-disclosing:

```json
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": -32000,
    "message": "Invalid Origin"
  }
}
```

Do not echo the attacker Origin, workspace id, public tunnel hostname, or local path.

## Route coverage

Apply the same guard before:

- `/mcp` GET/POST;
- OAuth authorization-server discovery;
- OAuth protected-resource discovery;
- `/oauth/authorize`;
- `/oauth/token`.

A partial MCP-only fix still leaves the local OAuth control plane browser-reachable.

## CORS interaction

`CorsLayer::permissive()` must not be mistaken for security validation.

After Origin validation is added, review whether permissive CORS remains necessary for actual browser tooling. Do not remove or tighten CORS in the same first fix unless a failing test proves it is required; keep blast radius bounded.

## Host-header validation

The MCP reference SDK also protects localhost deployments with Host validation.

This repository has a reverse-tunnel topology where the loopback listener may legitimately receive the public tunnel Host value.

Therefore Host validation is a **separate design item**:

- inventory actual FRP/Cloudflare Host behavior;
- never derive the public identity from an untrusted Host;
- decide whether valid Host is localhost + current public-origin host;
- validate through tunnel-specific synthetic/integration tests before enforcing.

Do not bundle Host validation into the first Origin patch.

## Protocol 2026-07-28

Do not upgrade protocol revision in this issue.

The newer protocol removes protocol-level Streamable HTTP sessions and SSE resumability, which is directionally compatible with this project, but real ChatGPT compatibility is still unverified.

Origin hardening is required independently and can be implemented while preserving `2025-06-18`.

## Mandatory impact analysis

Before production edit, run focused GitNexus impact for at least:

- MCP listener `serve`;
- `mcp_post`;
- OAuth route handlers;
- `PublicOrigin::snapshot`;
- router construction / middleware insertion point.

If GitNexus has lower-bound/UNKNOWN results, preserve them and complement with source/text review.

## Failure-first evidence

Pre-fix validation run `35513270637`, source `9eafdce08395ee1e987d90dc34d7fd5f92500ea0`: **FAIL as expected**.

The test suite compiled successfully and then demonstrated the actual behavior gap:

- missing/local Origin baseline: PASS;
- `https://attacker.example` on `/mcp`: observed HTTP 200, expected 403;
- attacker Origin on OAuth authorization-server metadata: observed HTTP 200, expected 403;
- stale managed public Origin after live publication: observed HTTP 200, expected 403.

Result:

```text
4 tests
1 passed
3 failed
```

This is a protocol/security behavior failure, not a test-compilation or environment failure.

Repair candidate begins at `ab89f652ba5c63c766c63a8c86a82007e60059fc`.

## Repair iteration 1

Repair candidate `ab89f652ba5c63c766c63a8c86a82007e60059fc` changed one production surface: the listener router now applies a live Origin guard before MCP/OAuth handlers.

Validation run `35513449933`:

- missing/local Origin compatibility: PASS;
- live managed public-origin replacement: PASS;
- OAuth control-plane guard: PASS;
- invalid-origin rejection behavior: production behavior PASS, but one test assertion failed.

The remaining test failure was not a product regression. The test searched the encoded JSON body for the literal attacker input `null`; a valid JSON-RPC rejection necessarily contains `"id": null`, so the sentinel collided with protocol syntax.

The assertion was corrected to validate the generic JSON error shape and check non-reflection only for attacker-controlled host/text values.

This failure remains recorded rather than being rewritten as PASS.

## Focused impact evidence

GitNexus workflow run `35513186585`: PASS as tooling execution.

Before any production edit:

- listener `serve`: **CRITICAL**, exact — 22 impacted symbols, 9 affected processes, 5 modules;
- `PublicOrigin::snapshot`: **CRITICAL**, lower-bound — 27 impacted symbols, 7 affected processes, 5 modules, with 2 receiver-typing call sites dropped;
- `mcp_post`: UNKNOWN/exact because router registration is not represented as a caller edge;
- OAuth authorize/token handlers: UNKNOWN/exact for the same router-registration boundary.

The UNKNOWN handler results are not interpreted as unused/safe. Source review confirms they are directly registered on the Axum router.

Because `serve` and `PublicOrigin::snapshot` are CRITICAL, the implementation must remain one bounded listener middleware change and reuse the existing live `PublicOrigin` handle rather than changing its public contract.

## Focused repair verification

Targeted validation run `35513687278`, source `625d8b59b101a6f4c2e0bc9d3f27df6e9ecf9917`: **PASS**.

```text
origin_security_tests
4 passed
0 failed
```

The four HTTP-level tests collectively cover O1–O12 plus additional duplicate-Origin and invalid CORS-preflight cases:

- missing Origin compatibility;
- localhost / 127.0.0.1 compatibility;
- current public Origin and live public-origin replacement;
- stale public Origin rejection;
- foreign/malformed/opaque Origin rejection;
- generic non-reflective 403 JSON-RPC shape;
- MCP GET/POST;
- OAuth authorization metadata / protected-resource metadata / authorize GET+POST / token POST;
- invalid preflight rejected before permissive CORS;
- repeated Origin headers rejected.

Cross-platform full regression remains the next gate.

## Acceptance

SOURCE PASS requires:

- O1–O12 plus O4b deterministic tests;
- existing OAuth/refresh/chat/offline tests stay green;
- no public-origin update requires listener restart;
- invalid Origin gets 403 before auth/business processing;
- missing Origin remains compatible;
- no attacker-controlled Origin is logged or reflected;
- focused impact and final `detect-changes` recorded;
- Windows and Ubuntu regression green.

HOST PASS is separate and requires eventual real ChatGPT validation that the host's normal requests are not rejected.

Until then, this issue can be source-complete without changing the project's existing `UNCONFIRMED_ON_REAL_HOST` truth label.

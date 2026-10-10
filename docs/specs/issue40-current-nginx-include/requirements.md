# Requirements: current existing-vhost Nginx include

## 功能概述 / Overview

Issue40 needs a reviewable include matching the currently implemented gateway. Baseline F is `310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`. Historical `render.py` emits `/agent/connect` and remains a NOT_DEPLOYABLE round-2 artifact; current `runtime_topology.py` emits `/agent` inside a whole private Nginx configuration. Neither is the requested current existing-vhost include.

## Scope

In scope: a separate offline renderer, source compatibility binding, pure and real private Nginx tests, exact Compose2.27 checks, actual current Gateway/PostgreSQL proof through the new include, and bounded operator documentation.

Out of scope: modifying any existing source or auth/runtime contract; real VPS/DNS/TLS/WAF/443/system-service actions; production credentials; deployment, main/release integration, tag/publication; PR98 and Issue86/snapshot work. All production readiness flags remain false.

## 需求列表 / Functional requirements

### FR-1: Offline exclusive output (Must)

As an operator, I want review-only files without affecting a host.

1. WHEN explicitly invoked with a canonical DNS name, canonical nonzero connector UUID and unprivileged upstream port, the renderer SHALL exclusively create a new private output directory and three review files
2. IF inputs or source compatibility are invalid, or the output exists/is linked, the renderer SHALL fail without overwriting prior files or executing any external command/network request

### FR-2: Existing-vhost and source contract (Must)

1. WHEN rendering, the renderer SHALL emit exactly five locations: a Host-guarded slashless `/coding-tools` returning404, the two current exact OAuth discovery locations, `location ^~ /coding-tools/`, and exact `/coding-tools/agent`; proxy locations use loopback with no URI suffix
2. IF any pinned current route/protocol/identity/MCP source bytes or unique expected shapes drift or are ambiguous, rendering SHALL fail closed before output
3. The output SHALL contain no global/server/listen/TLS/WAF/root-site/reload directive and SHALL include source-file and rendered-include SHA256 binding, without claiming authenticated Git provenance

### FR-3: Original authority and protocol forwarding (Must)

1. WHEN a syntactically accepted request reaches any included route with a Host other than the configured exact canonical authority, it SHALL reject with 421 before proxying, regardless of forged forwarded headers
2. WHEN accepted, the include SHALL retain original Host, clear untrusted forwarded authority/client values and natively preserve the required OAuth/MCP end-to-end request headers, including parser-accepted duplicates/empty values, and body without `$http_*` reconstruction
3. WHEN the exact current agent route is requested, only that location SHALL forward hop-by-hop Upgrade/Connection and natively pass unmodified end-to-end Sec-WebSocket-Protocol, preserving duplicates/empty values;  generic/discovery/historical/near-miss paths SHALL not forward upgrade capability
4. Duplicate Authorization/Host SHALL be rejected by the Nginx parser400; mechanics tests SHALL prove zero upstream hits, while actual service tests SHALL not misattribute that rejection to gateway403. Single empty Authorization on agent, plus duplicate/empty Origin and MCP values, remain native forwarding/runtime rejection cases. Runtime auth/subprotocol validation SHALL remain unchanged; buffering, cache, interception and redirect SHALL stay disabled with bounded body/time limits and scoped access logging disabled

### FR-4: Real private Nginx and Compose2.27 proof (Must)

1. WHEN the mechanics harness runs, actual Nginx SHALL parse and serve an include file on ephemeral loopback using only its owned foreground process and private configuration
2. Root, unrelated prefix and unrelated regex sentinels SHALL retain identical behavior before, during and after include removal; actual raw-header requests SHALL verify duplicate/empty/header/body/status forwarding, Host rejection, generic upgrade suppression and protection against a broad existing regex shadowing the namespace
3. Actual Compose SHALL report exactly 2.27.0 and normalize both unchanged historical/current topologies using config-only operations while retaining their loopback/private-DB/nonroot contracts
4. Echo tests SHALL be labeled mechanics-only, never authenticated service proof

### FR-5: Actual current service and source-bound CI (Must)

1. WHEN the hosted native job runs, it SHALL build locked exact-source gateway binaries, use a fresh owned disposable Gateway/Nginx/PostgreSQL fixture and the exact emitted include, and prove actual OAuth PKCE/MCP and current agent 101/subprotocol negative behavior
2. Root/unrelated prefix/regex sentinel, wrong Host, unsupported MCP version/mirror, wrong/duplicate valid+invalid/empty+valid subprotocol, empty forbidden agent Origin/Cookie/Authorization, duplicate MCP headers and nonupgrade historical path tests SHALL pass without changing runtime gates
3. Evidence SHALL bind source SHA/tree/run/attempt, actual versions/digests and finite case inventory; fixture secrets SHALL remain private and SHALL not be uploaded
4. A 101 SHALL be described only as a pending unauthenticated WebSocket; all production/TLS/WAF/publication flags SHALL remain false

## 非功能需求 / Nonfunctional requirements

- NFR-1: Every new Python file <=500 lines; explicit subprocess/readiness/network bounds and owned cleanup
- NFR-2: No real credentials, arbitrary forwarded trust, persistent authorization or host-global changes; no sensitive request/body/query logs in reports
- NFR-3: Python3.12 and Rust1.98.1 workflow tools; exact Compose2.27; private current native Nginx syntax rather than assuming newer schema compatibility
- NFR-4: Nine new paths only, zero existing tracked changes; independent design and candidate review plus precommit graph impact

## 依赖关系 / Dependencies and acceptance limits

Reuse existing pure validation/topology and hosted Fixture helpers. Existing 42 deployment tests must stay green. Native mechanics and actual service jobs must both pass on the reviewed source; local pure tests alone do not satisfy FR-4/FR-5. Issue40 stays open for live host/security/rollback acceptance. EOL CentOS is still a production blocker.

## Routing and topology limits

Only the reviewed single-hop wrapper is proved. Nginx normalizes location selection; raw-URI tests record both destination and retained upstream URI. Existing exact/longer/nested locations or server rewrites/internal redirects can conflict. Hop-by-hop Upgrade/Connection normalization is intentional; original client duplicates for those fields are not claimed preserved. The old runtime ingress two-hop composition remains unsupported because it still reconstructs end-to-end headers. Renderer upstream port, private Nginx listener and fixture published port have distinct meanings. No namespace-local gateway port is assumed reachable from the host. Operator must first review a gateway endpoint reachable in the actual Nginx namespace; existing topology published old-ingress port is not suitable by default. Known same-namespace fixture listener/upstream port equality SHALL be rejected before process launch, with explicit self-proxy negative tests. Owned process/project cleanup failure prevents PASS.

## Checklist

- [x] Requirements have unique IDs, Must priorities and testable triggers/results
- [x] Historical facts and current source are explicitly separated
- [x] Scope, security, compatibility, limits and dependencies are explicit
- [x] Independent preimplementation review accepted
- [ ] Current-source native acceptance verified

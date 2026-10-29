# Design: current existing-vhost Nginx include

## 概述 / Overview

Covers FR-1 through FR-5 and NFR-1 through NFR-4. Baseline F: `310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`.

## 技术方案 / Architecture and decisions

Explicit offline CLI -> source compatibility check -> current five-location include + source manifest. Two independent harnesses consume the emitted include: private Nginx/echo for byte/header mechanics, and freshly built real Gateway/Nginx/PostgreSQL for runtime proof. No existing implementation or workflow changes. Fifth block is exact `/coding-tools`: reject foreign Host421, otherwise return404, no redirect or proxy. This prevents implicit slash301. Existing root and adjacent application namespaces are untouched.

Historical `render.py` stays untouched. It is evidence from its own round, not a current route generator. `runtime_topology.py` stays untouched because its complete private server is a different product from a server-context include (FR-2).

The include uses original `$http_host` equality against canonical DNS before forwarding `Host $http_host`. Uppercase, explicit :443, trailing-dot, missing and foreign authorities are rejected deliberately; no identity normalization or arbitrary Forwarded/X-Forwarded-* trust (FR-3). This matches the current exact gateway authority contract.

The exact agent location alone explicitly forwards hop-by-hop Upgrade and Connection upgrade; its end-to-end Sec-WebSocket-Protocol passes natively with no proxy_set_header redefinition. Generic and discovery blocks clear all three. Duplicates and empty forbidden fields must survive to the unchanged gateway rejection gates. Hop-by-hop Upgrade/Connection normalization is deliberate and does not preserve original client duplicate-count semantics. The gateway remains the authority for subprotocol, query and authentication rejection of its actual upstream request; successful 101 is not authenticated agent acceptance (FR-3/FR-5).

## Interfaces and data

- `source_contract(root)`: read bounded regular nonsymlink current channel/transport.rs, channel/protocol.rs, config.rs, mcp/http.rs and mcp/protocol.rs; require exact whole-file SHA256 pinned to F before unique expected route/discovery/subprotocol shape checks; missing/ambiguous/any changed bytes refuse output. Return source SHA256 mapping; drift is an error, never heuristic auto-adaptation
- `locations(domain, connector, port)`: validate through existing pure validator and emit exactly five location blocks; no side effects
- `render(output, domain, connector, port)`: validate everything first, create a 0700 new directory, exclusive 0600 `nginx-locations.current.review.conf`, `source-contract.json`, `REVIEW_ONLY.txt`; no overwrite
- Manifest: schema version, route/subprotocol/domain/connector/port, actual source hashes and include hash; `applied=false`, `production_ready=false`, `real_host_tls_waf_tested=false`, `publish_approved=false`
- CI independently records authenticated source SHA/tree/run/attempt and hashes of relevant artifact bytes; manifest metadata by itself is not provenance

Explicit Host override retains accepted original `$http_host`. `proxy_pass_request_headers on` preserves Authorization, Origin, Cookie, Accept, Content-Type, MCP-Protocol-Version, Mcp-Session-Id, Mcp-Method, Mcp-Name and Last-Event-ID natively, including duplicates and empty values accepted by Nginx's parser. Duplicate Authorization/Host are parser-rejected400, not forwarding cases. Do not redefine those end-to-end headers using proxy_set_header/$http_* variables: collapsing duplicates or removing empty fields can bypass current runtime rejection. Sec-WebSocket-Protocol is also unmodified on the exact agent route. Strip Forwarded, X-Forwarded-Host/For and X-Real-IP; fixed X-Forwarded-Proto https is not used for identity. Preserve URI/body and response status/protocol headers. Disable buffering/request buffering/cache/interception/redirect; 64k body cap, 3s connect/75s read/30s send, 10s body deadline; scoped access_log off (FR-3).

## 文件结构 / Exact nine new paths

1. `deploy/cloud-gateway/current_nginx_include.py` <=300 lines
2. `tests/cloud-gateway-deployment/test_current_nginx_include.py` <=450
3. `tests/cloud-gateway-deployment/run_current_nginx_checks.py` <=400
4. `tests/cloud-gateway-deployment/run_current_nginx_runtime.py` <=400
5. `.github/workflows/issue40-current-nginx-include.yml` <=250
6. `docs/deployment/current-nginx-include.md` <=180
7. `docs/specs/issue40-current-nginx-include/requirements.md`
8. `docs/specs/issue40-current-nginx-include/design.md`
9. `docs/specs/issue40-current-nginx-include/tasks.md`

Existing helpers reused without edits: `render.validate`, `runtime_topology.compose/image_refs`, `container_fixture.Fixture/require`, `run_container_topology.oauth/mcp/inspect_boundaries`. A path/contract amendment requires review (NFR-4).

## Test strategy

FR-1: type/injection/canonicality/range and existing directory/file/symlink negatives; exact permission/output inventory; no subprocess/network; failure preserves prior bytes.

FR-2: exact source-shape and hash tests; mutated transport route, missing/changed subprotocol and metadata drift refuse output; no full configuration/global directives; no old route as upgrade target.

FR-3/FR-4: generic namespace uses `location ^~ /coding-tools/` so existing broad regex handlers cannot shadow its proxy boundary; exact discovery and agent routes already outrank regex. More-specific existing namespace prefixes/exact/nested routes, server rewrites/returns/error_page and prior ingress still require operator conflict review. No universal raw-prefix containment or original-URI claim is made for arbitrary existing vhosts. Actual Nginx syntax and HTTP via private owned process/loopback. Exact include file is included, not copied into a string. Baseline root/unrelated prefix/regex locations, then include, then removal tested across owned restart. A broad \.php regex remains active for /legacy.php but cannot capture /coding-tools/probe.php. A duplicate exact location must fail syntax validation. Slashless `/coding-tools` must404, foreign Host421 and no Location redirect. Raw canonical/query paths retain exact upstream URI; repeated-slash/percent-agent aliases record normalized location selection and original forwarded URI; dot-segment escape is expected to reach existing-site and is not raw-prefix containment evidence. Historical/trailing slash variants stay generic; actual gateway aliases must never101. Echo records ordered header pairs/get_all, preserving duplicate and empty observations instead of a lossy dictionary. Raw request helper uses ordered header lines without dictionary coalescing. Echo records only synthetic bounded data; verifies path/query/body, MCP/OAuth headers, auth challenge/status, original Host rejects, forged forwarding stripping, generic/historical/near-miss upgrade suppression and body limit. Actual Compose2.27 config only verifies both prior render forms, including current operator profile. Historical native harness also runs unchanged.

FR-5: current Fixture remains hosted-only with local default Docker guard and fresh UUID project. A new fixture-private ingress directory receives the include/full test wrapper; only generated Compose ingress bind source changes. Reuse from-empty DB/owner/client/device fixture bootstrap, exact-source image and process/port/network checks. Actual PKCE, MCP legacy/modern/mirror/version negatives, current agent101/subprotocol403/Host421, root/unrelated prefix/regex preservation and secret scan run. Raw-wire actual-gateway negatives require duplicate valid+invalid or empty+valid Sec-WebSocket-Protocol403; empty forbidden agent Origin/Cookie/Authorization403; duplicate MCP-Protocol-Version/Mcp-Method/Mcp-Name, including valid+empty,400/-32020; duplicate or empty MCP Origin403. Duplicate Authorization/Host require Nginx400 and zero echo-upstream hits in the mechanics harness; the actual service fixture verifies400 without incorrectly attributing it to gateway admission or claiming unobserved upstream hit counts. These are mandatory actual runtime tests, not solely echo/string assertions. Missing/duplicate malformed HTTP1.1 Host may be rejected by Nginx400 before the location gate; preserve that distinction. Close pending unauthenticated sockets and all exact-owned containers/volumes. Exact-owned cleanup failures prevent PASS. Private Nginx process uses foreground -p/-c, terminate/wait then kill/reap only its own PID; never kill by name/port or issue nginx -s. Echo threads are joined and ports closed. No fixture secrets in evidence.

## Port and topology meaning

Renderer port is an immediate loopback upstream, not a new listener. Mechanics uses independent ephemeral Nginx and echo ports. Runtime uses the new include directly in a generated private ingress: namespace Nginx8080 -> namespace gateway28880, with a separate fresh host published port. No host access to namespace-local28880 is assumed. Operator prerequisite: gateway reachable inside the actual Nginx network namespace through a separately reviewed immediate endpoint; existing host-published old-ingress port is not suitable by default. Where fixture listener/upstream share a namespace, reject equal ports before launching anything, with pure refusal tests. Do not confuse a published host port with the namespace listener. Offline rendering cannot inspect unknown operator listeners. The unchanged old ingress two-hop chain is unsupported: it reconstructs some headers and would invalidate duplicate/empty guarantees. No old source is edited to hide this limitation.

## CI and lifecycle

Branch `ci/issue40-current-nginx-include-20261005` targets PR89 feature branch in a draft PR only after candidate review. Workflow push glob is `ci/issue40-current-nginx-include-*`, with no other event, contents-read only and no persisted checkout credentials or secrets. Existing workflow path filters are rechecked before push.

Ubuntu22 native-config job uses Python3.12, official downloaded/extracted distro Nginx binary without installing/reloading a service, and checksum-verified official Compose2.27. Runtime job uses unchanged exact-build-audit pipeline, Rust1.98.1, fresh external target, exact-source nonroot four-binary image and observed official image digests. Both run deployment contracts; runtime also runs portable service/enrollment tests. Source cleanliness and exact case counts required. Upload only sanitized evidence/audits and bind artifacts through authenticated API/log/raw-ZIP checks.

## Risks and rollback

HIGH semantic boundary risk. Fresh graph on F marks read-only managed_agent_channel_routes CRITICAL (4 direct, 29 upstream, 2 flows); no Rust symbol is edited. Fixture/renderer helpers are LOW. Full-text graph search unavailable, exact symbol graph works. Review is mandatory before implementation.

Tests and renderers cannot establish compatibility with actual BaoTa/WAF/TLS or the unsupported host. Inherited global rules/regex locations/header policies can collide and need actual operator review. Restore/revocation behavior remains separate. No production application occurs; rollback is deleting never-applied output or reverting the additive candidate after explicit integration authority, never touching a live server.

## Checklist

- [x] All FRs map to interfaces and concrete tests
- [x] Current source paths, evidence boundaries and external dependencies verified
- [x] Ownership, failures, cleanup and production exclusions specified
- [ ] Independent design/candidate review and fresh native runs accepted

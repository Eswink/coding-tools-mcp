# Current Gateway Nginx include: operator review contract

**REVIEW ONLY. This is neither an installer nor deployment approval.**
The additive renderer follows the current Gateway route `/coding-tools/agent`.
The historical round-2 renderer remains unchanged. The current private container
ingress now reuses this reviewed contract instead of reconstructing security
headers. Historical results are not evidence for this repair or a real existing vhost.

## Generate an offline review specimen

From the repository root, choose a new output directory:

```sh
python deploy/cloud-gateway/current_nginx_include.py \
  --domain gateway.example.invalid \
  --connector-id 00000000-0000-0000-0000-000000000001 \
  --port 28880 --output /tmp/current-nginx-review-new
```

This synthetic `.invalid` example does not contact a server. The renderer does not
call Git, Docker or Nginx, inspect host configuration, access credentials, or reload
anything. It exclusively creates a private directory (0700) and three files (0600):

- `nginx-locations.current.review.conf`: five scoped location blocks
- `source-contract.json`: exact current-source, renderer and include byte hashes
- `REVIEW_ONLY.txt`: explicit nonproduction limits

An existing or linked final output directory is refused. The domain must be a
canonical lowercase DNS name; the connector must be a nonzero canonical UUID;
the immediate upstream port must be an integer in 1024–65535.
Default domain remains `research-system.eswlnk.com`; examples use `.invalid` only.

Before writing output, the renderer checks the whole-file SHA256 of the five
reviewed current Rust source files (`channel/transport.rs`, `channel/protocol.rs`,
`config.rs`, `mcp/http.rs`, `mcp/protocol.rs`) against the pinned baseline
`310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`, then checks expected route definitions.
Missing, linked, oversized, changed or ambiguous source fails closed. Even a
harmless source edit needs a reviewed pin refresh; this is not a general Rust parser.
The manifest records observed bytes, not authenticated Git provenance. CI must
independently bind those bytes to the exact source SHA, tree, run and attempt.

## The five-block boundary

1. Exact `/coding-tools`: canonical Host only, then 404 without a redirect
2. Exact `/.well-known/oauth-protected-resource/coding-tools/mcp/<connector>`
3. Exact `/.well-known/oauth-authorization-server/coding-tools/oauth`
4. `location ^~ /coding-tools/`: generic protocol namespace
5. Exact `/coding-tools/agent`: current agent WebSocket transport

Only the last four proxy. The output contains no `http`, `server`, `listen`, `map`
or `upstream` block, root-site replacement, TLS/WAF configuration, or apply steps.
The bare-path guard prevents the automatic prefix-slash redirect. Exact locations
and `^~` protect these routes from a broad existing regex such as `\.php$`.
They do not override conflicting exact, more-specific prefix or nested locations,
server-level rewrite/return/error-page behavior, or an earlier ingress.
Those remain mandatory preflight review subjects for any later operator proposal.

Nginx selects locations using normalized URIs. The private unrewritten wrapper
observes both the selected destination and original upstream URI: repeated slash
and encoded agent aliases, dot-segment escape, query, historical path and trailing
slash are separate cases. A dot-segment escape can select the existing site.
There is no claim that every raw textual `/coding-tools` prefix is contained.
`proxy_pass` has no URI suffix; original request URI forwarding is demonstrated
only in that unrewritten wrapper, not after arbitrary rewrites/internal redirects.

## Original Host and header integrity

Each scoped block requires original `$http_host` to exactly equal the canonical
authority. Uppercase, explicit `:443`, trailing dot, foreign and empty authorities
are deliberately refused. No `$host` normalization or forwarded-host trust applies.
Proxied Host remains the original accepted value. Missing, duplicate or malformed
HTTP/1.1 Host can be rejected earlier by the actual Nginx parser with 400, rather
than the location's 421. Rejected parser requests must not reach the echo upstream.

Inbound `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-For` and `X-Real-IP` are
removed. Fixed `X-Forwarded-Proto: https` is a transport hint, never an authority.
End-to-end Authorization, Origin, Cookie, Accept, Content-Type,
MCP-Protocol-Version, Mcp-Session-Id, Mcp-Method, Mcp-Name and Last-Event-ID pass
through Nginx's native request-header forwarding. No `$http_*` reconstruction
may erase empty fields or coalesce accepted duplicates before runtime admission.
Duplicate Authorization, like duplicate Host, instead produces parser-level 400.
A single empty Authorization is preserved and the actual agent runtime rejects it.

Only exact `/coding-tools/agent` forwards hop-by-hop Upgrade/Connection.
Sec-WebSocket-Protocol stays natively forwarded, preserving accepted duplicate
and empty offers for the Gateway to reject. Upgrade/Connection are intentionally
normalized; original client hop-by-hop duplication is not claimed to survive.
Generic, discovery, historical `/coding-tools/agent/connect` and near-miss routes
cannot acquire WebSocket support from this include. Runtime still owns query,
subprotocol, authentication and authorization checks; those gates are unchanged.

HTTP/1.1, bounded timeouts and a 64k body cap apply. Proxy buffering, request
buffering, cache, error interception and proxy redirects are off. Access logging
is off only within the five scoped locations; unrelated site settings are untouched.

## Immediate-upstream prerequisite and port meanings

The selected port is the immediate loopback upstream endpoint reachable **inside
the Nginx process network namespace**. Reachability needs a separately reviewed
arrangement; a port number alone establishes none. Default 28880 names the current
Gateway's direct loopback service contract, not a new public listener.

The single-hop runtime proof still replaces only its disposable ingress config:
private Nginx listen 8080 → same-namespace loopback Gateway 28880. A separate fresh
two-hop run keeps the topology's current generated private ingress config and adds
an owned runner-local distro Nginx subprocess:

outer loopback Nginx → host-loopback published inner ingress → Gateway → PostgreSQL.

The outer listener and published inner port are distinct; the outer include targets
the latter, never the namespace-only 28880. `runtime_topology.ingress_config` checks
`current.source_contract()` and embeds `current.locations(domain, connector, 28880)`
inside its existing private server wrapper. The source check fails closed on drift;
there is no second security-header renderer. Its Host guard, root 404, private
listener 8080 and Compose topology stay in place. Two-hop root/prefix/regex sentinel
checks concern the outer wrapper; direct-inner negatives separately check the repair.

**Historical header-reconstructing ingress remains UNSUPPORTED as this include's
immediate upstream.** Duplicate/empty-header safety does not compose through that
old config. A published port or image name alone does not prove the repaired bytes
are running. This is a bounded engineering fixture, not a ready-to-apply container
recipe, host reachability proof or production compatibility claim.

The mechanics proof uses separate ephemeral Nginx and echo-upstream ports; its
Compose config port values are read-only inputs. Known equal listen/upstream ports
are rejected before starting either private wrapper. The offline renderer cannot
inspect an unknown operator listener or rule out self-proxy there.

## Required evidence and its limits

The dedicated push-only workflow has two separate jobs on Ubuntu 22.04:

- `native-config`: baseline deployment tests and new pure/CLI tests, actual
  extracted distro Nginx syntax/mechanics, historical native checks, exact Compose
  2.27.0 config normalization. It uses a bounded echo upstream, never a real Gateway
- `runtime`: portable current Gateway contracts, a fresh locked Rust 1.98.1
  four-binary build with unchanged `exact_build_audit.py` and cargo-audit 0.22.2,
  then separate single-hop and two-hop fresh owned fixtures using the same audited
  binaries and immutable-image Nginx/Gateway/PostgreSQL references. The two-hop run
  uses an extracted distro Nginx binary, without installing a host Nginx service

The first proof checks root/unrelated-prefix/regex handlers before, during and
after inclusion; actual header pairs, raw URI selection, status/body/challenge
forwarding, the 64k limit, and parser 400 with zero echo hits. The second requires
real OAuth PKCE, MCP initialize/legacy/modern acceptance and rejection gates,
raw duplicate/empty-header negatives, exact current subprotocol 101 and nonupgrade
aliases. Keep the 34-case native mechanics and 45-case single-hop runtime inventories
separate. Two-hop mode runs the same 45-case suite through the outer endpoint, plus
direct-inner empty Origin/Cookie/Authorization, duplicate/empty subprotocol and
foreign Host negatives. Runtime parser 400 checks do not invent Gateway-side hit observability.
A 101 creates a pending **unauthenticated** socket, not enrollment, agent identity,
local tool execution, WSS/TLS acceptance, or authorization to execute anything.

The bounded two-hop lifecycle checks require a pending socket to drain on a clean
Gateway stop before authentication expiry, then restart with unchanged namespace,
inner ingress and outer process identities. OAuth authority must persist; shipped
CLI device revocation must survive a database restart and prevent service startup
with `provisioning_not_ready`. These checks do not exercise an authenticated Agent.
Authenticated Agent WSS, reconnect, revocation and drain remain **NOT_EXECUTED**:
the shipped Agent requires verified WSS, while this fixture uses plaintext loopback
transport with a synthetic `.invalid` HTTPS identity. No TLS bypass is introduced.

Private Nginx processes and echo servers are owned, stopped and reaped; runtime
containers/volumes are fresh, uniquely labeled and cleaned. Cleanup failure fails
the check. No production service is installed, adopted, signaled or reloaded.
Disposable fixture credentials stay in private files/stdin, never uploaded.
Only safe reports, tool identities, source manifests and raw audit evidence are
artifacts. The separately rendered review specimen uses fixed synthetic inputs;
the harness reports bind the distinct exact include bytes actually tested.
The two-hop report records the actual inner `nginx -v`, rendered-config hash checked
against `/run/ingress/nginx.conf` in the running ingress, immutable image identity,
outer include/config hashes and outer binary hash/version. The runtime artifact
retains distro package metadata and package/binary hashes alongside separate
`current-runtime.json` and `current-two-hop-runtime.json`, bound to the same exact
source SHA/tree, audited binaries, Compose hash and Actions run/attempt.

Require both jobs' terminal success on the reviewed SHA/tree, complete job logs,
authenticated Actions run/attempt and artifact IDs, raw ZIP digest/size verification,
data-only report/source replay, clean-source checks and secret scans. Neither a
source-binding receipt nor mock/pure tests alone establishes native success.
Raw audit findings and all existing release blockers remain visible and unchanged.
These are required checks, not a claim that CI has run or passed for this correction.
The existing closed composition profile intentionally rejects this changed source;
it remains untouched and blocked. Integration needs a separately reviewed exact-source
amendment, not refreshed historical pins or a descendant exemption.

`applied`, `production_ready`, `real_host_tls_waf_tested` and `publish_approved`
remain false. Real VPS/DNS/TLS/BaoTa/WAF/ChatGPT, host Engine and external reachability,
EOL CentOS suitability, route collisions, restore/rollback and broader Issue40
acceptance remain **NOT_EXECUTED / incomplete**. This document supplies no live
application instructions or release/merge/integration authorization.

References: [Nginx WebSocket proxying](https://nginx.org/en/docs/http/websocket.html),
[Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Compose services](https://docs.docker.com/reference/compose-file/services/).

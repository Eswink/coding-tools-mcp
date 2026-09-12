# Public OAuth routing repair plan

## Request and baseline

User request: fix the public discovery failures shown in the screenshot and
`MCP server https://research-system.eswlnk.com/mcp does not implement OAuth`.
Plan first, then iterate, with a maximum of 20 iterations.

Baseline: main `a0551c447712104e2c2cb253d3d8a5a966518580` (v0.3.2),
tree `181e5353c38aa39fa72d8b96abedfe1f75e80982`.
The source artifact digest and extracted Git tree were verified before editing.
The screenshot reports local OAuth discovery passing and three public metadata
requests returning HTTP 404 / non_json_response. It does not prove which proxy,
tunnel, backend, or deployment configuration generated those responses.

## Scope and acceptance

Separate four results: repository correctness, deployed routing, public discovery,
and real ChatGPT account integration. Never substitute one for another.
The public origin must return matching JSON authorization-server and protected-
resource metadata, including the path-specific and root compatibility locations.
An unauthenticated JSON POST /mcp must return 401 with the expected Bearer
resource_metadata challenge. Authorization, token exchange and MCP must route to
the same intended runtime, preserving paths and required headers. PKCE, token
validation and local user approval must remain enforced.

No secrets, authenticated business calls, private configuration or remote response
bodies may be exported as probe evidence. Do not change DNS, tunnel dashboards or
unrelated services without a verified deployment target and appropriate access.
Do not disable OAuth, TLS verification or system sandboxing to obtain a PASS.
Do not merge, publish or claim the reported public failure fixed while its public
gate is failing or unverified. Any later installer uses a new synchronized version.

## Iterations

| Iteration | Work | Evidence / exit condition |
|---|---|---|
| 1 | Recover exact source, rules and old release boundaries | Verified source tree and explicit baseline |
| 2 | Independent credential-free public probes | HTTP status, response classification, bounded digest; no raw body |
| 3 | Local listener/discovery/401 contract review | Identify OAuth disabled vs missing forwarding |
| 4 | Tunnel/proxy target, path and port investigation | Proven code defects separated from deployment hypotheses |
| 5 | Minimal verified configuration/routing repairs | Failure-first regression, then repaired contract |
| 6 | Real reverse-proxy HTTP regression | MCP-only routing fails; complete route set succeeds |
| 7 | Diagnostic classification and request location | Actionable missing-route/wrong-backend/auth-state distinctions |
| 8 | UI routing guidance matching active service | Correct origin, endpoint, local target and required routes |
| 9 | Adversarial and negative tests | No response/credential leakage, unsafe redirects or auth bypass |
| 10 | Full Windows/Linux Rust and frontend regression | All existing baselines and new cases pass |
| 11 | Recheck the specified public origin | Correct public metadata and challenge, not just local CI |
| 12 | Review and convergence | Separate code/deployment/public/account results; preserve blockers |
| 13-20 | Targeted repairs for newly reproduced failures | One hypothesis, minimal diff and evidence per iteration |

Stop early only on demonstrated convergence or a concrete external access blocker.
Do not manufacture iterations, invent failure evidence, or repeatedly rerun until
a transient failure disappears. Persist observed failures even after a repair.

## Execution channels

The current container could not resolve the user host or npm registry. That is an
execution-environment observation, not a diagnosis of the user's DNS.
The configured mcp-probe-kit 4.0.1 launcher is absent from the exported source;
its exact-version installation failed with EAI_AGAIN. GitNexus query via the
available offline CLI channel failed with ENOTCACHED. Plugin discovery returned
no usable research-system, mcp-probe-kit or Cloudflare administration connection.
Use bounded CI for independent networking and native builds. Record manual source
call-chain/diff review as a fallback, never as a successful MCP/GitNexus invocation.

## Reference contracts

- MCP authorization: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- OpenAI authentication: https://developers.openai.com/plugins/build/auth
- Repository rules: AGENTS.md and .agents/skills/mcp-probe-kit/SKILL.md

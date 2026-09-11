# OAuth discovery and runtime application repair

Baseline: main 192e9d7e326c0391bf6936d72d5f69bae62286f5 / tree e7054d30863215cf7506e6ffb9d693d2a34ee6f7.

## Evidence and limits

The reported public MCP GET returns 200 while two public OAuth metadata routes return 404. GET /mcp is a public discovery payload, not proof of OAuth enforcement. The listener explicitly returns 404 OAuth-not-configured for a non-OAuth snapshot. The health checker discards error bodies and only checks public OAuth endpoints, so it cannot distinguish this response from a reverse-proxy 404. We cannot inspect the user's running process or reverse proxy from the repository. Anonymous public reads have not returned an inspectable response here; no user credentials are used.

The previous diagnosis overstated two points. The page already attempts restart after an auth save, but relies on UI running state and swallows restart failure; backend update_workspace persists without synchronizing the listener. Origin-only resource identifiers are permitted by the MCP spec and shown in OpenAI documentation; /mcp is the explicit, more specific identifier selected for this repair, not a universal protocol requirement. Its migration must preserve exact audience checks and require reauthorization of old origin-audience tokens.

The runtime currently ignores stored MCP client_secret although the copy UI displays it. The server has neither DCR nor CIMD support: this repair uses predefined clients and documents ID/secret configuration rather than advertising unimplemented registration. OAuth callback remains exact and user-configured; never accept arbitrary redirect URLs.

## Acceptance and order

1. Characterize the three failing HTTP discovery/identity expectations on both platforms before implementation. Preserve production logic in this iteration.
2. Separate issuer and resource throughout PRM, code binding, token audience, validation and challenge. Serve root and /mcp-specific PRM without credentials. Preserve Actions' separate resource policy.
3. Apply auth changes at the backend lifecycle boundary, wait for completion, propagate failure, never start previously stopped services, revoke affected chat grants. Eliminate duplicate frontend restart. Make stored client secret usage match discovery metadata.
4. Compare local and public discovery, enforce required metadata fields and exact URLs, distinguish OAuth-disabled JSON from proxy/route failure, reject redirects/HTML/missing fields. Probe without sending secrets and bound all response bodies. Mask secret copy fields by default.
5. Real HTTP OAuth authorization-code/PKCE tests plus negative audience/client/redirect/code replay; running-config change tests; frontend tests; all existing Rust and native five-package combinations. Proxy routing is tested with an independent fixture; live deployment remains distinguished from fixture evidence.
6. Review every iteration. Scores are scoped self-review, no score can override a failed gate. Merge only verified head; build next patch release from exact main, no overwritten tags/assets, anonymously recheck public assets. Actual ChatGPT account and conversation metadata verification stays local.

## Initial review

Iteration 1: characterization only, 90/100 (CI pending; not a fix acceptance). Graph authority-flow impact HIGH: 4 direct callers and 8 total symbols in MCP, Actions and auth tests. update_workspace IPC edges are absent from static graph; manual caller review adds the Svelte/API path. Full-text graph lookup is unavailable offline; exact symbol graph is available. No product credential, personal endpoint or token is committed.

## Primary references

- https://developers.openai.com/plugins/build/auth
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

## Iteration 2 - explicit resource identity (2026-09-11)

Recovered the existing red tests at 687c7c84; both operating systems actually failed the three HTTP assertions in run 34560789194. This is the first implementation, not a reclassification of those failures as passing.

MCP now selects the /mcp resource independently of the issuer. Root and path-specific resource metadata are aliases, and the 401 challenge selects the path-specific document. Authorization codes preserve the exact resource and JWT validation checks issuer and audience separately. Actions retains its existing origin resource. Old origin-audience MCP tokens require a fresh link. Discovery success and OAuth-disabled responses are uncacheable. The stored-secret/lifecycle and diagnostic repairs are deliberately deferred to the next iteration; no package is released by this iteration.

Added real HTTP authorization-page/PKCE/code-exchange/initialize coverage, valid OAuth without a chat grant denial, metadata alias checks, wrong client secret, wrong resource, wrong PKCE, code replay and old-audience rejection. Existing fixture token audiences were migrated without deleting their isolation assertions. CI now runs the complete Rust baseline, all-target checks and production-library -D warnings. No dependency or version change.

Pre-CI self-review: 92/100, candidate only. Manual review covered service-specific audience handling, no redirects during the test exchange, no fixture credentials in product configuration, and no permissive audience fallback. GitNexus listener impact is CRITICAL (20 symbols, 6 flows); graph and exact staged diff are reviewed. Full-text graph search is unavailable offline; exact symbol traversal is available. This score cannot override pending or failed runtime tests.

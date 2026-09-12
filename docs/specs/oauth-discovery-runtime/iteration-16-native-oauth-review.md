# Iteration 16: migrate native OAuth acceptance to the repaired contract

Parent: `e629875b80f1a944f69ca5fc39ff50f67538d0a9`, tree `aa725ead78be1af3b9d690e1e6d62429cbf1f7ec`.

## Actual failure

Strict native run `34684664507`, Ubuntu 24.04 job `103529975777`, reached the real application window and passed its first workspace/security stage. At 2026-09-12 09:04:38 UTC it failed in `oauth_token` at the obsolete assertion `resource == base`. The output records `passed: false` and one completed stage. This is a genuine failed native run, not native acceptance. Its failure artifact is `10295630098`.

The earlier application repair intentionally made the MCP protected resource `origin + /mcp` while retaining the issuer at the origin. The native harness still expected the old origin resource and omitted client authentication even though it now exercises the real stored client secret. This is a migration of this application's chosen contract; it does not assert that an origin resource is universally invalid under OAuth.

## Repair and manual impact

Set a fresh random confidential-client secret through the real workspace IPC before starting the service. Require both protected-resource metadata routes to return identical metadata with the exact `/mcp` resource and the correct authorization server. Require exact issuer/endpoints, S256 PKCE, and the confidential-client authentication methods. Assert the precise path-aware 401 challenge and no-store behavior.

Before a successful token exchange, send actual HTTP requests with a missing secret and a wrong secret. Both must return 401 `invalid_client`, the Basic challenge, no-store, and no fixture secret/path disclosure. Then use the configured client secret and the same authorization code: failed client authentication must not have consumed the code. Existing real-window approval, denial, two-session isolation, revocation, exclusive access and restart assertions remain intact.

Callers include debug native Linux/Windows validation and all five installed-package combinations. Risk is HIGH for acceptance fidelity and confidential-client validation. No production authentication, authorization check, fixture approval policy, sandbox setting, workflow permission or failure gate is weakened. MCP/GitNexus are unavailable as previously documented; the upstream/downstream review is manual and is not a claimed graph-tool result.

## Evidence and scoped review

Six added harness unit cases characterize metadata identity, complete confidential-client flow, rejection of unauthenticated success, and secret non-disclosure. Before implementation these new cases produce one failure and five interface errors; the four existing cases pass. After implementation all **10/10** pass. Interface errors are not presented as six independently observed production bugs: the actual resource-contract failure is independently established by the native job above.

On the combined iterations 15–16 candidate, the integrated authorization helper suite passes **105/105**, release-readiness tests **13/13**, existing release tests **19/19**, native-entry contracts **5/5**, and complete frontend regressions **124/124**. Both changed workflows parse as YAML, the release preflight identifies six consistent 0.3.2 fields, and diff whitespace checks pass.

The new unit cases use controlled HTTP responses and are not native evidence. The exact uploaded candidate still requires full dual-platform CI and the unchanged five-combination installed native matrix. The failed old run cannot approve this new tree. No merge, publication or overall-complete claim is made.

Scoped self-review: **94/100**, eligible for strict CI only. Remaining uncertainty is resolved by actual native execution, not by this score.

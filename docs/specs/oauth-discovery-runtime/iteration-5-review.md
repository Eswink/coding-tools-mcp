# Iteration 5: bounded, semantic, runtime-aware diagnostics

Base: 3f1915f99ef6d02d55c92bad7693a7f4a29a1ade / c6bdf880f078cc66ff0d7071417abad18463d234. Source archive SHA-256 verified; local inspection snapshot has the exact remote tree. The uploaded Fixture::new conflict log is historical evidence, not a new failure of this revision. Iteration 4's Windows/Linux job success and raw evidence are retained.

## Cause and contract

The old check_url accepts 404. check_json_field returns true for successful JSON even without its required field. GET /mcp alone proves neither OAuth nor Chat Grant. The checker builds public metadata URLs from saved profiles rather than the live Quick origin, follows redirects and reads unrestricted bodies/errors into diagnostics. Its Actions checks fail when only MCP is intentionally running.

Replace this with fixed credential-free routes, no redirects/proxies, validated origins, response size/time limits, exact metadata identities and required fields, and a strictly parsed unauthenticated POST /mcp challenge. Check both root and path-specific PRM. A local success/public failure is classified separately. Never follow URLs from received JSON or log remote error strings. Inapplicable/stopped checks have skipped=true and ok=false, not a false PASS. Native ChatGPT linking is not performed by a health probe. Configuration/identity changes during a check invalidate the result.

## Scope and risk

Graph 1.6.9: 6010 nodes, 14435 edges. Exact-symbol upstream probes cover all replaced health helpers and both public entry points. The graph does not resolve the imported alias/Tauri IPC edge; manual caller inspection adds commands/health -> health::run_health_checks -> HealthPanel. Health helpers have one direct health-flow caller. Manual risk HIGH because these results guide authentication deployment. No OAuth issuer/audience policy, secret storage, package versions or dependencies are changed. Graph FTS is unavailable offline; it is not used as successful evidence.

## Verification and review

Added HTTP fixtures for 404, disabled OAuth, HTML/FRP, arbitrary or malformed JSON, redirects with an unvisited destination, no credential headers, Content-Length and chunked limits, timeout, required AS/PRM fields, exact challenge parsing, stopped-service semantics and an actual MCP listener behind a synthetic incomplete proxy. The latter proves local discovery success vs public missing metadata without claiming the user's public deployment was inspected.

Initial self-review: 90/100, rejected before submission for missing body bounds, stale-origin and skipped-service cases; those cases are now implemented and covered. Pre-CI candidate: 94/100. Rust cannot run in this container (no toolchain/network); Windows/Linux CI is mandatory. Frontend skipped-state rendering, duplicate-restart and credential refresh fixes, actual installed native matrix and release gates remain open. This intermediate revision must not be merged or released.

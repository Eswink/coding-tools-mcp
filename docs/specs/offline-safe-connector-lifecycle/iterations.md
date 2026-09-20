# Iteration evidence

## 00 — Planning baseline

Date: 2026-09-20  
Base: `main@823cbdeba68bbdd832d93f4636f701ddb98474f1`  
Branch: `plan/offline-safe-connector-lifecycle`  
Result: PASS for planning only; no product fix claimed.

### Repository evidence reviewed

- `src-tauri/src/mcp/listener.rs`: per-workspace MCP listener also hosts OAuth discovery, authorize and token endpoints.
- `src-tauri/src/commands/runtime.rs`: `stop_mcp_service` stops listener and then stops MCP tunnel.
- `src-tauri/src/auth/session_policy.rs`: chat lease/access/refresh durations are explicit and separate.
- `src-tauri/src/auth/聊天授权v1.rs`: chat authorization/exclusive owner/draining logic only applies after a request reaches the local service.
- `src-tauri/src/mcp/server.rs`: authorization and business-tool semantics are tool-layer behavior.
- Existing spec style in `docs/specs/exclusive-conversation-refresh/` uses plan/tasks/iterations with evidence-gated completion.

### Initial classification

Observed architectural coupling is sufficient to explain why an intentional local stop removes the remote protocol surface, but it is NOT sufficient to conclude exactly which ChatGPT host condition produces the reconnect card.

Therefore:

- root cause class: control-plane availability coupled to workspace execution lifecycle;
- exact host trigger: UNCONFIRMED;
- implementation choice: BLOCKED on Round 1;
- production change: NONE.

### Next gate

Execute ISSUE-001 C1/C2 first. Do not implement token-TTL or authorization changes as a speculative fix.

## 01A — Round 1 deterministic fault harness

Date: 2026-09-20  
Branch: `test/offline-safe-round1-harness`  
Candidate after repair: `6925bc864daecb9c4dc3923c2ebd9f80b8a76946`  
Result: PASS for harness contracts; real ChatGPT host gate remains OPEN.

### Scope

Added only test/docs infrastructure:

- `scripts/connector_fault_proxy.py`
- `scripts/connector_fault_proxy_tests.py`
- `.github/workflows/offline-safe-round1-harness.yml`
- `docs/specs/offline-safe-connector-lifecycle/round1-harness.md`

No production MCP, OAuth, runtime, tunnel, authorization or UI source file was modified.

Manual compare against planning base `a16ab50c9b543b305bb6958196d76dd2ac6fa3bd` reports exactly four added files and zero production changes.

### Harness contract

Allowlisted modes now cover:

- C1/C6: `pass`
- C3: `mcp-503`
- C4: `workspace-offline`
- C5: `oauth-token-503`
- C7: `oauth-refresh-reject`
- C8: `reset-mcp`

C2 continues to use the current application stop flow. C9/C10 use the real chat authorization/exclusive implementation.

The proxy does not log Authorization headers, OAuth request bodies or MCP request bodies. It supports bounded Content-Length and chunked requests and caps bodies at 2 MiB.

### Local validation

Isolated local execution before upload:

```text
python -m py_compile scripts/connector_fault_proxy.py scripts/connector_fault_proxy_tests.py
python scripts/connector_fault_proxy_tests.py
8 tests, 8 passed
```

This validates only the harness contract, not ChatGPT behavior.

### Failure-first CI and repair

Initial GitHub runs `35501924215` and `35501926129` failed on both Windows and Ubuntu during `py_compile`.

Observed cause: the connector upload string encoded Python `\n` / `\r\n` escape sequences as literal line breaks, producing an unterminated string at `EvidenceWriter.write`. This was a source transport/serialization defect in the uploaded harness, not a product runtime result.

Repair commit `6925bc864daecb9c4dc3923c2ebd9f80b8a76946` preserves the source escape sequences exactly.

Post-repair evidence:

- push run `35501992893`: SUCCESS;
- pull-request run `35501994608`: SUCCESS;
- Ubuntu 24.04: compile PASS, contract tests PASS;
- Windows 2025: compile PASS, contract tests PASS.

The failed runs are retained as evidence; they are not rewritten as PASS.

### Required tooling downgrade

This ChatGPT execution environment does not expose the repository's mcp-probe-kit or GitNexus tools. The documented CLI fallback could not be restored because the local container cannot resolve GitHub/npm network endpoints, and there is no mounted repository checkout.

Because this iteration adds only new test/docs files and changes no existing production symbol, execution proceeded with source inspection, exact GitHub compare and cross-platform CI as the bounded fallback. This does NOT waive the repository rule for Round 2/3 production edits: impact analysis is still mandatory before changing existing production symbols.

### Current blocker / next gate

Real-host C1-C10 evidence requires a dedicated local test workspace/listener plus a test-only public hostname routed through the proxy and an actual ChatGPT connector using that hostname.

Until that environment is active:

- ISSUE-001 stays IN PROGRESS;
- reconnect trigger remains UNCONFIRMED;
- Round 2 stays BLOCKED;
- no production fix is authorized.


### Final harness CI checkpoint

Workflow-only refinement commit `99bb250500f4089f55f1b39e62f2b240aa59f9ea` removed docs-only triggers so evidence edits do not launch redundant cross-platform harness jobs.

Final validation on that revision:

- push run `35502104161`: SUCCESS;
- PR run `35502107154`: SUCCESS.

The harness branch is therefore ready for real-host C1-C10 observation, but ISSUE-001 remains open.

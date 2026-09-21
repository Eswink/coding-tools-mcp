# Execution record

## Round 1 — preparation, 2026-09-21

- User approved implementation of the cloud Gateway + Windows/Ubuntu Agent plan.
- Verified main `758c60a6e74e624e144f9c19c5f19d04d17f7a13`; created independent branch and GitHub #32–#35.
- Read root AGENTS.md, pinned mcp-probe-kit skill, project context and GitNexus instructions. Context prose is stale; current source is authoritative.
- Container DNS cannot reach GitHub/npm. Initial clone failed with name resolution error; no source-change conclusion drawn from that failure.
- Added only a read-only CI preflight workflow at `0bb58707911bd46f257ade33ed313e4566f8a090`. Run [35562387111](https://github.com/Eswink/coding-tools-mcp/actions/runs/35562387111) succeeded, exporting public Git bundle and pinned mcp-probe-kit 4.0.1 / GitNexus 1.6.9 tooling.
- Source bundle and tooling SHA-256 checked. `resume_plan` reported no resumable plan. Created delegated plan `feature-cloud-gateway-agent-runtime-steady-78d17ac437` and initial heartbeat.
- Refreshed graph locally. Query FTS extension unavailable in this offline environment; recorded instead of interpreting empty results as absent code. Direct symbol impact works: handle_request LOW, intercept HIGH. User warned; no existing production symbols will be edited in round 1.
- Bootstrap workflow commit preceded local graph availability. CI retrospectively checked its diff and found no production symbol impact. This exception is limited to infrastructure bootstrap; subsequent commits require staged change review.
- Read official MCP wire/schema references and pinned Codex reference `a86631502d49274cb47208925c7d3dcece032029`. No Codex code copied.

## Current truth labels

Architecture/spec: SPEC_CHECK_PASS (0 errors / 0 warnings); production security review remains open.
Protocol laboratory: CROSS_PLATFORM_CONTRACTS_PASS for candidate `82c20d3`; see round1-validation.md.
Production OAuth/enrollment/agent execution/deployment: NOT_IMPLEMENTED.
Real ChatGPT cloud-path behavior: UNCONFIRMED_ON_REAL_HOST.
Existing desktop/runtime/package source: UNCHANGED.

## Round 1 — implementation and local validation

- Added a Node.js standard-library loopback protocol lab (four source modules, each under 500 lines), with explicitly synthetic state and no OS execution or outbound device transport.
- First spec check failed: missing dependency heading and FR mapping. Fixed these, then check_spec passed with zero errors and zero warnings.
- Initial HTTP suite: 30/30 passed. Manual review found null arguments silently became an empty object; added a regression that failed (6 pass / 1 fail in offline suite), then fixed dispatch to default only undefined. Direct impact analysis for dispatchProtocol was LOW, isolated to the new lab server.
- Added a separate-process CLI smoke test and startup/credential-output checks. Final local HTTP/CLI suite: **32/32 passed**, zero skips.
- Existing offline-safe UI contracts: **8/8 passed**. Existing Python fault proxy contracts: **8/8 passed**. These are source/harness regressions, not desktop installation or real-host tests.
- Local Node: v22.16.0; Python: 3.13.5. Container has no Rust toolchain; Rust production tests were not rerun because production source is unchanged. Candidate CI will verify additive scope and run the lab on Windows/Ubuntu.
- New production metadata, device identity, signed execution, native sandboxing and VPS deployment remain unimplemented. The lab's unknown-outcome fixture tests classification, not durable at-most-once execution.

## Round 1 — cross-platform candidate verification

Run `35564597505` passed on Windows 2025 and Ubuntu 24.04. Each platform ran 32 HTTP/CLI, 8 existing UI and 8 Python fault-proxy tests. The pinned graph/spec job also passed. Downloaded artifacts were SHA-256 verified; Ubuntu candidate bytes match all 31 local files, and Windows matches after its exact LF-to-CRLF checkout conversion. This is a protocol laboratory gate, not installed-app or real ChatGPT acceptance. Full evidence identifiers and continuation are in [round1-validation.md](round1-validation.md).


## Round 2 — local durable identity and deployment boundary (2026-09-21)

Base ba9c379; independent local branch, no GitHub write capability. Implemented Rust identity primitives with actual PostgreSQL/HTTP tests and review-only deployment rendering for the supplied Nginx/Baota topology. See `round2-validation.md` for result counts and remaining gates. A malformed-Origin URL normalization bug was reproduced by a failing regression, fixed after LOW-impact analysis, then retested. Test-file splitting exposed an unused import under `-D warnings`; removed and retested. Neither failure is hidden.

Remote publication, public OAuth/Agent integration and real Host acceptance remain open. No server or desktop configuration changed.


Round 2 gate follow-up: retained failing architecture metadata/cleanup checks and incremental graph CRITICAL evidence. Full graph rebuild restored symbol IDs; scoped impact and protected-object checks bounded the actual diff, while aggregate CRITICAL remained visible. Architecture metadata now models the additive library accurately; validate/drift passed. No production deployment or security certification inferred.

## Round 3 — ISSUE-013B / GitHub #41, 2026-09-21

Recovered local 4b6f197 from its verified Git bundle. No persisted probe state file was bundled, so resume returned not_found; reconstructed the same delegated plan identity from the exported checkpoint and resumed existing parent-child specs, not a new feature layout. Scope/spec checked before implementation.

Implemented browser identity/consent with an additive migration and six source modules; preserved the trusted issuance API with an internal caller-transaction helper. Found and fixed lock-wait expiry after a failure-first regression. Updated the deliberate authorize GET/POST contract without opening admin endpoints. See round3-validation.md and review.md for exact validation boundaries and retained intermediate failures.

Current local result: 68 Rust tests, 13 deployment contracts, 32 protocol lab tests, 8 UI contracts, 8 fault-proxy contracts; format and Clippy all-targets PASS. Real independent database/process restarts for both refresh and authenticated browser consent PASS. These are container tests, not remote Windows/PostgreSQL, VPS, or real ChatGPT evidence. Publication uses exact tested tree identity and no force update. M2 remains active.

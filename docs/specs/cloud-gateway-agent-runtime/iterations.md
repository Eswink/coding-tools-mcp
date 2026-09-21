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
Protocol laboratory: LOCAL_CONTRACTS_PASS; remote Windows/Ubuntu CI pending.
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

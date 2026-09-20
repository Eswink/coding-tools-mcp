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


## 02 — Real-host deferral and availability design freeze

Date: 2026-09-20  
Branch: `design/offline-safe-availability-contract`  
Result: DESIGN PASS; production implementation BLOCKED on mandatory impact analysis.

### Sequencing decision

Real ChatGPT host testing is deferred because the dedicated public test connector setup is operationally expensive. This does not convert synthetic behavior into host evidence.

Transferred to Round 5:

- C1-C10 actual ChatGPT UI observations;
- exact reconnect-trigger classification;
- proof that `WORKSPACE_OFFLINE` avoids reconnect UI.

Round 2 is allowed to proceed using only verified architectural coupling and the validated fault harness.

### Source review

Additional source review confirmed:

- `RuntimeStatusDto` currently has one lifecycle `state` field and no independent execution-availability field.
- TypeScript `RuntimeStatus` mirrors that DTO.
- `src/lib/api/workspaces.ts` exposes hard start/stop/restart operations only.
- `chat_domain::intercept` is the existing remote authorization boundary before chat-scoped recursive dispatch.
- `ChatAuthorizer::admit` already linearizes conversation admission but should not be overloaded with workspace execution policy.
- `ToolContext::background_snapshot` shares task/session resources, so a new execution gate must also be shared across snapshots.

### Design correction

A simple Online/Offline flag was rejected because of a pause-vs-dispatch TOCTOU:

```text
request observes Online
pause commits
request starts side effect
```

The frozen design uses `WorkspaceExecutionGate::try_admit` + RAII `ExecutionPermit` with one mutex-protected availability/in-flight state.

This gives the required linearization:

- permit acquired before pause => work was already admitted and may finish;
- pause returns => no later remote execution permit may be issued.

### Frozen first-increment contract

- Existing listener `RuntimePhase` remains control-plane state.
- New execution state is Online/Offline.
- Authorization runs before availability so foreign chats do not learn workspace state.
- Hard `stop_runtime` keeps current listener+tunnel shutdown semantics.
- New pause/resume operations are additive.
- OAuth, refresh family, chat lease and tunnel configuration do not change on pause/resume.
- `tools/list`, initialize, ping and OAuth routes remain stable.
- Offline drain-control set: `get_exec_task`, `list_exec_tasks`, `read_output`, `cancel_exec_task`, `kill_session`, `write_stdin`.
- Every other remote business tool requires Online.

### Impact gate

Manual source preparation classifies the future production change as HIGH risk, but repository rules require GitNexus impact before modifying existing symbols.

Current ChatGPT tools do not expose GitNexus/mcp-probe-kit and the local fallback remains unavailable here. No production symbol has been edited.

Round 3 therefore starts only after that impact gate becomes executable or the maintainer explicitly revises the repository rule.

### Truth status

- lifecycle coupling: VERIFIED;
- synthetic fault harness: VERIFIED CROSS-PLATFORM;
- Level A design: FROZEN PROVISIONALLY;
- exact ChatGPT reconnect trigger: UNCONFIRMED_ON_REAL_HOST;
- product fix: NOT IMPLEMENTED;
- release acceptance: NOT STARTED.


## 03 — Round 3 Level A control/execution split

Date: 2026-09-20  
Branch: `feat/offline-safe-execution-gate`  
Validated source candidate: `e4ea1e25f53e8d897609184e85c10d43328bf557`  
Draft PR: #21  
Result: **PASS for Round 3 source/synthetic gates; real-host reconnect acceptance remains DEFERRED.**

### Implemented boundary

The candidate keeps the MCP/OAuth control listener alive while independently fencing new remote workspace execution.

Source scope includes:

- atomic `WorkspaceExecutionGate` with Online/Offline admission;
- generation-bound pause/resume IPC;
- authorization-before-availability ordering;
- offline drain-control allowlist for existing task/session observation and control;
- additive `executionState` / `runtimeGeneration` status fields;
- explicit desktop “Pause remote execution” vs hard “Stop connector” UI;
- sanitized availability transition/rejection logs;
- hard stop and tunnel teardown semantics unchanged.

### Failure-first implementation evidence

The first listener implementation widened `spawn_listener_with_origin` from a 2-tuple to a 3-tuple. Existing OAuth, health and async transport fixtures failed compilation.

GitNexus independently classified the listener boundary as CRITICAL. The implementation was then narrowed:

- existing legacy listener wrapper remains test-only and keeps the pair-return contract;
- production runtime uses a crate-local gate-aware listener entrypoint;
- no failure was reclassified as PASS.

### Focused impact evidence

Workflow run `35506436646`: PASS.

GitNexus 1.6.12 reports:

- `spawn_listener_with_origin_and_execution_gate`: **CRITICAL**, exact; 33 impacted symbols, 4 direct dependants, 8 affected processes, 5 modules.
- test-only `spawn_listener_with_origin`: **HIGH**, exact; 20 impacted symbols, 8 direct dependants, 4 affected processes, 3 modules.
- `RuntimeSupervisor::start`: LOW, lower-bound.
- `RuntimeSupervisor::status`: MEDIUM, lower-bound.
- `ToolContext::background_snapshot`: **HIGH**, lower-bound.
- `chat_domain::intercept`: LOW, exact.
- `RuntimeStatusDto`: LOW, exact.

The lower-bound results explicitly retain unresolved receiver-typing call sites. The overall candidate is therefore treated as CRITICAL-risk for review.

Svelte symbol indexing is an evidence limitation, not a PASS:

- run `35504168445`: exact `applyMcpRuntime` lookup not found;
- run `35504745045`: both targeted Svelte `Props` probes returned non-zero.

UI edits are instead covered by source review, `svelte-check`, production build and a focused Node contract test.

### Final change-impact evidence

Validation run `35506548418`, graph job: PASS.

```text
Changes: 22 files, 93 symbols
Affected processes: 26
Risk level: critical
```

Affected flows include Runtime start/status paths and ToolContext snapshot flows. This critical blast radius remains part of the acceptance record.

### Final source validation

Validation run `35506548418`, source job: PASS.

Frontend:

- `npm ci`: PASS;
- `npm run check`: PASS;
- `npm run build`: PASS;
- `node --test tests/offline-safe-ui.test.mjs`: **3/3 PASS**.

Rust:

- `cargo check --locked --all-targets`: PASS;
- `cargo test --locked`: PASS;
- primary library suite: **376 passed, 0 failed**;
- integration suites reported 22/22, 24/24, 6/6, 4/4, 9/9 and 16/16 PASS;
- `cargo rustc --locked --lib -- -D warnings`: PASS.

Focused regressions observed PASS:

- `workspace_pause_keeps_oauth_and_chat_owner_but_blocks_new_business_dispatch`;
- `oauth_refresh_and_owner_survive_workspace_execution_pause`;
- `pause_preserves_generation_origin_and_runtime_membership`;
- `stale_generation_cannot_pause_a_replacement_listener`;
- offline drain-control classification;
- typed non-OAuth `WORKSPACE_OFFLINE` error contract.

The HTTP regression also proves authorization remains stronger than availability: an unapproved chat receives `CHAT_AUTHORIZATION_REQUIRED` while execution is Offline, not `WORKSPACE_OFFLINE`.

### Security and lifecycle result

Synthetic/source evidence now supports all Round 3 invariants:

- OAuth refresh remains available while execution is paused;
- active chat ownership is not transferred or recreated by pause/resume;
- foreign chat remains blocked by existing exclusive semantics before availability is disclosed;
- intentional Offline is a business availability result, not an HTTP OAuth challenge;
- stale runtime generation cannot pause a replacement listener;
- pause/resume does not change the active runtime/tunnel membership or public origin;
- hard stop remains the existing listener+tunnel shutdown path.

### Truth boundary

Not established in Round 3:

- real ChatGPT reconnect-card behavior;
- installed Windows/Ubuntu lifecycle acceptance;
- survival of desktop-process exit;
- survival of machine sleep/power-off/network loss.

Those remain Round 5 gates. Round 3 therefore closes as a source/synthetic implementation milestone, not as proof that the original ChatGPT UI symptom is eliminated.


## 04 — Round 4 non-disclosing multi-user boundary

Date: 2026-09-20  
Branch: `hardening/offline-safe-multi-user-boundary`  
Validated source candidate: `145feec1b4d9af6a96057754ba6a6de072c0ab41`  
Draft PR: #22  
Result: **PASS for source/synthetic privacy gates; no production authorization change required.**

### Failure-first scope

Round 4 added privacy regressions before changing production behavior.

Covered boundaries include:

- foreign authenticated conversation while another chat owns the workspace;
- unapproved authenticated conversation while execution is Offline;
- Online vs Offline error precedence;
- repeated blocked authorization requests;
- control-plane `initialize`, `ping`, `tools/list`;
- async task list/get/cancel isolation across chat domains while Offline;
- draining denial metadata;
- recovery-required denial metadata.

### Focused impact evidence

Workflow run `35507344111`: PASS as tooling execution.

GitNexus 1.6.12 results:

- `ChatAuthorizer::status`: **UNKNOWN**, lower-bound; 3 receiver-typing call sites dropped.
- `ChatAuthorizer::request`: LOW, lower-bound; 5 impacted symbols, 4 receiver-typing call sites dropped.
- `ChatAuthorizer::admit`: **UNKNOWN**, lower-bound; 1 receiver-typing call site dropped and no caller resolved.
- chat-domain `intercept`: LOW, exact.
- MCP `handle_request`: LOW, exact.
- MCP `initialize_result`: LOW, exact.
- `server_info`: LOW, exact.

UNKNOWN/lower-bound results remain evidence limitations. They were not interpreted as proof of safety.

### Final change-impact evidence

Validation run `35507366052`, graph job: PASS.

```text
Changes: 8 files, 21 symbols
Affected processes: 0
Risk level: low
```

The low final change-impact reflects that Round 4 contains tests/docs/workflows only; the production auth/runtime behavior inherited from Round 3 was not modified.

### Final source validation

Validation run `35507366052`, source job: PASS.

Frontend:

- `npm ci`: PASS;
- `npm run check`: PASS;
- `npm run build`: PASS;
- offline-safe UI Node contract: **3/3 PASS**.

Rust:

- `cargo check --locked --all-targets`: PASS;
- `cargo test --locked`: PASS;
- primary library suite: **380 passed, 0 failed**;
- integration suites remained green;
- `cargo rustc --locked --lib -- -D warnings`: PASS.

Focused privacy regressions observed PASS:

- `foreign_owner_is_non_disclosing_online_and_offline`;
- `unapproved_offline_chat_and_control_plane_do_not_disclose_workspace_state`;
- `draining_denial_contains_no_owner_or_work_metadata`;
- `recovery_denial_contains_no_generation_binding_or_workspace_metadata`;
- `http_conversations_require_separate_grants_and_cannot_observe_each_others_jobs`;
- `all_business_tools_are_denied_before_approval_including_dangerous_mode`.

### Privacy result

Source/synthetic evidence now supports:

- B + Offline + owner A => `EXCLUSIVE_CHAT_LOCKED`, not `WORKSPACE_OFFLINE`;
- C + Offline business call => `CHAT_AUTHORIZATION_REQUIRED`, not `WORKSPACE_OFFLINE`;
- blocked foreign calls expose no owner grant id/fingerprint, profile id, workspace path or task id;
- 100 repeated foreign authorization requests create no new pending record for the profile;
- control-plane initialize/ping/tools-list contain no workspace path/profile id;
- task domains remain conversation-isolated while execution is Offline;
- draining/recovery denials do not expose generation/binding/work metadata.

No production defect was reproduced by the Round 4 matrix, so no production authorization semantics were changed.

### Shared-account truth boundary

This round proves server-side workspace confidentiality, not ChatGPT account-level connector invisibility.

The local server cannot prevent another person sharing the same ChatGPT account from seeing that an app/connector is installed in the host UI. Real host visibility and reconnect behavior remain Round 5 acceptance items.


## 05 — Round 5 cross-platform packaged engineering acceptance

Date: 2026-09-20  
Branch: `acceptance/offline-safe-round5`  
Validated packaged source candidate: `b1c190f29135dda6a80cb9af03883e8c6dcdd5a8`  
Independent Windows strict candidate: `5bd80a79e92c534c4b764bcc5d47015dd4476deb`  
Draft PR: #23  
Result: **ENGINEERING_CANDIDATE_PASS; real ChatGPT host acceptance remains DEFERRED.**

### Failure-first packaged evidence

Initial packaged run `35508467273` failed on both platforms for distinct, retained reasons.

Windows reached the final strict non-test library compile and exposed pre-existing platform-scoping warnings:

- conditional `mut` in `merge_default_allowed_commands`;
- Linux-only Secret Service helper compiled unused on Windows;
- three Linux-only `StartupFailureReason` variants compiled unused on Windows.

Ubuntu completed source regression and package build, then failed install smoke because a repository-relative `.deb` path was passed to apt and interpreted as a package name.

Focused GitNexus impact before the Windows source cleanup retained:

- `merge_default_allowed_commands`: **CRITICAL**, exact — 25 impacted symbols / 6 processes / 5 modules;
- Secret Service helper: LOW, exact;
- startup failure enum: UNKNOWN with no resolved callers, explicitly not treated as proof of safety.

A second Windows correction exposed one remaining Linux-only import warning. Each failure was classified and corrected with a bounded semantics-preserving change rather than retried blindly.

### Final packaged run

Workflow run `35509843023`: **SUCCESS** on Windows 2025 and Ubuntu 24.04.

#### Ubuntu

- frontend offline-safe UI contract: 3/3 PASS;
- Rust primary suite: 380 passed, 0 failed;
- integration suites: PASS;
- strict non-test library compile: PASS;
- Tauri Debian bundle: `Coding Tools MCP_0.6.0-rc.4_amd64.deb`;
- package id: `coding-tools-mcp`;
- package version: `0.6.0-rc.4`;
- package SHA-256: `4c6ff10665fcd73756cbdb5e4cb8ff36e9a390dcc9138a01eaddcad9aba9ad7a`;
- installed executable: `/usr/bin/coding-tools-mcp-desktop`;
- apt/dpkg install verification: PASS;
- purge/removal verification: PASS;
- CI artifact id: `10605615493`;
- artifact digest: `sha256:b638409e5a890380f0c75d636493048a0a576db7f7269607b9d90e9fc8429c0a`.

#### Windows

- frontend offline-safe UI contract: 3/3 PASS;
- Rust primary suite: 382 passed, 0 failed;
- integration suites: PASS;
- Tauri NSIS bundle: `Coding Tools MCP_0.6.0-rc.4_x64-setup.exe`;
- installer SHA-256: `576db69738bf90ecdd95b89613725bb3c2dc492e7aabb6e75919f0a055c6dd2c`;
- silent install: PASS;
- install location: `C:\Users\runneradmin\AppData\Local\Coding Tools MCP`;
- installed executable: `coding-tools-mcp-desktop.exe`;
- registered uninstaller found and silent uninstall completed: PASS;
- uninstall-registration removal verification: PASS;
- CI artifact id: `10605026829`;
- artifact digest: `sha256:366622590fdac780333931fcaf16474a111b852bd328b32b82b37d3f8e470870`.

Independent Windows strict run `35510062552`: SUCCESS.

### Lifecycle evidence retained across both packaged suites

Relevant source regressions observed green include:

- owner pause/resume and OAuth refresh while execution is Offline;
- long-running owner revocation/draining before successor;
- listener restart retaining a running async job and idempotency key;
- durable queued records never replaying commands after restart;
- network recovery requiring sustained Offline rather than one failed probe;
- FRP reconnect-loop detection and successful relogin recovery;
- active FRP route rehydration;
- tunnel rollback/identity invariants;
- Linux process-group drain confirmation.

These are SOURCE/PACKAGED engineering evidence, not ChatGPT-host UI evidence.

### Exact Round 5 diff review

Compared with the Round 4 plan base, Round 5 contains acceptance workflows/docs plus four narrow production-source portability cleanups:

- `src-tauri/src/commands/app_info.rs`;
- `src-tauri/src/error.rs`;
- `src-tauri/src/runtime/supervisor.rs` test cleanup;
- `src-tauri/src/tools/policy.rs`.

No OAuth token policy, chat lease, execution gate, MCP availability error, tunnel pause/resume semantic, or persistent data schema is changed in Round 5.

### Rollback

`round5-rollback.md` records:

- Round 5-only rollback;
- complete Round 3 feature rollback boundary;
- additive/ephemeral data compatibility;
- no release/tag/signing withdrawal required.

### Engineering gate result

```text
engineering candidate: ENGINEERING_CANDIDATE_PASS
real ChatGPT reconnect UX: UNCONFIRMED_ON_REAL_HOST
shared-account connector visibility: UNCONFIRMED_ON_REAL_HOST
```

No Git tag, GitHub Release, production signing secret, or public installer release was created.

### Remaining host gate

The dedicated real ChatGPT test connector remains deferred by user choice. The exact procedure is preserved in `round5-host-deferred-procedure.md`.

Until that procedure runs, ISSUE-005 remains open and the project must not claim `HOST_VALIDATED` or `DONE`.


## 06 — Streamable HTTP Origin hardening

Date: 2026-09-20  
Branch: `security/mcp-origin-validation`  
Draft PR: #25  
Result: **SOURCE + CROSS-PLATFORM + PACKAGED PASS; real-host compatibility remains DEFERRED.**

### External reference review

The hardening design was compared against:

- MCP 2025-06-18 / 2026-07-28 specifications;
- MCP TypeScript SDK;
- official MCP Rust SDK;
- `MikkoParkkola/mcp-gateway`;
- PMCP and chuk-mcp-rs.

The review changed the original hostname-only public-Origin proposal to exact scheme + host + effective-port comparison while keeping missing-Origin compatibility for server-to-server clients.

### Failure-first evidence

Run `35513270637` demonstrated the gap before repair:

```text
4 focused tests
1 passed
3 failed
```

Foreign Origin, stale managed Origin, and OAuth control-plane Origin requests were accepted with HTTP 200.

Repair run `35513449933` fixed production behavior but exposed one invalid test assertion around the literal string `null`; that test defect was recorded and corrected rather than hidden.

### Impact

Focused pre-edit run `35513186585`:

- listener `serve`: **CRITICAL**, exact;
- `PublicOrigin::snapshot`: **CRITICAL**, lower-bound;
- router-registered handlers: UNKNOWN due graph-registration boundary.

Final detect-changes in run `35516677404`:

```text
11 files
57 symbols
0 affected processes
aggregate risk: low
```

The low aggregate result does not replace the focused CRITICAL evidence.

### Focused security result

Run `35516439406`: PASS.

```text
origin_security_tests
4 passed
0 failed
```

Coverage includes:

- missing/local Origin;
- exact current public Origin;
- live public-origin rotation;
- stale public Origin;
- wrong public scheme/port;
- foreign/malformed/opaque Origin;
- duplicate Origin headers;
- invalid CORS preflight;
- MCP GET/POST;
- OAuth discovery/authorize/token control routes;
- non-reflective 403 envelope.

### Windows timing isolation

Run `35513687191` produced one unrelated owner-drain startup timeout at 8056 ms under parallel Windows CI.

No product timeout was weakened.

Run `35516343223` executed the exact test alone:

```text
drain-startup ready after 895ms
1 passed
0 failed
```

The full workflow was changed to keep the test outside the Windows parallel batch.

### Final full source validation

Run `35516677404`: SUCCESS.

Ubuntu:

- 384 primary tests passed;
- Origin matrix green;
- integration suites green;
- strict compile green.

Windows:

- 385 primary tests passed with the one drain case intentionally filtered from the parallel batch;
- isolated drain case passed with readiness at 69 ms;
- Origin matrix green;
- integration suites green;
- strict compile green.

Frontend contract: 3/3 PASS on both platforms.

### Final packaged validation

Run `35516447042`: SUCCESS.

Ubuntu:

- package SHA-256 `54920e4a565fe031129249e3bab0af20debbcf453842fbe2d58215db6e704357`;
- install/executable/purge PASS;
- artifact digest `sha256:b511ad9caa315b221e640c92209696782b3473048ce83d2a09e7a4b49479bc43`.

Windows:

- installer SHA-256 `269d5aa3b911ffddd92b8f16c04a2db1d5bddd6d00807d4b7b04e9954c7af123`;
- silent install/executable/uninstall PASS;
- artifact digest `sha256:6c9cb3021301b62fe55b1f5e589c85a8dd3161c592894e1bfd725b71a61af895`.

### Result

ISSUE-006 closes at source/security acceptance.

The project remains:

```text
engineering candidate: PASS
Origin boundary: SOURCE/PACKAGED PASS
real ChatGPT reconnect UX: UNCONFIRMED_ON_REAL_HOST
real ChatGPT Origin compatibility: UNCONFIRMED_ON_REAL_HOST
```

Next direct product task: ISSUE-008 intent-aware lifecycle UX. ISSUE-007 Host/:authority enforcement waits for tunnel-topology evidence.


## 07 — Intent-aware lifecycle UX

Date: 2026-09-20  
Branch: `ux/offline-safe-intent-controls`  
Draft PR: #26  
Result: **SOURCE/UX PASS; real ChatGPT reconnect outcome remains DEFERRED.**

### Problem confirmed

Although Round 3 separated connector reachability from workspace execution in the backend, the workspace UI still presented the generic running MCP power button as `停止`, directly calling `stopRuntime`.

Pause/Resume existed in a separate panel, so the normal visible action could still intentionally tear down listener+tunnel reachability.

### Failure-first contract

Run `35517398463`:

```text
5 tests
1 passed
4 failed
```

Failures confirmed:

- no explicit Start Connector path;
- no confirmation-gated Stop Connector path;
- execution panel did not own connector Start/Stop actions;
- generic ServicePanel still rendered the MCP hard-stop button.

Actions start/stop behavior passed and was preserved.

### Impact limitation

Run `35517373147`:

- GitNexus query resolved pause/resume TypeScript API symbols;
- Svelte symbol probes for page/component functions/Props all returned non-zero;
- exact grep review located the only UI `stopRuntime` call in the MCP toggle and the separate pause/resume calls.

The parser limitation is retained rather than relabeled as low risk.

### Implementation

MCP UI now uses one intent-aware lifecycle panel:

```text
stopped       -> Start Connector
running online -> Pause remote execution
running offline -> Resume remote execution
running        -> secondary Stop Connector
```

Hard Stop:

- calls the unchanged backend `stopRuntime`;
- requires explicit confirmation;
- states that MCP/OAuth listener and public tunnel will close;
- directs temporary-work intent to Pause instead.

The generic ServicePanel toggle is hidden for MCP and unchanged for Actions.

### Focused verification

Run `35517680310`: Ubuntu + Windows contract PASS.

### Full frontend validation

Run `35517763406`: SUCCESS.

Ubuntu:

- Svelte check: 0 errors / 0 warnings;
- production build: PASS;
- existing offline-safe UI contract: 3/3;
- new intent-aware UI contract: 5/5.

Windows:

- Svelte check: 0 errors / 0 warnings;
- production build: PASS;
- existing offline-safe UI contract: 3/3;
- new intent-aware UI contract: 5/5.

Final detect-changes:

```text
11 files
16 indexed symbols
0 affected processes
aggregate risk: low
```

This aggregate graph result does not remove the known Svelte indexing uncertainty.

### External-reference result

MCPJam and the official MCP Inspector independently distinguish transport connect/disconnect from conversation/server enablement or session state. This supports making Pause/Resume the ordinary temporary-work intent and reserving disconnect/stop for explicit connector lifecycle changes.

### Truth state

```text
engineering candidate: PASS
Origin boundary: PASS
intent-aware lifecycle UX: SOURCE/UX PASS
real ChatGPT reconnect behavior: UNCONFIRMED_ON_REAL_HOST
```

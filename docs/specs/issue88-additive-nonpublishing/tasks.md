# Tasks: authenticated FINAL artifact consumer

## 交付物清单

New modules only: snapshot, safe I/O, archive, transport, contracts, explicit noncloud validation, terminal finalization, orchestration and the mandatory-fixture test runner; split any module over 500 lines. New matching fixture/test modules (at most 500 lines each), two workflows and these three specs. No existing tracked files modified. The actual additive file inventory is recorded below.

## 任务列表

## 1. Authenticate selected CI snapshot (FR-1, FR-2; design sections 1–3)

- [x] Implement rc_consumer_snapshot.py (budget 450 lines) with immutable trusted producer and repeated full snapshot fence
- Evidence: scripts/release_tag_gate.py:145 selects latest run without a success filter; lines 169–193 bind exact current-attempt jobs. scripts/final_rc_evidence.py:61 uses exact candidate branch grammar
- [x] Add snapshot fixtures and negatives (budget 450 lines per module)

## 2. Bound untrusted data (FR-2, FR-3; design section 4)

- [x] Implement rc_consumer_io.py, rc_consumer_archive.py and rc_consumer_transport.py (budget 450 each), with data-only standard parsers and nofollow roots
- Evidence: scripts/release_tag_gate.py:198 validates metadata but digest remains optional and bytes unverified; new consumer strengthens without editing it
- [x] Add adversarial archive/transport tests (budget 450 lines per module)

## 3. Recompute explicit producer contracts (FR-4; design section 5)

- [x] Implement rc_consumer_contracts.py and rc_consumer_noncloud.py (budget 450 each), leaving all producer helpers unchanged
- Evidence: scripts/release_dependency_contract.py:58 current_producer reads actual process context; consumer must not invoke it. scripts/rc_native_gate.py:21 verifies explicit installed-native identity
- [x] Add synthetic full fixture and contract negative parity (budget 450 lines per module)

## 4. Emit sanitized nonpublishing plan (FR-5, FR-6; design section 6)

- [x] Implement rc_artifact_consumer.py (budget 350), rc-artifact-consumer.yml and rc-artifact-consumer-checks.yml (budget 200 each)
- Evidence: scripts/final_rc_evidence.py:162 bundle re-enters current-producer validators; new consumer must orchestrate explicit validation without this call
- [x] Add workflow/output/orchestration tests (budget 450 lines per module)

## 5. Validate acceptance and review (all FRs)

- [x] Run each focused suite after increment, complete consumer suite and current required producer tests
- [x] Compile Python, check diff and all new line counts; inspect the staged change graph; obtain independent frozen-tree code review
- [ ] Publish the reviewed engineering commit and run exact-source hosted fixture tests
- [ ] Establish separately reviewed authenticated storage-host and byte/ZIP transport proof before enabling live transport
- [ ] Validate a genuine eligible first-attempt FINAL DAG against the selected source, approved version, reviewed manifest and existing lightweight tag

## 需求覆盖矩阵

FR-1 → task 1; FR-2 → tasks 1–2; FR-3 → task 2; FR-4 → task 3; FR-5 → task 4; FR-6 → tasks 4–5. Every file is additive and capped at 500 lines. Release eligibility remains tracked in the [full-scope RC ledger](../../releases/next-rc-ledger.md) and [Issue #88](https://github.com/Eswink/coding-tools-mcp/issues/88).

## 文件变更清单

The additive file list and per-file budgets are specified in tasks 1–4 above. No tracked producer file changes are permitted; the final test-module splits and actual counts are listed below.

## Local implementation checkpoint (2026-10-01 UTC)

30 additive files; zero existing source modifications. Local full fixture gate: 159 tests, zero skips with the checksum-pinned official GLib source archive. Required unchanged producer suites: 194 tests plus 14 original stable-version regressions. Historical stable_release_v050 suite has its unchanged baseline version-expectation failure and is outside this increment. Hosted fixture run, real storage transport proof and genuine eligible FINAL artifact remain unestablished; production storage hosts remain empty and fail closed.

Terminal close/withdrawal and supported workflow-context regressions are included. Independent local code review passed after correcting terminal-failure handling and step-level workflow context. Documentation reconciliation also requires exact-tree review before publication. No local check substitutes for the pending hosted, transport or genuine FINAL gates.

Actual files (each at most 500 lines):

- .github/workflows/rc-artifact-consumer-checks.yml
- .github/workflows/rc-artifact-consumer.yml
- docs/specs/issue88-additive-nonpublishing/design.md
- docs/specs/issue88-additive-nonpublishing/requirements.md
- docs/specs/issue88-additive-nonpublishing/tasks.md
- scripts/rc_artifact_consumer.py
- scripts/rc_consumer_archive.py
- scripts/rc_consumer_archive_tests.py
- scripts/rc_consumer_contract_boundaries_tests.py
- scripts/rc_consumer_contract_numeric_tests.py
- scripts/rc_consumer_contract_parity_tests.py
- scripts/rc_consumer_contract_tests.py
- scripts/rc_consumer_contracts.py
- scripts/rc_consumer_fence_tests.py
- scripts/rc_consumer_fixtures.py
- scripts/rc_consumer_io.py
- scripts/rc_consumer_io_tests.py
- scripts/rc_consumer_noncloud.py
- scripts/rc_consumer_output_tests.py
- scripts/rc_consumer_plan_tests.py
- scripts/rc_consumer_snapshot.py
- scripts/rc_consumer_snapshot_fixtures.py
- scripts/rc_consumer_snapshot_tests.py
- scripts/rc_consumer_source_tests.py
- scripts/rc_consumer_test_runner.py
- scripts/rc_consumer_transport.py
- scripts/rc_consumer_transport_tests.py
- scripts/rc_consumer_workflow_tests.py
- scripts/rc_consumer_finalize.py
- scripts/rc_consumer_finalization_tests.py

## Finite deadline bugfix tasks (2026-10-04; separate Plan)

Historical checkboxes above describe PR89's original increment, not this fix. Engineering base is exact unmerged PR89 `6b6ad879` / tree `29cbb919`. No integration selection is approved by this preparation.

- [x] Read AGENTS, Probe4.0.1 Skill and current project context; create genuinely new finite bugfix Plan
- [x] Bind unchanged source and preserved original 0.20s/0.7593s local HTTP observation; run unchanged 12-test fake-opener transport baseline (12 pass, no skips)
- [x] Finish fresh exact-symbol impacts/manual call graph, source-bound requirements/design/test matrix and check_spec; obtain independent exact-plan review and root approval
- [x] Implement only existing transport plus one private byte worker after approval; keep both public signatures and source/host/finalization contracts
- [x] Adapt shared existing transport fixture and add one supervised-boundary test module; preserve plan/finalization test callers without edits
- [x] Verify actual header/body trickle cancellation, startup/partial IPC, error/cancel, HTTP close, DONE-then-hang, abnormal exit, file-I/O lateness and uncertain terminate/kill/reap cases
- [ ] Run focused tests, full zero-skip consumer fixture runner and unchanged producer suites; validate syntax, line caps, default-host no-spawn, exact diff and independent staged review
- [ ] Parent decides source integration and publication separately; reuse existing hermetic CI and verify exact candidate head/tree without adding a workflow

Coverage: FR-7 -> supervisor deadline tests; FR-8 -> cancel/cleanup fault matrix; FR-9 -> parent integrity, DONE/EOF/exit and consumer parser/plan exclusion; FR-10 -> unchanged policy regressions/default-host no-spawn and exact frozen exclusions; FR-11 -> Ubuntu24/Python3.12 exact-source run and documented OS limits. The full finite matrix and source bindings are in the review preparation evidence, not assertions of completed candidate tests.

CI reuse: existing `rc-artifact-consumer-checks.yml` discovers `rc_consumer*_tests.py`, requires the official checksum-pinned GLib data fixture, >=159 tests and zero skips, then runs unchanged producer regressions. Existing push prefixes exclude local `fix/artifact-transport-deadline`; the approved `feat/rc-final-artifact-consumer-deadline-20261004` name matches without workflow edits. A fresh remote matching-ref query returned an empty list before the local rename; no remote ref or publication was created. Alternatively a PR merge SHA requires exact candidate-tree equality checks and cannot silently count as head-source evidence. No FINAL workflow is part of testing.

Finite lifecycle bug tracking: [Issue107](https://github.com/Eswink/coding-tools-mcp/issues/107); Issue88 remains the broader consumer/release scope.

Local candidate checkpoint (Issue107, 2026-10-04): original159 consumer tests plus15 new lifecycle tests pass (174 total), with all194 unchanged producer tests and14 version tests also passing;382 local tests, zero skips. Earlier candidate fixture-cleanup instrumentation failures were fixed only in the shared test adapter; no finalization assertions/code changed. Short-cleanup terminate-failure testing exposed and corrected lack of reserved kill/reap time. The retained original0.20s/0.7593s header witness is untouched. A fresh same-loopback scenario at0.5s budget measured baseline headers4.0323s vs supervised candidate0.5020s (reaped); baseline slow-body0.5052s is a passing control, preserved at candidate0.5021s. This remains local HTTP/fake API/token evidence, not TLS or authenticated GitHub acceptance. Final frozen-tree review and hosted CI remain pending.

## Finite exact-host adoption tasks (2026-10-04; separate source-only Plan)

The historical checklists and observations above are retained rather than recast as current successes. This increment uses integrated PR89 `6dba87ceb3551b08fd98d0a49e649c3d02026d02` / tree `2f6b775ff396468de49802eed12552b6d626d2fc`. It explicitly supersedes only FR-10's historical production-default-empty hold as described in the new requirements/design addenda; empty-policy rollback and all other fences remain mandatory.

- [x] Bind approved exact-host review, AGENTS/Probe4.0.1/project context, remote-name absence and an isolated local worktree at the integrated base; create a finite source-adoption Plan
- [x] Complete existing-spec amendment, passing check_spec and fresh exact-symbol M impacts before runtime edits; retain manual HIGH risk/UNKNOWN graph coverage
- [x] Edit only both compiled host declarations/adjacent comments and add unpatched compiled-default/exact-host adversarial tests in the existing transport test file
- [x] Prove inverse-runtime byte equality, original12 assertion AST preservation, unchanged supervisor/producer/workflow inventory and six-path/line-cap limits
- [x] Run full174-existing-plus-new consumer,194 producer,14 version tests with checksum-pinned official GLib fixture and zero skips; record actual loaded/run counts
- [ ] Freeze exact staged diff/tree/manifest, complete staged GitNexus/code review and obtain independent review before parent-owned publication
- [ ] Separately authorize and establish actual default-worker live compatibility; currently UNPROVEN and outside this source-only Plan

Coverage: FR-12 -> compiled-policy equality/URL and synthetic wire tests plus unchanged policy regressions; FR-13 -> inverse-byte/AST/inventory checks; FR-14 -> explicit historical912-byte nonFINAL proof/source/expiry binding and independent live gate. FR-7..11 continue to use the unchanged full supervisor/lifecycle suite; FR-10's explicit empty-policy rejection tests remain intact. The finite source Plan ends at frozen-candidate validation/review or a concrete blocker; live validation, canonical integration, FINAL and release work are separate.

Local source-adoption checkpoint: CPython3.12.14 passed180 consumer tests (174 existing +6 compiled-policy additions),194 unchanged producer and14 version regressions,388 total with zero skips. The official GLib0.18.5 crate SHA256 is `233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`. Inverse runtime reconstruction, all original12 transport test ASTs, supervisor bytes, syntax and six-path line caps pass. New tests first failed against the empty-default base and then passed after only declaration/comment adoption. This is local synthetic/regression evidence; frozen independent review, hosted CI and separately authorized actual-worker live compatibility are not claimed by these results.

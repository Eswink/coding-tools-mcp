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

# Tasks: Windows owned-Job completion (#101)

## 任务列表

- [x]1.1 Reconcile current PR98/PR100 source and create independent issue, no leak/admission claim (FR-1..4)
  - 证据块: Baseline c3fcfb1; issue #101; runtime blobs match bdeefba; no PR100 dependency
- [x]1.2 Read project context, fresh exact-symbol impact, manual HIGH caller review and finite scope approval (FR-1..4)
  - 证据块: Root approved separate retaining method, exact legacy/PTy/Unix preservation, private supervisor seam and mechanical extraction
- [ ]2.1 Pass specification gate and extract existing start/I/O/tests within500line files (FR-1,FR-3)
  - 证据块: Preserve original helper bodies except declared joined/completion changes; record mechanical proof
- [ ]2.2 Add borrowed request/owned Job query and opt-in publication proof (FR-1..3)
  - 证据块: exact retained-method/query and supervisor gate diff
- [ ]3.1 Add deterministic query/order/sticky uncertainty tests against real supervisor (FR-2..4)
- [ ]3.2 Add native private-pipe self-descendant, retained identity and immediate owned-handle checks (FR-2,FR-4)
- [ ]3.3 Run exact-source full Windows/Ubuntu local-agent and PTY regressions (FR-4)
  - 证据块: Locked cargo test/check, fmt and Clippy; source/tree/toolchain metadata; nonzero focused counts
- [ ]4.1 Freeze diff, independent review, staged detect_changes and gencommit (FR-4)
- [ ]4.2 Publish small additive commits/draft PR to integration base and verify remote/source-bound CI (FR-4)
  - 证据块: No main merge/tag/release, no cancelled PR98 retry; Windows admission stays SANDBOX_REQUIRED

## 交付物清单

Borrowed Job request/query, private bounded publication gate, preserved legacy paths, deterministic and native regressions, exact-source CI and review records.

## 需求覆盖矩阵

FR-1:1.1/2.1/2.2/3.3; FR-2:2.2/3.1/3.2; FR-3:2.1/2.2/3.1; FR-4:1.2/3.1/3.2/3.3/4.1/4.2.

## 文件变更清单

services/local-agent/src/process.rs; process_supervisor.rs(new); process_tests.rs(new mechanical extraction); process_tree_windows.rs; process_completion.rs(new); process_completion_tests.rs(new); services/local-agent/src/bin/process_fixture.rs; services/local-agent/tests/windows_job_completion.rs(new); .github/workflows/local-agent-runtime.yml; docs/specs/windows-owned-job-completion/{requirements,design,tasks}.md. All unspecified production/test files remain unchanged.

## 证据块

1.1 current-source reconciliation/issue101;1.2 exact graph and independent manual review;2.1 checked spec and mechanical-body comparison;2.2 source-bound diff;3.1 named injected supervisor tests;3.2 original-owned Job and process-handle native results;3.3 full Windows/Ubuntu test outputs/counts;4.1 frozen tree/staged graph/gencommit;4.2 verified remote SHA/tree/CI artifacts. Unrun gates stay explicitly pending.

## Safe incomplete boundary

- [ ]5.1 Reject unsupported Windows strengthening before permit/spawn; distinguish InvalidSpec from occupied Capacity and missing-program Spawn
  - 证据块: unchanged positive tests plus a separate pre-spawn guard test
- [ ]5.2 Run all targets with --no-fail-fast and preserve unmet positive gates as failures, not skips or expected passes
  - 证据块: exact source/run/artifact evidence; Issue101 remains open
- [ ]5.3 Isolate the independent consumed-JoinHandle correction on a c3-based branch; do not call its green regressions Windows feature completion
  - 证据块: separate issue/PR and unchanged baseline production failure witness

Status: FEATURE INCOMPLETE. Tasks3.3 and4.2 cannot be marked complete for Windows strengthening merely because the unsupported guard works. No census implementation, sandbox/admission change or release is authorized.

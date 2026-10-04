# Tasks: isolated process I/O join-once correction (#103)

## 任务列表

- [x]1.1 Create isolated c3-based worktree and read current project/Probe context (FR-1..4)
  - 证据块: immutable source/tree/process blob verified; no PR98/PR102 mutation
- [x]1.2 Obtain fresh exact-symbol context/impact and identify manual HIGH risk (FR-1,FR-2)
  - 证据块: exact graph/callers and explicit Rust reexport limitations
- [x]1.3 Obtain independent pre-edit review and pass specification gate (FR-1..4)
  - 证据块: parent finite HIGH review and current check_spec result
- [x]2.1 Mechanically extract supervisor and original unit tests; compare original bodies/tokens (FR-2)
  - 证据块: source-bound original method/helpers/test token hashes
- [x]2.2 Remove consumed handles immediately and clean up only unconsumed handles (FR-1,FR-2)
  - 证据块: exact join_io/join_once diff with synchronous take before later await
- [x]2.3 Add four identical baseline/candidate test bodies and provenance gates (FR-3,FR-4)
  - 证据块: shared test bytes and strict per-test panic witness validation
- [ ]3.1 Run real immutable-production baseline witness on Windows/Ubuntu (FR-3)
  - 证据块: successful build, exactly three named repeated-poll failures and one control pass, raw output/hashes
- [ ]3.2 Run actual candidate fmt/Clippy/full locked tests/check on both native runners (FR-4)
  - 证据块: exact source/tree, positive inventory=result counts, no failures/ignored/filtered tests
- [ ]4.1 Freeze eight-path diff, independent exact review, staged graph and gencommit (FR-4)
  - 证据块: candidate tree and source-bound review/graph/commit results
- [ ]4.2 Obtain separate publication approval, publish additively, verify remote/source-bound CI (FR-4)
  - 证据块: root approval, verified remote SHA/tree and exact native runs

## 交付物清单

Narrow join-once ownership fix, mechanically preserved original bodies/tests, four regression bodies, bounded unchanged-baseline witness, full exact-source dual-OS evidence and review records.

## 需求覆盖矩阵

FR-1:1.2/1.3/2.2/2.3/3.2; FR-2:1.2/1.3/2.1/2.2/3.2; FR-3:1.1/1.3/2.3/3.1; FR-4:1.1/1.3/2.3/3.2/4.1/4.2.

## 文件变更清单

services/local-agent/src/process.rs; services/local-agent/src/process_supervisor.rs; services/local-agent/src/process_tests.rs; services/local-agent/src/process_io_join_tests.rs; .github/workflows/local-agent-runtime.yml; docs/specs/process-io-join-once/requirements.md; docs/specs/process-io-join-once/design.md; docs/specs/process-io-join-once/tasks.md.

## 证据块

Baseline c3fcfb1/tree2066e8ae/process blob47bf41f; fresh exact graph plus manual caller review; mechanical function/token proofs; identical regression test hash and baseline production-prefix/overlay hashes; raw native baseline and candidate commands/results; frozen candidate tree and exact-source CI metadata. Native tests are pending until actual execution. Source syntax checks alone never satisfy3.1/3.2. Windows Job completion, sandbox/security, physical host, deployment and release gates are unchanged.

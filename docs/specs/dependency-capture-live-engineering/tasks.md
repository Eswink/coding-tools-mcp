# 任务清单：dependency-capture-live-engineering

## 概述
Add only the independent engineering execution-evidence lane approved for local preparation.

## 交付物清单（Scope-lock）
Six new files, zero modified existing files. Helper and tests each below 300 lines; workflow approximately 130; each specification below 100. Approximately ten new helper functions and one new test class. Exact file list is in design.md.

## 任务列表
- [x] 1.1 Inspect unchanged collector and shared verifier impact
  - 证据块: scripts/release_dependency_capture.py:24 captures three locks and invokes the pinned GLib verifier; scripts/release_dependency_contract.py:206 hard-codes final producer/policy requirements.
  - 涉及文件: three specifications, below 100 lines each; no existing implementation edits.
  - 需求: FR-1, FR-2, FR-3; 设计: 技术方案、风险评估
- [x] 2.1 Add additive collect and independent integrity verification commands
  - 证据块: scripts/exact_build_audit.py:264 binds a clean exact source; scripts/release_dependency_contract.py:181 exposes the existing independent desktop_source_proof.
  - 涉及文件: scripts/engineering_dependency_capture.py, below 300 lines.
  - 需求: FR-1, FR-2; 设计: 数据模型与接口、设计决策
- [x] 2.2 Add deterministic adverse-exit, drift and artifact-tamper regressions
  - 证据块: scripts/release_dependency_capture_tests.py:30 mocks commands; its GLib case stops at missing verifier. Hosted live evidence must remain distinct.
  - 涉及文件: scripts/engineering_dependency_capture_tests.py, below 300 lines.
  - 需求: FR-1, FR-2, FR-3; 设计: 测试策略
- [x] 2.3 Add exact-branch read-only capture and independent download verification
  - 证据块: .github/workflows/final-rc-packages.yml:158 invokes noncloud collection behind the source/cloud final gate; the new lane must not invoke that workflow.
  - 涉及文件: .github/workflows/issue85-dependency-capture.yml, approximately 130 lines.
  - 需求: FR-1, FR-2, FR-3; 设计: 技术方案
- [ ] 3.1 Verify local contracts, independent review and exact hosted evidence when authorized
  - 证据块: scripts/verify_glib_backport.py:281 invokes real cargo metadata; local Cargo is unavailable. Existing mocked tests cannot establish this path.
  - 涉及文件: only new tests/workflow/specifications and external evidence logs.
  - 需求: FR-1, FR-2, FR-3; 设计: 测试策略

## 检查点
Require check_spec before implementation. Require independent implementation review, GitNexus staged detect-changes and Probe gencommit before requesting commit/push approval. No GitHub writes before parent review. Hosted capture/artifact verification is pending and final-source recapture remains necessary.

## 需求覆盖矩阵
FR-1: 1.1, 2.1, 2.2, 2.3, 3.1. FR-2: 1.1, 2.1, 2.2, 2.3, 3.1. FR-3: 1.1, 2.2, 2.3, 3.1.

## 文件变更清单
Only the six new paths listed in design.md are authorized. Existing runtime, collectors, policies, manifests, locks and final workflows remain byte-identical to the base.

Local preparation: 16 new wrapper tests, 6 unchanged collector tests, 29 dependency-contract tests, 22 exact-build tests, 16 final-evidence tests and 39 GLib adversarial/source tests passed (128 total). The GLib tests used a freshly downloaded official crate with the exact pinned SHA-256. This verifies source/fixture contracts, not live Cargo metadata/audit execution. Independent implementation review approved the 261-line helper, 288-line tests and 132-line workflow; actionlint passed. Hosted capture and downloaded verification remain unrun, pending explicit commit/push review.

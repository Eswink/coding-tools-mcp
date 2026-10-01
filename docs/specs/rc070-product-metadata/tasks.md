# 任务清单：rc070-product-metadata

## 概述
Deliver only the independent non-final version increment under the existing product/component release contracts.

## 交付物清单（Scope-lock）
Five new files and ten modified files, fifteen total. New files are the engineering guide, exact-branch validation workflow and these three specifications. Modified files are the seven authoritative metadata files, two engineering workflow constants and scripts/rc_version_gate_tests.py. The test module remains below 350 lines and new workflow below 250; no runtime functions are changed.

## 任务列表
- [x] 1.1 Validate scoped requirements and pre-edit consumer impact
  - 证据块: docs/specs/cloud-release-artifacts/requirements.md:11 requires desktop six-field RC and gateway package/self-lock equality while preserving independent libraries; scripts/rc_version_gate.py:30 reads desktop authority.
  - 涉及文件: three specifications, each below 100 lines. Run check_spec before implementation.
  - 需求: FR-1, FR-2, FR-3; 设计: 技术方案、设计决策与风险评估
- [x] 2.1 Add deterministic drift and byte-transition regressions, retaining original fixtures
  - 证据块: scripts/rc_version_gate_tests.py:16 has two original tests; scripts/cloud_release_bundle.py:30 validates component self-locks and product authority.
  - 涉及文件: scripts/rc_version_gate_tests.py, below 350 lines. Demonstrate original-source failure and expected transition positives/negatives.
  - 需求: FR-1; 设计: 技术方案、测试策略
- [x] 2.2 Align eight product fields and two engineering expectations without dependency churn
  - 证据块: package.json:3 and src-tauri/Cargo.toml:3 are 0.6.0-rc.4; services/cloud-gateway/Cargo.toml:3 is 0.1.0; Linux/Windows engineering workflows have fixed RC_VERSION values.
  - 涉及文件: seven metadata files (version tokens only) and two workflow constants (one line each).
  - 需求: FR-1; 设计: 技术方案
- [x] 2.3 Add bounded engineering guide and exact-source read-only CI
  - 证据块: scripts/release_preflight.py requires a version-matched guide but returns release-inputs-only; existing CLI implementations derive CARGO_PKG_VERSION and retain their capability suffixes.
  - 涉及文件: guide below 100 lines and new CI workflow below 250 lines; pinned actions and exact branch/repository, three 35-minute jobs.
  - 需求: FR-2, FR-3; 设计: 技术方案、数据模型
- [ ] 3.1 Verify, review and retain exact-source engineering results
  - 证据块: docs/releases/legacy-source-gates.md:25 requires reviewed complete source before manual freeze; this task does not create that manifest.
  - 涉及文件: existing validation entry points and scoped evidence only; stage/review before commit/push. Final hosted proof remains pending until the exact new head completes.
  - 需求: FR-1, FR-2, FR-3; 设计: 测试策略

## 检查点
Require check_spec, actual local tests/frontend checks, independent staged review and Probe review; retain blocked/unrun results honestly. Require exact-head hosted Windows/Ubuntu metadata and binary evidence before declaring the engineering increment verified.

Local implementation checks: 111 Python contract tests pass; both original RC test ASTs are unchanged. npm ci, Svelte check (zero errors/warnings), build, 233 full frontend tests and 147 gateway/delivery tests pass on Node 24.19.0. Three-workflow actionlint passes. The twelve-file raw-byte proof passes; preflight reports release-inputs-only with source_verified=false on the uncommitted tree. The cloud bundle CLI correctly requires GitHub CI identity and was not represented as a local CLI pass. Hosted Node 22/Rust 1.98.1 and compiled-binary proof remain pending; local Cargo is unavailable. Final review/commit and exact-head hosted results are not yet complete.

## 需求覆盖矩阵
FR-1: tasks 1.1, 2.1, 2.2, 3.1. FR-2: tasks 1.1, 2.3, 3.1. FR-3: tasks 1.1, 2.3, 3.1.

## 文件变更清单
The fifteen explicit files in design.md are the complete allowed scope. Preserve independent component manifests/locks, pnpm lock, historical reconstruction workflows, old guides/receipts and all production source.

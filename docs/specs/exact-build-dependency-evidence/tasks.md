# 任务清单：exact-build-dependency-evidence
## 概述
Implement one additive verifier/collector and adversarial tests; do not integrate parent audit gate.
## 交付物清单（Scope-lock）
Seven new files: two Python scripts, one integration proposal, one isolated-CI-prefix/manual engineering workflow and three specs. No existing production symbol or workflow edited. Helper budget500lines, tests300lines; split if scope exceeds these bounds.
## 任务列表
- [ ] 1.1 Capture exact source/build/audit evidence with unmodified raw reports
  - **证据块**: Cargo external-tools JSON specification defines compiler-artifact package_id/features/fresh and build-finished; existing gateway Cargo.toml defines four bins
  - **涉及文件**: scripts/exact_build_audit.py (500lines)
  - _需求: FR-1,FR-2,FR-3_ ｜ _设计: 技术方案_
- [ ] 2.1 Reject altered or incomplete package and provenance evidence
  - **证据块**: issue85 raw report has rsa0.9.10/RUSTSEC-2023-0071; all-target selected tree has no rsa; four roots plus a count cannot detect deleted dependency events
  - **涉及文件**: scripts/exact_build_audit_tests.py (300lines)
  - _需求: FR-4_ ｜ _设计: 测试策略_
- [ ] 3.1 Document separate raw and exact-build release meaning without changing gate
  - **证据块**: final_rc_evidence.audits currently expects rawzero; helper adoption must be explicit and never describe retained rawfinding aszero
  - **涉及文件**: docs/releases/exact-build-audit-integration.md (120lines)
  - _需求: FR-3,FR-4_ ｜ _设计: 设计决策_
## 检查点
- [ ] Specs valid before implementation
- [ ] Deterministic negative tests and manual source review
- [ ] Exact native source/CI capture remains separately tracked
## 需求覆盖矩阵
|需求 ID|任务|设计章节|
|---|---|---|
|FR-1|1.1|技术方案|
|FR-2|1.1|技术方案|
|FR-3|1.1,3.1|设计决策|
|FR-4|2.1,3.1|测试策略|
## 文件变更清单
Seven additive paths above; no Cargo manifests/locks, existing workflows or parent gate changed. New isolated-CI-prefix/manual engineering workflow produces proof, never release approval.
## 检查清单
- [x] Requirement links and scope recorded
- [ ] All local checks complete

- [x] Parent review corrections: strict numeric/schema JSON, exact GitHub repository/toolchain binding, fresh official acquisition provenance, and negative contracts
- [ ] Hosted actual-product proof and parent final-contract review remain open

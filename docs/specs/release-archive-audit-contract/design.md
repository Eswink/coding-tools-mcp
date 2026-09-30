# 设计文档：release-archive-audit-contract

## 概述
Covers FR-1, FR-2, FR-3 and NFR-1 through NFR-3. Existing exact-build invariants remain unchanged.

## 技术方案
### 技术选型
Use a small Python adapter with existing strict parsers, complete Cargo verifier and archive validation. CI outputs, not downloaded sidecars, supply trust anchors.
### 架构设计
source/version/integration -> cloud build -> process -> image -> contracts -> native packages -> installed acceptance -> bundle.
In parallel after source approval, the same-commit issue40 reusable topology workflow builds separate engineering binaries and runs all 14 cases; its successful completion is also mandatory for bundle. Those binaries never substitute for the authenticated release archive.
The engineering issue85 workflow remains a separate evidence producer without release approval.

## 数据模型
Producer fields: provider, repository, sha, run_id, run_attempt, workflow_ref, job, runner_os. Archive and envelope digests are exact lowercase64hex strings. Derived receipts preserve raw warnings and classified findings and explicitly deny release/publication approval.

## API 设计
release_dependency_contract verifies an externally authenticated envelope, exact extracted binaries and warning policy. The cloud_release_bundle unpack CLI uses unpack_trusted and requires an external archive digest. Final dependency verification recomputes the proof and requires canonical raw cloud bytes. Legacy raw-zero audits remains separately callable.

## 文件结构
New scripts/release_dependency_contract.py and contract tests; edits to scripts/cloud_release_bundle.py, scripts/final_rc_evidence.py, their tests, final-rc-packages.yml, full-rc-cloud-binaries.yml and issue85-exact-build-audit.yml. Integration documentation records proof limits. No product Rust source changes.

## 设计决策
### Decision1: Independent adapter (FR-1, FR-2)
Do not modify verify_records: its CRITICAL graph impact and existing evidence boundary are avoided. The adapter strengthens producer and warning policy after full existing verification.
### Decision2: Same-commit reusable workflow (FR-3)
Trusted needs outputs preserve both digests without cross-run artifact self-authentication. All outputs and targets stay outside the checkout. Remove unused agent_fixture workflow plumbing only.
### Decision3: Separate desktop proof (FR-2)
Active local GLib is never classified as absent. A local backport requires its independent source verifier and original advisory evidence; installed byte proof remains the native-package workflow responsibility.

## 测试策略
Exercise malformed/missing trust anchors, producer replay, altered streams/archive/binaries, graph/unit/features mismatch, active/unmapped vulnerabilities, unsound and malformed warnings, raw-report substitution, missing backport proof, DAG failures and existing release gate negatives. Actual final hosted proof cannot be claimed while source/version/security gates block.
Call-route regressions require every final archive consumer to reach unpack_trusted before legacy unpack, and verify a wrong external digest rejects before legacy unpack is called. DAG tests require an unconditional local topology call after source approval and normal success-only bundle prerequisites.

## 风险评估
- Producer fields accidentally sourced from artifact: require external inputs and mutation tests
- Circular Python imports: adapter depends on exact verifier only; archive import in final helper is local
- Warning omission: validate raw warning shape and map each record to exact lock identity
- Mixed CI attempts: fail closed and require rerunning producer/dependents

## 检查清单
- [x] All requirements covered and security boundaries explicit

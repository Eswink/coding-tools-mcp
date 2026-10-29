# 任务清单：release-archive-audit-contract

## 概述
Implement only the reviewed release-evidence contract, with independent parent review before adoption.

## 交付物清单（Scope-lock）
- New: adapter, raw capture helper, their two test suites and three specification files
- Modified: archive helper/tests, final helper/tests, three workflows and integration document
- Functions: bounded producer/warning policy helpers, audited archive join and CLI plumbing; no verify_records edits
- Any file approaching500lines will be split into a small policy module or test fixture module

## 任务列表
### 阶段1: Contract implementation
- [x] 1.1 Authenticate archive and CI producer before binary use
  - **证据块**: scripts/cloud_release_bundle.py:120 compares digest(archive) only to item.get('sha256'); scripts/exact_build_audit.py:119 accepts a repository workflow prefix
  - **涉及文件 + 行数预算**: adapter <350lines, archive helper <260lines
  - _需求: FR-1; 设计: Decision1_
- [x] 1.2 Preserve canonical raw audit and reject unresolved unsound evidence
  - **证据块**: scripts/exact_build_audit.py:248 only checks warnings is a dict
  - **涉及文件 + 行数预算**: adapter <350lines, final helper <350lines
  - _需求: FR-2; 设计: Decision1, Decision3_
- [x] 1.3 Wire same-commit workflow outputs and retain original release gates
  - **证据块**: final-rc-packages.yml:31 contracts currently gates all builds; full-rc-cloud-binaries.yml:70 contains unused --example agent_fixture
  - **涉及文件 + 行数预算**: three workflows each <500lines
  - _需求: FR-3; 设计: Decision2_
- [x] 1.4 Require same-final-source topology and lock trusted unpack call routes
  - **证据块**: issue40-container-topology.yml supports workflow_call and exact-source collector; final bundle must require its success
  - **涉及文件 + 行数预算**: final workflow <500lines; adapter tests <500lines
  - _需求: FR-1, FR-3; 设计: Decision2, 测试策略_

### 阶段2: Validation and review
- [ ] 2.1 Execute mutation matrix and existing package/image/native contracts
  - **证据块**: exact_build_audit_tests.py already covers22 invariant groups; archive tests9; final tests16
  - **涉及文件 + 行数预算**: adapter tests <450lines; existing tests bounded additions
  - _需求: FR-1, FR-2, FR-3; 设计: 测试策略_
- [ ] 2.2 Stage-audit isolated patch and record blocked hosted acceptance
  - **证据块**: current final source/version/integration guards are mandatory before final workflow builds
  - **涉及文件 + 行数预算**: docs/releases/exact-build-audit-integration.md <220lines
  - _需求: FR-3; 设计: 风险评估_

## 验收标准
All local affected suites and workflow lint pass; unknown/active security findings remain blocked; no excluded product/version/security files change. Independent parent review and new-source hosted proof remain explicitly pending.

## 需求覆盖矩阵
- FR-1: tasks1.1 and2.1 authenticate the producer and actual archive bytes
- FR-2: tasks1.2 and2.1 preserve raw reports and separate desktop provenance
- FR-3: tasks1.3 and2.2 preserve the non-circular release gates and review boundary

## 文件变更清单
- scripts/release_dependency_contract.py and scripts/release_dependency_contract_tests.py: new policy and negative tests
- scripts/release_dependency_capture.py and scripts/release_dependency_capture_tests.py: separate raw collector and command-boundary tests
- scripts/cloud_release_bundle.py and scripts/cloud_release_bundle_tests.py: required external digest and archive join
- scripts/final_rc_evidence.py and scripts/final_rc_evidence_tests.py: final dependency and artifact verification
- .github/workflows/full-rc-cloud-binaries.yml, final-rc-packages.yml and issue85-exact-build-audit.yml: producer outputs, consumers and engineering exercise
- docs/releases/exact-build-audit-integration.md and this specification: contract and limitations

## 检查清单
- [x] Scope and evidence links defined
- [ ] Implementation, tests and independent review complete

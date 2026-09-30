# 任务清单：strict-legacy-release-gates
## 概述
Implement strict source evidence classification and cumulative manifest validation.
## 交付物清单（Scope-lock）
New8files and modified2files, total10. Helpers/tests4, specs3, release audit1; workflow2. Each helper/test below500lines.
## 任务列表
- [x] 1.1 Route strict provenance without modifying existing validators
  - 证据块: scripts/发布版本校验v4.py:17 VERSION matches stable only; rc_version_gate.py:14 RC_VERSION matches numberedRC.
  - 涉及文件: source_provenance_gate.py100lines, tests150lines, 发布来源验证v4.yml100lines.
  - 需求: FR-1; 设计: 技术方案.
- [x] 2.1 Validate exact frozen cumulative manifest including deletions
  - 证据块: cloud-gateway-lab.yml:51 compares main758c againstHEAD with additive prefixes; failure currently prevents tests.
  - 涉及文件: reviewed_source_gate.py250lines, tests250lines, cloud-gateway-lab.yml220lines.
  - 需求: FR-2,FR-3,FR-4; 设计: 数据模型.
- [x] 3.1 Execute positive/negative tests and document parent freeze trust boundary
  - 证据块: prior packaging audit identifies stableRCclassification mismatch and historical source allowlist failure; production code remains unchanged.
  - 涉及文件: docs/releases/legacy-source-gates.md150lines and three specs.
  - 需求: FR-5; 设计: 测试策略.
## 检查点
Spec and impact before edits; tests/diff/actionlint/detect before handoff; no manifest autogeneration.
## 需求覆盖矩阵
FR-1:1.1; FR-2/FR-3/FR-4:2.1; FR-5:3.1.
## 文件变更清单
Two helpers, two tests, three specs, one release document, two workflows.

## Verification
14 new helper tests,14 unchanged stable tests,2 RCtests,93 protocol tests,8 offline tests and8 fault-proxy tests pass. actionlint passes. Final reviewed manifest absent by design; cumulative source gate remains blocked until parent freeze.

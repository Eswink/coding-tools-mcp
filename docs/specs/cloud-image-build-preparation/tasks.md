# 任务清单：cloud-image-build-preparation
## 概述
Bounded missing image preparation for #40.
## 交付物清单（Scope-lock）
8files:7new and1modified. Dockerfile, helper, tests, auditdoc,3specs; cloudworkflow appended job.
## 任务列表
- [x] 1.1 Build non-root image from exact accepted bundle
  - 证据块: deploy/cloud-gateway/render.py sets65532 and obsoleteLISTEN_ADDR; actual input.rs rejects non-loopback.
  - 涉及文件: Dockerfile40lines, full-rc-cloud-binaries.yml250lines.
  - 需求: FR-1,FR-2; 设计: 技术方案.
- [x] 2.1 Verify hosted fixture ownership and exact parser boundary
  - 证据块: service/input.rs read_protected checks parent/fileUID andmode; ServiceError maps file_protection_failed versusinvalid_secret_input.
  - 涉及文件: cloud_image_gate.py180lines, tests120lines.
  - 需求: FR-3,FR-4; 设计: 数据模型.
- [x] 3.1 Preserve unfinished ingress and unsupportedhost release blockers
  - 证据块: Issue40 requiresimage/build; currentrenderer declaresNOT_DEPLOYABLE and _FILE contract doesnotmatch executableCLI.
  - 涉及文件: docs/releases/issue40-image-gap.md120lines and3specs.
  - 需求: FR-5; 设计: 风险与决策.
## 检查点
Spec/impact, unit/actionlint, stageddelta and exactmanifest. No publication.
## 需求覆盖矩阵
FR-1/FR-2:1.1; FR-3/FR-4:2.1; FR-5:3.1.
## 文件变更清单
Eight files above; no production source edits.

## Verification
Seven new synthetic image tests, nine cloud bundle tests and23 existing deployment tests pass; actionlint passes. Actual Docker image/native mount tests remain NOT_EXECUTED until CI. Functional container ingress/CLI Compose mapping remains unfinished engineering.

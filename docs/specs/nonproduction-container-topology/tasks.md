# 任务清单：nonproduction-container-topology
## 概述
Implement runnableengineering topology andactualnegativeproof.
## 交付物清单（Scope-lock）
9newfiles and2 documentation/scope updates:renderer,2fixturemodules,unit tests,workflow,guide,3specs. Noexistingproduction edits; eachmodule below500lines.
## 任务列表
- [x] 1.1 Render actualCLI/privateDB/nonrootnamespace topology
  - 证据块: service/input.rs rejectsnonloopback andrequiresprotectedparentUID; oldrender.py usesobsoleteenvcontract.
  - 涉及文件: runtime_topology.py220lines, unit tests150lines.
  - 需求: FR-1,FR-2; 设计: 技术方案.
- [x] 2.1 Bootstrapempty privateDB throughshippedcommands andexercise protocol/lifecycle
  - 证据块: newIssue39CLI invite/prove/redeem/select; mcp_cli.rs requiresregisteredselecteddevice; channel/transport.rs requiresoriginalHost/subprotocol.
  - 涉及文件: container_fixture.py350lines,run_container_topology.py350lines.
  - 需求: FR-3,FR-4,FR-5; 设计: 数据模型.
- [x] 3.1 Gate nativeCompose2.27 evidenceanddocumentremainingproductionboundaries
  - 证据块: Issue40acceptance requiresactualimage/Compose/Nginx, nottemplateonly; Dockerpre28loopbackrisk remainsblocked.
  - 涉及文件: issue40-container-topology.yml180lines,guide150lines,3specs.
  - 需求: FR-6; 设计: 测试策略.
## 检查点
Spec/impact beforeedits; no nativeclaims beforeactualCI; cleanupandsecretreceipts reviewed.
## 需求覆盖矩阵
FR-1/FR-2:1.1; FR-3/FR-4/FR-5:2.1; FR-6:3.1.
## 文件变更清单
Nine new files plus the historical image-gap document and image receipt scope text. Customer binary packaging files remain unchanged.

## Lifecycle refinement
Use a non-root stable namespace anchor rather than gateway-owned namespace, preserving loopback policy and private DB network. Test gateway restart with unchanged anchor and ingress container IDs. No extra image or public port.

## Validation state
Eight new topology contracts plus23 existing deployment contracts pass; seven image tests and nine archive tests pass; actionlint and Python compilation pass. Native DockerCompose/Nginx application evidence remains pending the dedicated GHA run on a candidate containing the shipped enrollment CLI.

# 任务清单：cloud-release-artifacts
## 概述
Prepare server artifactfamily without changing desktoppackagefiles.
## 交付物清单（Scope-lock）
7newfiles: workflow,helper,tests,installguide,3specs. Noexistingproduction edits. Helpersbelow500lines.
## 任务列表
- [x] 1.1 Validate product/componentversions andactualreleaseCLI
  - 证据块: services/cloud-gateway/Cargo.toml has4binentries andpackage0.1.0; service/cli.rs:94 usesCARGO_PKG_VERSION.
  - 涉及文件: cloud_release_bundle.py300lines andtests220lines.
  - 需求: FR-1,FR-2; 设计: 技术方案.
- [x] 2.1 Build andverify exactallowlisted archive andnativeprocessreports
  - 证据块: tests/run_service_http.py --binary acceptsreleasepath; run_agent_process.py --bin-dir acceptsdownloadedbins.
  - 涉及文件: full-rc-cloud-binaries.yml220lines,helper300lines.
  - 需求: FR-3,FR-4; 设计: 数据模型.
- [x] 3.1 Document usablebinarysetup andremainingdeployment/securitygates
  - 证据块: deploy/cloud-gateway/README.md explicitlyNOT_DEPLOYABLE, noimplemented imageinstaller.
  - 涉及文件: cloud-binary-install.md150lines plus3specs.
  - 需求: FR-5; 设计: 风险与决策.
## 检查点
Spec/impact beforeimplementation, realnegativeunit/actionlint, exactsource nativepending.
## 需求覆盖矩阵
FR-1/FR-2:1.1; FR-3/FR-4:2.1; FR-5:3.1.
## 文件变更清单
Seven new filesabove; previouspackaging7files byteunchanged.

## Verification
Nine synthetic unit tests and actionlint pass. No local or native release build was run. Gateway version alignment, exact integration and native binary/process evidence remain pending. All seven prior desktop packaging files retain their original hashes.

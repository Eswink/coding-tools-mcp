# 任务清单：preliminary-package-engineering
## 概述
Enable early package diagnosis without touching final gates.
## 交付物清单（Scope-lock）
Six files: two modified workflows, one new workflow contract test and three specs. No new runtime functions.
## 任务列表
- [x] 1.1 Pin existing engineering workflow toolchain/cache and bounded trigger
  - 证据块: windows-rc-packages.yml useswindows-latest andRuststable; both workflows pinRC_VERSION0.6.0-rc.4.
  - 涉及文件: windows-rc-packages.yml below180lines,linux-rc-packages.yml below240lines.
  - 需求: FR-1,FR-2; 设计: 技术方案.
- [x] 2.1 Preserve acceptance and add explicitly unverified build receipts
  - 证据块: rc_windows_install.ps1 copies package only after nativeacceptance; Linux build already uploads prior to installedmatrix.
  - 涉及文件: same2workflows, existing helper scripts unchanged.
  - 需求: FR-3,FR-4,FR-5; 设计: 数据模型.
- [x] 3.1 Verify actionlint and all inherited strictcontract tests
  - 证据块: rc_native_gate.py enforces12stages andsandbox_disabled=false; unchanged.
  - 涉及文件:3specs plus2workflowdiffs.
  - 需求: FR-3,FR-5; 设计: 测试策略.
## 检查点
Spec/impact beforeimplementation; actionlint/tests/detect beforehandoff; no nativepass claimed locally.
## 需求覆盖矩阵
FR-1/FR-2:1.1; FR-3/FR-4/FR-5:2.1,3.1.
## 文件变更清单
Exactly six files above; final RC workflow remains unchanged.

## 验证结果
33 existing contract tests and actionlint pass. Native Windows/Ubuntu installed evidence remains pending GHA. Build receipts explicitly accepted=false, publish_approved=false. Final release workflow is untouched.

Parent review addition: required Rust regression remains a failing step and keeps the workflow red. Only independently successful source/frontend prerequisites permit diagnostic package build. Native smoke may continue only from verified build/driver outcomes; no continue-on-error. Linux regression uses private D-Bus/Secret Service and system Python. Failure-propagation tests cover these conditions.

# 任务清单：final-rc-packaging-gate
## 概述
Prepare exact-source packaging without release authorization.
## 交付物清单（Scope-lock）
预计新建文件数:7. 预计修改文件数:0. 预计新增函数数:8.
1. docs/specs/final-rc-packaging-gate/requirements.md
2. docs/specs/final-rc-packaging-gate/design.md
3. docs/specs/final-rc-packaging-gate/tasks.md
4. .github/workflows/final-rc-packages.yml
5. scripts/final_rc_evidence.py
6. scripts/final_rc_evidence_tests.py
7. docs/releases/final-rc-gates.md
## 任务列表
- [x] 1.1 Verify explicit version and exact successful integration source
  - 证据块: scripts/rc_version_gate.py:77 `def verify_source` checks six fields and clean source; dot-rc-integration.yml:25 `native` covers3OSes.
  - 涉及文件: final_rc_evidence.py budget250lines; workflow budget450lines.
  - 需求: FR-1,FR-2; 设计: 架构设计.
- [x] 2.1 Build22-compatible packages and install samebytes across22/24, keepWindows native acceptance
  - 证据块: scripts/rc_packages.py:66 `def identity` binds source/run/tree/version; rc_windows_install.ps1:1 requires explicit output/driver.
  - 涉及文件: final-rc-packages.yml budget450lines.
  - 需求: FR-3,FR-4; 设计: 架构设计.
- [x] 2.2 Validate evidence and checksum bundle withoutpublication
  - 证据块: scripts/rc_native_gate.py:16 `def verify` preserves twelve native stages and sandbox_disabled=false.
  - 涉及文件: final_rc_evidence.py budget250lines; tests budget200lines.
  - 需求: FR-5; 设计: 数据模型与接口.
- [x] 3.1 Audit legacy guards and run negative regression/actionlint
  - 证据块: cloud-gateway-lab.yml:51 mainbase additive allowlist rejects cumulative source; release.yml:39 tag resolver targetsstable versions.
  - 涉及文件: docs/releases/final-rc-gates.md budget150lines.
  - 需求: FR-6; 设计: 测试策略.
## 检查点
Spec before implementation; impact before existing symbol changes; native status explicitlypending.
## 需求覆盖矩阵
FR-1/FR-2:1.1; FR-3/FR-4:2.1; FR-5:2.2; FR-6:3.1.
## 文件变更清单
Seven files above, allnew. No production file edits.
## 检查清单
No version rewrite or publication; no disabled security assertions; allnative limitations retained.

## 验证结果
16 new synthetic evidence tests,2 RCversion,3 RCpackage,3 Windowsinstallercontract,25nativecontract,14stableprovenance tests pass; actionlint passes. Native packaging not run; Windows production isolation remains blocked. Historical main-PR repairs documented, not silently applied.

## Orchestration extension
FR-1/FR-2: bounded push branch trigger uses committed version and read-only exact-SHA successful integration resolution; dispatch keeps explicit inputs. Four new negative/selection tests pass. Parent alone creates trigger after owner decision.

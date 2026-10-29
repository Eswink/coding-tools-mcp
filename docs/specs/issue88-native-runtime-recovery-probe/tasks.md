# 任务清单：issue88-native-runtime-recovery-probe

## 概述

先规格和freshimpact，再管理helper与workflow、静态及真实恢复检查、peer冻结、gencommit/nonforce/draftPR/actualCI；本地首85FAIL保留，300NOTRUN。

## 交付物清单（Scope-lock）

预计新建11文件，修改0已有文件；新增22函数、原runner8函数/class逐字复制，不修改生产symbol。全部列在文件变更清单；若拆分/增加文件或函数需更新具体scope、impact和peer review。

## 任务列表

### 阶段1: 准备工作

- [ ] 1.1 固定真实backups、spec/Plan与freshGN，新helperunknown按manualHIGH披露后实现。
  - 证据块：AGENTS.md:45 `MUST run impact analysis before editing any symbol`；本地diagnostic实际原PREFIX129、workerdelegate1/sourceb9cf未变。
  - 涉及文件：3规格各250行以内。
  - _需求: FR-1, FR-2, FR-5_ ｜ _设计: 决策1/2_

### 阶段2: 核心实现

- [ ] 2.1 从F13和dab238两patch完整恢复并核1878/b9cf、唯一privateparent。
  - 证据块：原run_native_stage_immutable.py:27 `subprocess.check_output(['/usr/bin/git', '-C', str(root), 'ls-files', '-z'])`；source02独立full5984AST仅8差。
  - 涉及文件：restore<=300行、inventory JSON<=450行；禁止management源进SUT。
  - _需求: FR-1_ ｜ _设计: 决策1_
- [ ] 2.2 逐字保留原runner并有限ownnative supervisor、完整85到300原文件seal与nofollow重读门。
  - 证据块：原103行runner:103 `sys.exit(0 if receipt['passed'] else 1)`；V5owner `assert observed.si_pid == child.pid`；TERM7/KILL2/family2及动态adoption/ECHILD原审查通过。
  - 涉及文件：kernel<=180行、owner<=400行、immutableoriginalrunner103行；原helpers语义diff必须explicitreview。
  - _需求: FR-2, FR-3, FR-4_ ｜ _设计: 决策2/3_
- [ ] 2.3 编写只contentsread fixedtestbranch workflow与最小env、安全原artifact扫描。
  - 证据块：rc-pretag-contract-checks.yml:23 `runs-on: ubuntu-24.04`、checkout `persist-credentials: false`；原Git2.43unsupported不授权setupGit。
  - 涉及文件：workflow<=150行、entry<=250行。
  - _需求: FR-2, FR-5_ ｜ _设计: 决策2/4_

### 阶段3: 集成测试

- [ ] 3.1 对照验收标准实际source-restoration、static/negative checks、peer冻结与precommit检测。
  - 证据块：原85rawreceipt `passed:false`、nativeCLD_EXITED1/ECHILDtrue；此失败绝不作新CI门。
  - 涉及文件：checks<=300行；证据全部outside管理与pure源码。
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ ｜ _设计: 测试策略_
- [ ] 3.2 gencommit小步非强推testbranch/draftPR，检查actualCI；85全部qualified才300一次。
  - 证据块：AGENTS.md提交前detect_changes与gencommit；根已明确允许具体testCI路径，无Releasegrant。
  - 涉及文件：0新增；真实CIrun/PR证据outside。
  - _需求: FR-3, FR-5_ ｜ _设计: 决策3/4_

## 检查点

- [ ] 规格通过后才代码；HIGH通知先发生。
- [ ] 所有源码冻结与必要checks和peer闭合后才提交。
- [ ] 原Gitprecondition/85/300每个实际结果保留，失败无retry。

## 需求覆盖矩阵

| 需求ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 决策1 | 1.1/2.1/3.1 | pending |
| FR-2 | 决策2/3 | 1.1/2.2/2.3/3.1 | pending |
| FR-3 | 决策3 | 2.2/3.1/3.2 | pending |
| FR-4 | 决策3 | 2.2/3.1 | pending |
| FR-5 | 决策4 | 1.1/2.3/3.1/3.2 | pending |

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---|---|
| docs/specs/issue88-native-runtime-recovery-probe/requirements.md | 新建 | 250 | fiveFR |
| docs/specs/issue88-native-runtime-recovery-probe/design.md | 新建 | 250 | boundedsource/native/evidence |
| docs/specs/issue88-native-runtime-recovery-probe/tasks.md | 新建 | 250 | thisscope |
| .github/workflows/rc-native-recovery-probe.yml | 新建 | 150 | literaltestbranch |
| scripts/rc_native_probe_restore.py | 新建 | 300 | immutablefullsource |
| scripts/rc_native_probe_kernel.py | 新建 | 180 | V5kernel |
| scripts/rc_native_probe_owner.py | 新建 | 400 | owned85/300gate |
| scripts/rc_native_probe.py | 新建 | 250 | minimalenv/safeartifact |
| scripts/rc_native_probe_original_runner.py | 新建 | 103 | exactoriginal |
| scripts/rc_native_probe_inventory.json | 新建 | 450 | exact85/300 |
| scripts/rc_native_probe_checks.py | 新建 | 300 | meaningfulstatic/negative/restore |

## 检查清单

- [x] 明确11交付物、0production修改，必要证据和所有FR回链。
- [ ] 实际实现/测试/peer/CI完成证据未取得。

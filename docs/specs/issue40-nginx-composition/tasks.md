# 任务清单：issue40-nginx-composition

## 概述
本地七路径候选；fresh Plan=`feature-issue40-nginx-composition-steady-6bd7f2b70a`。经核验的评审packet SHA256=`0f41eacae6296c7e6db6d8c7f5b86f419102ae686f79ded2711735c970be067b`；以下执行闸门未完成前不声明通过。

## 交付物清单（Scope-lock）
新增5、修改2、合计7路径；四个新profile公开函数、20个新test方法，修改当前树test及desktop setUp/两兼容test共4个既有方法；辅助函数仅限两新Python文件且不增加scope。
两适配器+新测试+三规格六文件先定稿，profile记录六完整blob/SHA256；七项全100644/blob，A完整树1664项，P九新增与全部历史非review路径保持精确。

## 任务列表
### 阶段1：固定规格与先验影响
- [x] 1.1 阅读批准packet、Probe4.0.1、项目架构/开发/测试上下文并编写三份有界规格
  - **证据块**: `scripts/rc_pretag_composition_tests.py:193–195`：`expected = desktop.selected_profile(`；`scripts/rc_pretag_desktop_tests.py:18–19`：`self.blob((c.ROOT / p).read_bytes())`证明当前fixture绑定工作树
  - **涉及文件**: `docs/specs/issue40-nginx-composition/{requirements,design,tasks}.md`，各≤80行
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6_ ｜ _设计: 概述、架构设计、设计决策、测试策略_
- [ ] 1.2 通过check_spec并取得本轮fresh upstream impact，保留降级事实及HIGH语义风险
  - **证据块**: `docs/project-context/how-to-develop.md:9–11`要求规格/heartbeat/impact；`scripts/rc_pretag_desktop_profile.py:126–131`：`original = ownership.selected_profile(`保留旧链
  - **涉及文件**: 本步骤不增改source文件；三规格各≤80；graph/Plan证据在source外
  - _需求: FR-1, FR-6_ ｜ _设计: 架构设计、风险评估_
### 阶段2：实现固定边界
- [ ] 2.1 实现只读profile，固定F/P/R、九源/四文档、封闭parents及六pin引导
  - **证据块**: `scripts/rc_pretag_desktop_profile.py:58–68`完整AMENDMENT_PINS；`:126–144`旧source完整map/hash检查；`scripts/rc_pretag_composition_tests.py:27–31`四个固定R文档
  - **涉及文件**: `scripts/rc_pretag_nginx_profile.py`≤400行；仅只读回调与常量；六非self pin定稿后固定，profile self交外部manifest核验
  - _需求: FR-1, FR-2, FR-3_ ｜ _设计: 架构设计、数据模型、API 设计、决策1、决策3_
- [ ] 2.2 仅调整composition三片段和desktop三个方法，完整逆回F并保留旧断言
  - **证据块**: `scripts/rc_pretag_composition_tests.py:434–435`：`EXPECTED_GROUPS.update(desktop.EXPECTED_GROUPS)`；`scripts/rc_pretag_desktop_tests.py:243–280`保留原F→X逆变换、AST及147+20集合检查
  - **涉及文件**: composition≤500行/Δ24，desktop tests≤400行/Δ80；其它旧函数、方法、Git/index/worktree与run_inventory不变
  - _需求: FR-3, FR-4, FR-5_ ｜ _设计: 决策2、决策3、测试策略_
- [ ] 2.3 实现且冻结恰20新方法，逐项独立构造拓扑/内容拒绝证据
  - **证据块**: `scripts/rc_pretag_desktop_tests.py:39–60`先验证内容再`content.assert_not_called()`；`:62–67`先desktop_topology再拒绝内容；`scripts/rc_pretag_composition_tests.py:459–462`比较discovery与declared Counter
  - **涉及文件**: `scripts/rc_pretag_nginx_tests.py`≤480行；方法名称逐字等于design20项，不过滤167旧项
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ ｜ _设计: 测试策略_
### 阶段3：验证当前revision并停止于评审
- [ ] 3.1 定稿六pin后在独立clean A/feature/release三个context执行完整矩阵并逐条核验EARS
  - **证据块**: `scripts/rc_pretag_composition_tests.py:454–462`：GLib SHA校验及`Counter(loaded) != Counter(expected)`；旧评审实际P/I/L1是167中1失败，不是已修复结果
  - **涉及文件**: 七source路径不额外扩展；187 strict/discovery各一次、原452、deployment68、desktop129、source-backport39；外部日志记录commit/tree/parents、ID、command/count/exit/SHA256
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6_ ｜ _设计: 测试策略、风险评估_
- [ ] 3.2 审核精确七路径diff、预算、完整inverse、fresh graph及外部七blob/tree manifest
  - **证据块**: `scripts/rc_pretag_desktop_profile.py:57`：`Acyclic full-file pins: adapter, tests and specs never contain this module's hash.`；新profile亦不能认证自身
  - **涉及文件**: 七路径总Δ≤1250且各预算不超；旧更严预算/模块/pins不变；外部审查必须绑定profile自身准确bytes
  - _需求: FR-3, FR-4, FR-6_ ｜ _设计: 决策1、决策3、风险评估_

## 检查点
- [ ] 阶段1：spec通过后才写实现，fresh impact记录HIGH语义风险及静态/FTS能力限制
- [ ] 阶段2：原167+精确20声明无交集，六文件完整pin，七路径/1664项/六版本槽/旧预算均准确
- [ ] 阶段3：三context所有矩阵实际退出0且零skip/xfail/xpass，外部self-pin审查后才报告本地候选结果
- [ ] 保留P原红灯及P-only原生run；不提交/推送/merge/dispatch/发布，不触及PR98/Issue86；允许本地暂存/tree snapshot/staged detect_changes用于精确候选评审；source commit/publication仍需未来授权

## 需求覆盖矩阵
| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 架构设计、测试策略 | 1.1,1.2,2.1,2.3,3.1 | 规格已写，待验证 |
| FR-2 | 数据模型、测试策略 | 1.1,2.1,2.3,3.1 | 规格已写，待验证 |
| FR-3 | 决策1、决策3 | 1.1,2.1,2.2,2.3,3.1,3.2 | 规格已写，待验证 |
| FR-4 | 决策2、测试策略 | 1.1,2.2,2.3,3.1,3.2 | 规格已写，待验证 |
| FR-5 | 测试策略 | 1.1,2.2,2.3,3.1 | 规格已写，待验证 |
| FR-6 | 测试策略、风险评估 | 1.1,1.2,3.1,3.2 | 规格已写，待验证 |

## 文件变更清单
| 文件 | 操作 | 行数预算 |
|---|---|---|
| scripts/rc_pretag_composition_tests.py | 修改 | ≤500，Δ≤24 |
| scripts/rc_pretag_desktop_tests.py | 修改 | ≤400，Δ≤80 |
| scripts/rc_pretag_nginx_profile.py | 新增 | ≤400 |
| scripts/rc_pretag_nginx_tests.py | 新增 | ≤480 |
| docs/specs/issue40-nginx-composition/requirements.md | 新增 | ≤80 |
| docs/specs/issue40-nginx-composition/design.md | 新增 | ≤80 |
| docs/specs/issue40-nginx-composition/tasks.md | 新增 | ≤80 |

## 检查清单
- [x] 七交付物、真实代码证据、FR/设计回链、每文件及总预算已明确，无占位内容
- [ ] 最终矩阵、source图谱、pin/inverse与独立评审证据齐备；未执行不标成PASS

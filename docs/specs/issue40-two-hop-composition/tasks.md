# 任务清单：issue40-two-hop-composition

## 概述
批准的本地八路径组合amendment；最终原生P与F/R见requirements。以下是稳定验收任务，实际执行记录置于外部审查包，避免进度勾选改变被pin规格字节；未验证不声明完成。

## 交付物清单（Scope-lock）
修改3、新增5，共8路径；公开函数two_hop_topology/two_hop_content/amendment_content/selected_profile；固定22新tests；既有方法仅composition1、desktop2、nginx6。helpers只在两新Python文件。
三适配器、新测试、三spec先冻结七完整blob/SHA256，profile最后固定pins；外部manifest核验全部八文件尤其self-bytes、tree及ordered parents。八文件均100644/blob；P1665、A1670，保留全部原生七源和历史受保护项。

## 任务列表
### 阶段1：规格与修改前影响
- [ ] 1.1 核对批准设计/库存、最终P独立原生审计及当前F/P/R对象，冻结三份规格并通过Probe4.0.1 check_spec
  - **证据块**: `scripts/rc_pretag_composition_tests.py:194–196`仍调用nginx.selected_profile；`scripts/rc_pretag_nginx_tests.py:20–22`从当前工作树构造旧amendment，说明新层与历史fixture必须分开
  - **涉及文件**: 仅本目录requirements.md/design.md/tasks.md，各≤80行；引用批准187+22=209显式清单，不由discovery生成expected
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6_ ｜ _设计: 概述、架构设计、设计决策、测试策略_
- [ ] 1.2 取得九个待改方法及复用边界的fresh upstream impact/context，报告HIGH语义风险和图谱降级事实
  - **证据块**: `docs/project-context/how-to-develop.md:9–11`规定check_spec、heartbeat、impact；`scripts/rc_pretag_nginx_tests.py:18–26,250–336`覆盖fixture、预算及历史inverse
  - **涉及文件**: 此步不增改source；外部记录ownership commit/parents/topology/selected_profile/budgets/release_content、desktop/nginx topology/content/selectors和composition runner/fixture边界
  - _需求: FR-1, FR-4, FR-6_ ｜ _设计: 架构设计、决策2、风险评估_
### 阶段2：实现有限准入与历史保护
- [ ] 2.1 实现只读profile，固定F/P/R、七原生完整pins、闭合parents与四发行文档，并保留旧终结式分派
  - **证据块**: `scripts/rc_pretag_composition_tests.py:194–196`旧selector入口；`scripts/rc_pretag_nginx_tests.py:28–38`既有selected/content/amended回调边界；F→P实际六替换一新增
  - **涉及文件**: scripts/rc_pretag_two_hop_profile.py≤360/Δ360；仅标准库、惰性常量、只读callback，旧三profile字节及所有旧pins不变
  - _需求: FR-1, FR-2, FR-3_ ｜ _设计: 架构设计、数据模型、API 设计、决策1、决策3_
- [ ] 2.2 只改composition三片段、desktop两个方法及nginx六方法；保持历史全部断言并实现完整inverse
  - **证据块**: `scripts/rc_pretag_desktop_tests.py:246–295`旧全文件inverse/AST/147+20+20；`scripts/rc_pretag_nginx_tests.py:259`当前长度减一负例必须改为冻结fixture长度减一
  - **涉及文件**: composition≤500/Δ24、desktop≤400/Δ48、nginx≤480/Δ128；精确方法allowlists见design；desktop setUp、旧runner/Git/index/worktree及其它方法不变
  - _需求: FR-3, FR-4, FR-5_ ｜ _设计: 决策1、决策2、测试策略_
- [ ] 2.3 冻结design逐字列出的22新方法，独立触发拓扑/内容/adapter拒绝边界及保留187完整ID
  - **证据块**: `scripts/rc_pretag_nginx_tests.py:43–55`先验证内容再测拓扑拒绝；`:316–336`保留167+20库存及runner AST；`scripts/rc_pretag_composition_tests.py:459–462`Counter比较真实discovery与声明
  - **涉及文件**: scripts/rc_pretag_two_hop_tests.py≤480/Δ480；独立覆盖每source字段、protected entry、版本槽、doc、pin、cap、inverse片段及旧断言，禁止filter/skip/xfail/xpass
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ ｜ _设计: 测试策略、决策2、决策3_
### 阶段3：精确当前候选验证与停止闸门
- [ ] 3.1 七非self文件定稿后固定pins并分别物化干净A、I=[F,A]、L=[R,I]，执行每context完整矩阵
  - **证据块**: `scripts/rc_pretag_composition_tests.py:454–474`固定GLib hash、loaded/executed精确库存及零抑制要求；原187七失败条目必须保留而非补写通过
  - **涉及文件**: 不扩八路径；各209 strict与209 discovery、452含audit22、deployment86、desktop129、source-backport39；独立完整对象库及隔离细节见requirements FR-6
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6_ ｜ _设计: 测试策略、风险评估_
- [ ] 3.2 完成精确八路径diff/caps/inverse、新增符号fresh impact、staged detect_changes及外部八blob/tree/parents/self认证
  - **证据块**: `scripts/rc_pretag_nginx_tests.py:277–314`旧全文件inverse及assertion Counter不能替代新profile自身的独立认证；内嵌七pins不涵盖第八profile self-bytes
  - **涉及文件**: 八路径总Δ≤1300且全部个别/旧更严预算通过；外部记录每command/ID/count/exit/log SHA256、完整模式/blob表与独立审核结果
  - _需求: FR-3, FR-4, FR-6_ ｜ _设计: 决策1、决策2、风险评估_
- [ ] 3.3 报告实际A/I/L结果、历史红灯和P-only原生证据归属，在另行授权前停止远端/生产动作
  - **证据块**: 最终P=`f8d187dfe9fe30e8641c7f8906d615265811c107`是34/45/57、deployment86/job、Rust128/audit22原生证据的唯一source；新合成SHA不同不能继承
  - **涉及文件**: 此步无source变化；保留engineering_only=true及全部旧false flags，不声称真实host/installed/security/release/publication已验
  - _需求: FR-6_ ｜ _设计: 决策3、测试策略、风险评估_

## 检查点
- [ ] 阶段1：规格与fresh impact先于代码修改；图谱不支持时明确限制，不用过期LOW代替HIGH语义审查
- [ ] 阶段2：仅1/2/6既有方法变化；旧187与新22无交集；七非self pins、八路径及P/A树数量准确
- [ ] 阶段3：A/I/L所有实际矩阵退出0、精确ID/零抑制与外部self认证；失败/未运行/阻断分别报告
- [ ] 不转移P原生证据；允许本地审查commit objects/fixture refs及暂存/tree snapshot以验证A/I/L，不push/PR操作/远端merge/dispatch/tag/Release/deploy或扩权限

## 需求覆盖矩阵
| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 架构设计、API 设计、测试策略 | 1.1,1.2,2.1,2.3,3.1 | 待当前证据验收 |
| FR-2 | 数据模型、测试策略 | 1.1,2.1,2.3,3.1 | 待当前证据验收 |
| FR-3 | 决策1、文件结构 | 1.1,2.1,2.2,2.3,3.1,3.2 | 待当前证据验收 |
| FR-4 | 决策2、测试策略 | 1.1,1.2,2.2,2.3,3.1,3.2 | 待当前证据验收 |
| FR-5 | 测试策略 | 1.1,2.2,2.3,3.1 | 待当前证据验收 |
| FR-6 | 决策3、测试策略、风险评估 | 1.1,1.2,3.1,3.2,3.3 | 待当前证据验收 |

## 文件变更清单
| 文件 | 操作 | 行数预算（完整/相对P增删） |
|---|---|---|
| scripts/rc_pretag_composition_tests.py | 修改 | ≤500 / Δ≤24 |
| scripts/rc_pretag_desktop_tests.py | 修改 | ≤400 / Δ≤48 |
| scripts/rc_pretag_nginx_tests.py | 修改 | ≤480 / Δ≤128 |
| scripts/rc_pretag_two_hop_profile.py | 新增 | ≤360 / Δ≤360 |
| scripts/rc_pretag_two_hop_tests.py | 新增 | ≤480 / Δ≤480 |
| docs/specs/issue40-two-hop-composition/requirements.md | 新增 | ≤80 / Δ≤80 |
| docs/specs/issue40-two-hop-composition/design.md | 新增 | ≤80 / Δ≤80 |
| docs/specs/issue40-two-hop-composition/tasks.md | 新增 | ≤80 / Δ≤80 |

## 检查清单
- [ ] FR/设计/任务/代码证据、八路径及个别与总预算均经独立审查
- [ ] 固定规格只描述验收任务；实际通过声明必须具备当前revision完整矩阵、pins/inverse及外部review证据

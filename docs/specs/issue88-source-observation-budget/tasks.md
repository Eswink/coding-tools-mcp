# 任务清单：暂存源码观察的共享 Git 预算

## 交付物清单

- 既有五个 runtime 模块中的完整 source Git 预算透传和九个固定 typed 读取
- 两个保留原测试 ID/断言的 phase/kwargs 适配；两个新增真实 Git/child/TLS 用例模块
- 最新 Windows admission 的精确后继层、两处历史直接读取适配和全部原字节 inverse
- 既有双 Ubuntu workflow 中先执行新预算用例的真实 30/60s 测量；原门禁继续完整执行
- 本 requirements/design/tasks 三份规格及绑定实际 source 的最终验证结果

## 任务列表

1. 完成既有 Plan、上下文和逐符号 upstream impact，保留图谱遗漏 alias/_call 的限制；按 source 认证 CRITICAL 手工审查（FR-1—FR-5）
2. 冻结完整未执行 runtime/test、历史 inverse、workflow、路径/caps/ID 清单；独立检查后通过 check_spec 和估算指导，再编辑实现（FR-1—FR-5）
3. 等待 Windows PR144 正常整合，核对实际 F 原始 commit、ordered parents、tree 和全部原始操作数；不以候选或同树推断替代 actual F（FR-5）
4. 实现内部自有 Reader 的完整 source 链；原 activation pair 与后续 operation pair 分开传递，省略控制仍为空 kwargs（FR-1、FR-2）
5. 在已完成语义检查且 owner 成功关闭后检查预算；失败和不确定清理路径不加成功轮询，保持原错误优先级（FR-3、FR-4）
6. 保留原固定 Git 策略、metadata/config/index 支持集和原 known-child 清理；后期 source 清理不确定时标记既有粘性保留字段（FR-2、FR-4）
7. 应用两个最小测试适配，新增用例覆盖九类操作、真实 EOF/exit/reap、ignored 文件、manifest/tag/workflow 失败和后期已有远程效果（FR-1—FR-4）
8. 应用最新与历史直接读取的精确 inverse；保留旧断言 AST、ID、历史 pin，有限 D[F]/I[F,D]/J[R,I] 只允许四个 R 文档 overlay（FR-5）
9. 先运行支持环境的 focused 检查、实际源码独立 review、detect_changes 和 gencommit，再发布一次有限 draft candidate（FR-5）
10. 在双 Ubuntu 原生环境先测新完整 source/activation/session 路线的实际耗时和剩余原 30/60s 预算；失败先诊断，不扩大 deadline 或伪造 owner0（FR-1、FR-2、FR-5）
11. 新 native 路线通过后并行完成全部必要 D/I/J 与 hosted 检查；可复用证据须精确绑定源码、命令、setup 和 ID，不能声称组合证据是单次完整运行（FR-5）
12. 全门禁通过后按正常仓库流程整合、核对实际 parents/tree/overlay 与新 postmerge checks，更新既有 Issue/Plan 证据（FR-5）

## 需求覆盖矩阵

| 需求 | 实现与验证 |
|---|---|
| FR-1 | 任务4、5、7、10；两次 activation 与后续当前 operation 的真实 source 路线 |
| FR-2 | 任务4、6、7、10；固定命令、操作数、输出、config/index 与 helper/environment 拒绝 |
| FR-3 | 任务5、7；默认行为、dirty/SHA/祖先/manifest/tag/workflow 错误先于成功预算轮询 |
| FR-4 | 任务5、6、7；初始零私有根、known-child reap、后期不确定清理与已有效果 |
| FR-5 | 任务1—3、8—12；实际 F、whole-byte inverse、唯一 ID、真实双 Ubuntu 和最终来源组合 |

## 文件变更清单

- 修改 runtime：scripts/rc_consumer_fixed_git.py、scripts/rc_publication_stage.py、scripts/rc_version_gate.py、scripts/reviewed_source_gate.py、scripts/source_provenance_gate.py
- 修改 runtime 用例：scripts/rc_publication_git_budget_cases.py、scripts/rc_publication_staging_budget_cases.py
- 新增 runtime 用例：scripts/rc_consumer_source_git_cases.py、scripts/rc_publication_source_budget_cases.py
- 修改最新 admission：scripts/rc_pretag_windows_vm_profile.py、scripts/rc_pretag_windows_vm_cases.py
- 修改历史直接读取操作数：scripts/rc_pretag_git_budget_cases.py、scripts/rc_pretag_stage_retirement_cases.py
- 新增 admission：scripts/rc_pretag_source_observation_profile.py、scripts/rc_pretag_source_observation_cases.py
- 修改既有 workflow：.github/workflows/issue88-publication-executor.yml
- 新增规格：docs/specs/issue88-source-observation-budget/requirements.md、design.md、tasks.md

共19条路径，12修改、7新增。单源码文件不超过500行；实测完整 delta/caps 和唯一 ID 清单必须在实现前与冻结 packet 一致。
两处额外历史 case 路径只恢复原读取语义，不能删除或放宽原断言，也不产生新测试 ID。
本增量不改 Rust/Go/Cargo、Windows VM、snapshot、PR98 保留载荷、API transport 或实际 publisher eligibility。

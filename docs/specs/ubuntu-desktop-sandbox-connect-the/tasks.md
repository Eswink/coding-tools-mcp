# 任务清单：ubuntu-desktop-sandbox-connect-the

## 概述
基线 9b2639d47aaecc0a903124404c9c97cbf1f806d6；计划 feature-ubuntu-desktop-sandbox-connect-the-s-5aa75bc66e 来自 mcp-probe-kit 4.0.1 的真实 start_feature。规格落盘、check_spec 通过和风险评估之后才实施生产代码。

## 交付物清单
预计新增 9 个文件：本目录三份规格、auth/runtime_admission.rs、auth/local_admission_deadline_tests.rs、tools/linux_sandbox_bridge.rs、tools/linux_sandbox_tests.rs、services/local-agent/tests/sandbox_command_attachment.rs 和专用只读原生 workflow。预计局部修改 13 个文件：auth/聊天授权v1.rs、tools/context.rs、tools/exec.rs、tools/session.rs、tools/dispatch.rs、tools/mod.rs、tools/异步命令v1.rs、src-tauri/Cargo.toml、src-tauri/Cargo.lock、services/local-agent/src/sandbox/mod.rs、.github/workflows/cloud-gateway-lab.yml、tests/cloud-gateway/scope-guard.test.mjs，以及需要真实授权存储的测试接线文件（实施前确认具体路径并更新清单）。新模块均少于 500 行；旧大文件只进行锚定局部修改。开发工具导出和补丁生成脚本不属于最终交付物。

## 任务列表
- [x] 1.1 读取基线、授权来源和逐符号图谱，确认生产接线尚缺。
  - 证据块：exec.rs 的 run_command 使用 command.spawn 或 managed process_tree::spawn；LinuxSandbox 仅在 local-agent 里可选附加。auth/聊天授权v1.rs:501-564 的 commit_local_admission 仅入口调用 ticket.expired()。
  - 涉及文件：只读；图谱 run36302640460 包含18组 context/impact。构造器 CRITICAL58，执行主链 HIGH，保留风险。
  - _需求: FR-1, FR-2, FR-6_ ｜ _设计: 架构设计、风险评估_
- [ ] 1.2 持久化完整 Plan，验证三份规格并完成风险估算。
  - 证据块：真实 start_feature 返回 delegated Plan，不代表任何代码已完成；首次必须用完整 Plan 调用 plan_heartbeat。
  - 涉及文件：本目录三份规格各少于200行；检查点与日志作为证据保存。
  - _需求: FR-6_ ｜ _设计: 决策6_
- [ ] 2.1 修复等待锁期间票据过期仍可提交的问题，并验证旧失败新通过。
  - 证据块：commit_local_admission 在 self.state.lock 和 gate.try_admit_generation 前仅检查一次 ticket.expired()。
  - 涉及文件：聊天授权v1.rs 局部增加时限检查与测试模块接线；新增 local_admission_deadline_tests.rs 少于250行。
  - _需求: FR-1_ ｜ _设计: 决策1_
- [ ] 2.2 添加私有运行时许可观察器和固定工作区命令隔离接入。
  - 证据块：LocalAdmissionPermit 已持有聊天与执行 guard；LinuxSandbox::prepare 返回拥有型内核准备状态，既有 pre_exec 调用 apply。
  - 涉及文件：runtime_admission.rs、linux_sandbox_bridge.rs 各少于350行；sandbox/mod.rs 局部新增命令接入；Cargo.toml/lock 仅本地路径依赖；context.rs 和 tools/mod.rs 条件编译接线。
  - _需求: FR-2, FR-3_ ｜ _设计: 决策2、决策3_
- [ ] 2.3 将真实进程启动、会话监督、授权失效清理与准确输出串接。
  - 证据块：exec.rs 当前在 spawn_readers().await 之后才在部分分支建立超时监督；session.rs::wait_for_readers 收束 I/O；异步 run 继续调用公共 dispatcher。
  - 涉及文件：exec.rs、session.rs、dispatch.rs、异步命令v1.rs 仅局部修改，新增逻辑放入 bridge 模块。
  - _需求: FR-4, FR-5_ ｜ _设计: 决策4、决策5_
- [ ] 3.1 对照每条验收条件执行真实内核、桌面和生命周期回归。
  - 证据块：已有132项Ubuntu local-agent 用例及Windows兼容套件不证明实际桌面接线；新增测试必须经过真实桌面本地许可和子进程。
  - 涉及文件：linux_sandbox_tests.rs、sandbox_command_attachment.rs 各少于450行；必要测试存储接线逐项审查。
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ ｜ _设计: 测试策略_
- [ ] 3.2 固定最终源码完成原生全量、范围守卫、代码审查与收敛。
  - 证据块：原 cloud-gateway-lab.yml 使用 allowed_exact 精确批准桌面路径；scope-guard.test.mjs 执行真实 Python 守卫而非复制允许列表。
  - 涉及文件：新增只读原生CI；修改精确范围守卫及正反例；本 tasks 收据。
  - _需求: FR-6_ ｜ _设计: 决策6、回滚_

## 检查点
- [ ] 规格检查与完整 Plan heartbeat 已成功持久化。
- [ ] FR-1 旧代码失败、新代码通过，并保留实际失败日志。
- [ ] 实际桌面执行已接线；不确定清理没有被报告为成功。
- [ ] Ubuntu/Windows 最终提交全量通过，源码 blob、tree 与执行日志对应。
- [ ] code_review 和 converge 返回可核验结论；物理验收仍未冒充通过。

## 需求覆盖矩阵
| 需求ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 决策1 | 1.1,2.1,3.1 | 未实施 |
| FR-2 | 决策2 | 2.2,3.1 | 未实施 |
| FR-3 | 决策3 | 2.2,3.1 | 未实施 |
| FR-4 | 决策4 | 2.3,3.1 | 未实施 |
| FR-5 | 决策5 | 2.3,3.1 | 未实施 |
| FR-6 | 决策6 | 1.1,1.2,3.2 | 准备中 |

## 文件变更清单
最终以已审查的逐文件 diff 为准，交付物清单中的测试接线待实际实现确认后锁定。禁止用路径前缀放宽整个桌面目录；禁止带入临时工具、测试机器配置、凭据或 dev workflow。新增模块超过行数预算须先分拆并更新这里，不压缩可读性规避预算。

## 检查清单
- [x] 全部任务对应需求、设计和已观察代码。
- [x] 真实设备验收不属于此工程增量的自动通过项。
- [ ] 文件清单与最终交付逐项一致，全部证据完备。

# 任务清单：ubuntu-execution-sandbox

## 交付物清单
Issue #73 / Epic #32 的库级首增量：Linux x86_64 的 Landlock ABI3+、seccomp、持续持有的工作区FD，以及显式宿主策略的普通进程/PTY接入。只有带策略的调用获得隔离；宿主强制挂载不属于本增量的已交付物。

## 任务列表
- [x] 1.1 恢复检查点并对启动符号建立索引、context和impact。
  - 证据块：process.rs `ProcessManager::start` 与 pty_unix.rs `spawn`；pinned GitNexus 1.6.9。
  - 涉及文件：验证日志，无规则文件改动。
  - _需求: FR-1, FR-6_ ｜ _设计: 架构设计_
- [x] 2.1 实现根FD、Landlock规则、seccomp与静态错误分类。
  - 证据块：sandbox/linux.rs 的 open_beneath、prepare、PreparedSandbox::apply；filter.rs 的 program。
  - 涉及文件：sandbox/mod.rs、linux.rs、filter.rs（各少于500行），lib.rs 小范围导出。
  - _需求: FR-2, FR-3, FR-4_ ｜ _设计: 决策1、决策2_
- [x] 2.2 为普通进程和PTY接入显式宿主策略。
  - 证据块：ExecSpec/PtySpec::with_sandbox；进程exec前限制，PTY建会话后限制。
  - 涉及文件：process.rs、pty.rs、pty_unix.rs；Windows实现文件不改。
  - _需求: FR-1, FR-5_ ｜ _设计: 架构设计_
- [x] 3.1 执行内核隔离、生命周期与平台兼容自动验收。
  - 证据块：原生运行36260633250，Ubuntu113项、Windows91项；Ubuntu14项内核测试包含在113项内。
  - 涉及文件：sandbox/tests.rs、tests/linux_sandbox.rs、src/bin/sandbox_fixture.rs。
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ ｜ _设计: 测试策略_
- [x] 3.2 添加只读双平台CI、规格精确路径正反例并审查真实暂存差异。
  - 证据块：两平台各55项范围守卫；真实16文件 staged diff，无相邻路径放宽。
  - 涉及文件：cloud-gateway-ubuntu-sandbox.yml、cloud-gateway-lab.yml、scope-guard.test.mjs。
  - _需求: FR-6_ ｜ _设计: 测试策略、回滚_

## 需求覆盖矩阵
| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 架构设计、决策3 | 1.1,2.2,3.1 | 库级自动验收通过；宿主挂载未交付 |
| FR-2 | 决策1 | 2.1,3.1 | 自动验收通过 |
| FR-3 | 决策2 | 2.1,3.1 | 补充回归通过 |
| FR-4 | 决策2 | 2.1,3.1 | 自动验收通过 |
| FR-5 | 架构设计 | 2.2,3.1 | 双平台回归通过 |
| FR-6 | 决策3、回滚 | 1.1,3.2 | 原生证据已核验；发布后另验 |

## 验收证据与保留的失败
- 基线：593b173cb7c36d3ac7b8b633f1410399756ad7e5。
- 初轮运行36259716227：Ubuntu110 / Windows91项通过，但没有覆盖新系统调用与队列信号缺口；保留为历史，不能替代修正后的验收。
- 修正运行36260633250：先将旧生产过滤器与新增单测组合，5项中3通过、2如期失败；恢复修正后代码，再运行完整双平台检查。
- 修正源码树：abc373a5475a30fb1a33d2424645437ca948cc5c。本次收据更新仅改变本Markdown；运行时代码和测试仍与该受检树相同。
- Ubuntu：77单元 +14内核隔离 +12普通进程 +10PTY =113项；Windows：68单元 +12普通进程 +11PTY =91项。最终套件零失败、零忽略。重复运行不算新增独立用例。
- 两平台fmt、all-target Clippy、生产库-D warnings、55项范围守卫通过。Windows内核步骤为条件跳过，不是隔离通过。
- 源码与原生产物ZIP、内部SHA256和16个Git blob身份已核验。正式候选与父功能分支CI仍需按发布后实际revision另行核验；以PR/Issue交付收据为准。
- GitNexus存在Rust/FTS覆盖限制；fixture入口未被索引，已复核它只作为独立测试程序。图谱与自动测试不是独立安全认证。

## 修正与已知限制
seccomp拒绝335..423及>=453的未审查系统调用，防止新metadata接口绕过旧过滤器；同时拒绝队列信号和外部调度控制。运行时目录只读。工作区内chmod/xattr等也保守拒绝，不能承诺任意工具链透明兼容。只读stat/路径存在性不隐藏；不是完整namespace或微虚机隔离。
依据：https://docs.kernel.org/userspace-api/landlock.html 及 https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/entry/syscalls/syscall_64.tbl 。

## 后续工程（不是延期的真实测试）
宿主/Agent需把LocalAdmission + ExecPolicy批准的工作区对象绑定到策略，并为需隔离的执行入口强制附加策略；不得接受模型传入的关闭沙箱开关。补充实际调度、遗漏策略拒绝、撤销/取消和工具链兼容性自动回归后，才可完成#73。真实工作站、VPS、ChatGPT仍明确延期，不能将它们或宿主集成标记通过。

## 文件变更清单
仅16个文件：上述local-agent代码/测试、3个规格文档、只读CI和精确范围守卫。无桌面/云端授权、Windows实现、根依赖、安装器、密钥、真实主机改动。辅助验证分支不得合并。

## 回滚
候选只进入独立分支；后续若纳入feature，复读最新HEAD后只允许非强制快进。回滚采用普通revert，不重写共享历史，不删除持久授权数据。main、生产发布和部署不在授权范围。

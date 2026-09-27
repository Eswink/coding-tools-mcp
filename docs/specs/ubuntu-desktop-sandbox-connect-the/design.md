# 设计文档：ubuntu-desktop-sandbox-connect-the

## 概述
覆盖 FR-1、FR-2、FR-3、FR-4、FR-5、FR-6 与 NFR-1 至 NFR-4。基线 9b2639d47aaecc0a903124404c9c97cbf1f806d6。使用桌面已有私有许可包装运行时观察器，不改变库级 LocalAdmission 的不可构造边界。

## 技术方案
### 技术选型
继续使用 Rust、Tokio、桌面现有授权与执行围栏、已有 LinuxSandbox 和 ExecPolicy。Linux 目标增加本仓库 local-agent 路径依赖，不升级第三方依赖。新代码通过条件编译与 Windows 隔离。
### 架构设计
实际 MCP/Actions 公共 dispatcher -> 会话准入和既有策略 -> exec_command/run_command -> 固定工作区边界、ExecPolicy、清洁环境和内核准备 -> 桌面最终 RuntimeAdmission -> 进程树创建 -> 会话自持有监督 -> 输出、取消与清理。
异步任务继续经过相同 dispatcher。内建诊断没有子进程，不宣称内核隔离。真实 PTY 替换及 Git/Harness 隐式子进程属于独立后续工作。

## 数据模型
- RuntimeAdmission：拥有已有 LocalAdmissionPermit、授权器引用、会话/工作区/授权记录身份、所需权限和单调期限；所有字段私有，不实现 Clone 或序列化。
- LinuxExecutionBoundary：持有批准工作区的 LinuxSandbox 初始化结果与共享八槽信号量；初始化失败保持可报告状态，禁止回退。
- SandboxExecutionGuard：拥有 RuntimeAdmission 和活动槽，随会话清理后释放；不确定终止时继续保留。
- 会话隔离标志独立于许可是否已释放，确保终态结果仍报告真实边界。
不改变持久授权文件格式，不从网络数据恢复执行许可。

## API 设计
LinuxSandbox::attach_to_command(&mut tokio::process::Command) 在父进程准备固定 cwd/program 的限制，安装只在子进程执行的 pre_exec 闭包。该 API 是受信任底层机制，不是授权源。
ChatAuthorizer::commit_runtime_admission 消费既有私有票据，调用最终准入，再绑定确切授权记录及单调期限。
RuntimeAdmission::authorization_ended 只观察，不触碰或续期授权；状态锁忙时不阻塞执行监督，固定期限仍生效，后续检查检测撤销。
linux_sandbox_bridge 的准备与生命周期接口仅在桌面 crate 内可见。它拒绝未知模型参数和权限不足，不能通过参数关闭沙箱。

## 文件结构
新增 auth/runtime_admission.rs、auth/local_admission_deadline_tests.rs、tools/linux_sandbox_bridge.rs 和分拆的桌面隔离测试模块。局部修改 auth/聊天授权v1.rs、tools/context.rs、tools/exec.rs、tools/session.rs、tools/dispatch.rs、tools/mod.rs、tools/异步命令v1.rs；Linux 路径依赖涉及 src-tauri/Cargo.toml/Cargo.lock。local-agent/sandbox/mod.rs 添加命令接入方法和独立接入测试。CI 与范围守卫只允许实际审查的精确路径。开发辅助脚本和工具包不得并入最终候选。

## 设计决策
### 决策 1：在等待之后验证时限（FR-1）
在获得授权锁后、执行锁准入后、持久围栏完成后重新检查票据。先进行只读校验，再增加计数；失败时由现有 guard 析构释放已分配许可。保留可能已写入的保守恢复状态，不把失败解释为没有任何持久写入。
### 决策 2：包装现有许可，而非公开铸造器（FR-2）
不公开 LocalAdmission 构造器，不由调用参数生成能力。新的私有包装器使用现有桌面最终准入函数与真实授权记录。仍要求全部身份、generation、期限和作用域。
### 决策 3：重用内核规则与显式环境（FR-3）
复用已验收 Landlock/seccomp；进程 exec 前强制安装，失败不重试。只在宿主侧提供固定运行时环境，不透传用户令牌和模型 env。工作区句柄在 ToolContext 生命周期内持续保留。
### 决策 4：监督器先于可取消等待（FR-4）
创建会话后，在第一个可中断 await 前安装持有会话的监督器。授权撤销与绝对/空闲期限失效触发进程树清理；Pause 仍允许已提交操作完成。guard 只在子进程退出、进程树状态确定、读写任务收束之后释放，不能在持有授权锁的状态检查路径释放，以免锁反入。
### 决策 5：报告事实而非能力宣传（FR-5）
成功的隔离进程才报告 sandbox_enforced=true；内建诊断和失败启动不伪称通过。环境页区分 required、初始化可用和实际启动检查。异步去重及不重放记录保持原始实现。
### 决策 6：独立候选和原生证据（FR-6）
开发分支用于规格、旧新回归和依赖准备；最终源码由经审查的精确 Git blob 构造干净提交并重新验收。任何运行中、辅助成功或不完整输出均不当作最终门禁通过。

## 测试策略
FR-1：真实本地授权下分别持有授权状态锁和执行锁，让票据在等待期间过期；旧代码必须出现获准错误，修复后拒绝且计数归零，正常有效票据仍获准。
FR-2/FR-3：真实桌面工具与内核进行工作区成功读写、越界/软链接/网络拒绝、环境清理、缺失权限和模型绕过字段拒绝、目录替换不转移授权。
FR-4：已提交命令撤销、单调期限、future 取消、子孙进程清理、八槽容量和 Pause 语义。
FR-5：原生输出、内建诊断、交互管道、异步提交去重与输出/取消；Windows 完整兼容回归。
FR-6：锁定依赖的 Ubuntu24.04 与 Windows2025 全量桌面及 local-agent 测试，严格编译、范围正反例、真实暂存图谱、code_review、最终候选身份和原始日志。

## 风险评估
ToolContext 构造器图谱为 CRITICAL/58 上游，exec、错误路径、环境报告与会话初始化为 HIGH；必须覆盖实际 HTTP、会话/异步、授权/恢复、Windows 兼容主链，不降低为只看单元测试。Rust 同名解析存在错误连接，额外直接检查源码。沙箱保守禁止 chmod/xattr 等，不能承诺完整工具链兼容。最终实现不覆盖 Git/Harness 全部隐式进程、真正桌面 PTY、Windows 沙箱或云端挂载，因此整体预发布仍有独立门禁。

## 回滚
最终候选只进入独立功能分支；集成前重读 feature HEAD，使用非强制快进。出现回归使用普通 revert，不重写共享历史、不删除授权或恢复记录。开发工作流永不自动修改 ref 或发布。

## 检查清单
- [x] 需求与架构、数据和生命周期检查点建立对应关系。
- [x] 明确高风险调用链、底层隔离限制和范围之外能力。
- [ ] 原生验证、审查和最终提交核验完成。

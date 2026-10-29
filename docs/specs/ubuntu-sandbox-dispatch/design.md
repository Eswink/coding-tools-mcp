# 设计文档：ubuntu-sandbox-dispatch
## 概述
覆盖FR-1、FR-2、FR-3、FR-4、FR-5、FR-6。新增Linux-only SandboxedDispatch构造强制沙箱注册表；底层可选API不改。
## 技术方案
### 技术选型
复用现有Tokio watch/oneshot/Mutex/Semaphore、ExecPolicy、LinuxSandbox和Process/PTY管理器，无新依赖。
### 架构设计
可信宿主已有LocalAdmission + approved root + ExecPolicy -> SandboxedDispatch -> ToolRegistry.invoke -> 固定Executor -> 策略批准 -> 强制沙箱spec -> 有界拥有型启动/等待worker -> 现有进程监督器。
## 数据模型
不可序列化宿主绑定保存会话/工作区/generation/能力上限/到期上限和固定目录。独立只读配置、活动槽和撤销watch，开始锁协调启动与永久撤销。无已知结果重放或云端授权。
## API设计
SandboxedDispatch::new(&LocalAdmission, workspace_root, ExecPolicy) -> Result<Self,ToolError>。
invoke(&ToolCall,&LocalAdmission) -> ToolFuture：系统时间不由模型输入。
revoke().await -> Result<(),ToolError>：关闭入口、通知取消、有限等待活动worker退出。Drop通知但不伪称同步排空。
仅受信任代码可得到实例，不公开内部注册表/执行器/裸session。
## 设计决策
FR-1/FR-2：要求已有LocalAdmission而不是引入公开mint；这使真实桌面桥接仍是可见后续项。
FR-3：拥有型worker不在PTY的spawn_blocking中途被丢弃；调用future取消通过oneshot关闭传递，worker完成启动后负责关闭session。Tokio运行时强制销毁仍不在运行中排空保证内。
FR-3：持有开始锁直到start返回，撤销只能在之前或之后线性化；检查在锁内再次执行。不报告取消等于未执行。
FR-4：固定策略不能被入参省略/替换；cwd使用相对组件并由底层openat2验证。所有调用要求ProcessExec+WorkspaceRead+WorkspaceWrite，因底层策略是工作区读写。
FR-5：保守兼容性，不改变过滤器。
## 文件结构
services/local-agent/src/dispatch/{mod.rs,execute.rs,tests.rs}，lib.rs仅cfg接线；现有只读沙箱workflow补强门槛；三份本规格精确路径允许并增加范围测试。
## 测试策略
FR-1拒绝矩阵；FR-2参数/策略禁止及未知字段；FR-3revoke/cancel/drop/过期/未poll；FR-4实际内核执行、越界和网络及PTY；FR-5shell/Python兼容；FR-6锁定原生全套、范围正反、图谱和源码哈希。
## 风险评估
实际本地授权桥接尚缺，不将内部fixture当作Tauri授权验收；FTS/Rust图谱不完整；start_blocking不可中止须保留worker所有权；库层旧接口仍可信代码可调用但不暴露模型。
## 回滚
复读功能HEAD后普通revert本提交，不变更持久授权数据，不强制重写历史。
## 检查清单
- [x] FR-1至FR-6映射到实现与测试。

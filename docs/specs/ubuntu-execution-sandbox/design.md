# 设计文档：ubuntu-execution-sandbox

## 概述
覆盖 FR-1、FR-2、FR-3、FR-4、FR-5、FR-6。宿主先完成 Registry/ExecPolicy，再为 ExecSpec/PtySpec 附加 LinuxSandbox；没有任何新的远程工具或可反序列化策略。既有无沙箱低层构造器保留兼容，生产宿主挂载未在本增量实施。

## 技术方案
### 技术选型
Landlock ABI3 提供路径内容读写、跨目录引用和截断约束；seccomp x86_64 BPF 拒绝网络、跨进程/命名空间和外部元数据修改。较低 ABI 不作降级。openat2 用于根句柄之下的无符号链接 cwd 解析，close_range(CLOEXEC) 消除额外描述符继承。已有 libc 足够，不新增 crate。

### 架构设计
LocalAdmission -> ExecPolicy -> trusted host spec.with_sandbox -> parent-side prepare -> child pre_exec -> Landlock + seccomp -> exec -> existing bounded supervisor。
PTY 在 setsid/controlling-terminal/dup2 后应用相同限制；过滤器随后禁止 setsid/setpgid，后代不能脱离现有清理进程组。父进程不应用任何限制。

## 数据模型
LinuxSandbox 保留 Arc 包装的根 O_PATH FD 和规范根路径，不实现 serde。PreparedSandbox 持有 ruleset FD、cwd FD、预先分配的 BPF 程序，仅在受信任启动代码使用。错误只有静态公开信息。

## API 设计
- LinuxSandbox::new(workspace_root) -> Result<Self, SandboxError>：受信任本地策略构造。
- ExecSpec::with_sandbox(LinuxSandbox) -> Self、PtySpec::with_sandbox(LinuxSandbox) -> Self：仅 Linux 可用。
- LinuxSandbox::prepare(program,cwd) -> Result<PreparedSandbox, SandboxError>：内部调用，无用户程序执行。
- PreparedSandbox::apply() -> io::Result<()>：内部 fork 后方法，不分配内存、不加锁。

## 文件结构
新增 sandbox/mod.rs、sandbox/linux.rs、sandbox/filter.rs、sandbox/tests.rs；新增 sandbox_fixture.rs 和 tests/linux_sandbox.rs。
修改 process.rs、pty.rs、pty_unix.rs 与 lib.rs 的小范围接线；既有500行以上模块不进行无关格式化重写。
新增只读 cloud-gateway-ubuntu-sandbox.yml；三个本规格文档通过精确路径加入既有范围守卫，补正反例。

## 设计决策
### 决策 1: 句柄授权而非检查后按名字重新授权（FR-2）
根目录在策略构造时保留，cwd 使用 openat2 根内解析；即便根目录在父进程中重命名，授权也不转移到替代路径。运行时目录只读；工作区外普通内容不开放。
### 决策 2: 不依赖网络 namespace 或 root（FR-3、FR-4）
Landlock3 与 seccomp 不需要 root；拒绝 root/euid变化。socket 和危险IPC系统调用一律拒绝；clone3 返回 ENOSYS 以允许 libc 使用被过滤的 clone 回退。x32/非x86_64 ABI 不进入许可路径。
### 决策 3: 隔离不等于授权或部署（FR-1、FR-6）
不修改 ExecPolicy、LocalAdmission、桌面和云端挂载；新增接口只接受宿主创建的策略。无策略的低层 API 不承诺沙箱。此设计收敛范围是可测试的库级首增量，#73 的实际宿主启用保持后续事项。

## 测试策略
FR-1：原授权单测不变，新增拒绝授权不会到达沙箱启动的回归。
FR-2：正常工作区读写、外部读写、符号链接、根替换、工作目录逃逸、继承FD。
FR-3：TCP/UDP/Unix sockets、setsid/setpgid、子进程继承及取消。
FR-4：子进程预先拒绝 Landlock 系统调用后验证无用户程序落盘，公开错误脱敏。
FR-5：原 Windows/Ubuntu 全套回归，新增沙箱 PTY/普通进程输入输出、超时和树清理。
FR-6：只读双平台CI、精确树和产物哈希、真实 staged detect_changes；无真机/VPS操作。

## 风险评估
Rust/FTS 图谱覆盖不足：用实际符号UID、调用方源码和全量CI补充，不将零调用结果当完整安全证明。
元数据修改在工作区内也被保守拒绝；不承诺任意工具链透明兼容。
seccomp 黑名单不是内核漏洞隔离：不承诺微虚机安全；文件路径存在性/stat 不隐藏。限制未来 syscall 语义需持续复审。
沙箱原语缺失：返回错误，不回退。没有网络放行或宿主挂载，不能把库测试当成已部署。
继承/进程组逃逸：关闭额外FD并拒绝setsid、setpgid、clone危险标志及namespace入口。

## 回滚
候选只在独立分支；如纳入feature则复读新HEAD后普通revert，不force push，不修改持久授权数据。main/部署/密钥不变。

## 检查清单
- [x] FR-1 至 FR-6 全部映射到技术方案与自动验收。
- [x] API、范围、内核依赖和恢复方法明确。

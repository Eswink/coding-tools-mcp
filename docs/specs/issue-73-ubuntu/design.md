# 设计文档：issue-73-ubuntu

## 概述

本设计在 local-agent 的低层 process/PTY spawn 边界引入 Linux-only sandbox facade。策略与 admission 仍先于 spawn；sandbox 只负责将已决定的最小权限落实到 Linux kernel。默认策略为 workspace 外只读、network deny。Network allow 只能由 `VerifiedInvocation` 中的 `Capability::Network` 派生。

**对应需求:** FR-1, FR-2, FR-3, FR-4, NFR-1..4

---

## 技术方案

### 技术选型

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| 文件系统写隔离 | Linux Landlock raw syscall | 内核强制、无需外部 daemon；ABI 7 runner 已实测 | FR-1 |
| 网络默认拒绝 | seccomp-BPF deny new socket/socketpair | 覆盖 TCP/UDP/Unix 新 socket，避免 Landlock ABI7 的网络范围不足 | FR-2 |
| 权限来源 | `VerifiedInvocation` capability | 不增加可伪造 public bool 开关 | FR-2 |
| child 安装 | parent prepare + child raw-syscall apply | 避免 post-fork 分配/复杂 Rust 调用 | FR-1, FR-3 |
| Windows | cfg-gated no-op / existing path | 保持 ConPTY/process baseline | FR-4 |

### 架构设计

```
ToolRegistry.invoke
  -> VerifiedInvocation (LocalAdmission checked)
  -> executor / spec construction
       -> default Linux sandbox: workspace-write + deny-network
       -> optional Network grant derived from VerifiedInvocation only
  -> ProcessManager / PtyManager
       -> parent: sandbox::prepare(canonical_workspace, network_mode)
       -> child pre_exec:
            PR_SET_NO_NEW_PRIVS
            Landlock restrict_self(prepared ruleset fd)
            seccomp filter install when network denied
       -> exec target
```

Landlock 只声明 write-class handled rights：write/create/remove/rename/refer/truncate 等。未 handled 的 read/execute 权限继续由宿主 Unix DAC 控制，使 `/usr/bin`、动态 loader 与共享库可读/可执行，同时 workspace 外写入 fail-closed。

网络 deny filter 在 child 没有继承网络 fd 的前提下拒绝 `socket` 与 `socketpair`，从源头阻止创建 TCP/UDP/Unix sockets。Network capability 存在时不安装网络 deny filter，但 Landlock write confinement 仍安装。

---

## 数据模型

不涉及持久化。

内部 runtime 增加：
- `SandboxErrorKind`: Unsupported / Setup / Apply。
- `LinuxSandboxPlan`: parent prepared Landlock fd + optional seccomp program；Debug 不显示 host path。
- `ExecSpec/PtySpec` 内部 sandbox network mode，Linux 默认 Denied。
- capability-gated network enable 方法接受 `VerifiedInvocation`，不接受裸 bool 作为 public authority。

---

## API 设计

| 函数/类型 | 契约 | 关联需求 |
|---|---|---|
| `sandbox::prepare(workspace, allow_network)` | parent 侧 canonicalize + Landlock ruleset/BPF 准备；失败即 error | FR-1, FR-2 |
| `LinuxSandboxPlan::install_in_child()` | pre_exec 中仅 raw syscall/close，失败阻止 exec | FR-1, FR-3 |
| `ExecSpec/PtySpec network grant` | 只从 verified local Network capability 派生 | FR-2 |
| process/PTY spawn wiring | Ubuntu child exec 前安装 sandbox；Windows 不走该实现 | FR-3, FR-4 |

---

## 文件结构

```
services/local-agent/
├── Cargo.toml                         # 仅在确有需要时调整；优先复用 libc
├── src/
│   ├── lib.rs                         # 导出稳定 error/policy surface
│   ├── registry.rs                    # VerifiedInvocation capability query（最小）
│   ├── process.rs                     # ExecSpec + parent prepare
│   ├── process_tree.rs                # Unix child pre_exec wiring
│   ├── pty.rs                         # PtySpec sandbox policy
│   ├── pty_unix.rs                    # existing PTY pre_exec + sandbox apply
│   ├── sandbox.rs                     # cfg facade / bounded public error
│   └── sandbox_linux.rs               # Landlock + seccomp raw implementation
└── tests/
    ├── process_runtime.rs
    ├── pty_runtime.rs
    └── sandbox_runtime.rs             # Ubuntu integration contracts
```

单文件预算：`sandbox_linux.rs < 500` 行，其余每个增量 <150 行。

---

## 设计决策

### 决策 1: 不使用 bubblewrap（FR-1）

**问题**: 外部 sandbox 工具可能未随产品安装。  
**决策**: 第一增量使用内核原语，不引入必须存在的外部 binary。  
**理由**: issue 要求 primitive 不可用时 fail-closed，而非依赖未打包工具。

### 决策 2: Landlock 限制写，不限制全局只读读取（FR-1）

**问题**: execve、动态 loader 和宿主 executable 需要读取 workspace 外系统文件。  
**决策**: handled rights 只包含 write-class operations；workspace root 获得这些 rights。  
**理由**: 与 Codex-style “workspace writable / host read-only”边界一致，且不会为动态依赖建立脆弱 allowlist。

### 决策 3: seccomp 默认禁止新 socket（FR-2）

**问题**: Ubuntu runner Landlock ABI 7 不能完整覆盖所有网络族/UDP。  
**决策**: 无 Network capability 时拒绝 `socket`、`socketpair` syscall；Network capability 时省略该 filter。  
**理由**: 默认无网络覆盖 TCP/UDP/Unix socket 创建，规则小且可在 parent 预构建。

### 决策 4: 不把 process-group/Job Object 当 sandbox（FR-3）

**问题**: 现有 process_tree 只处理生命周期。  
**决策**: sandbox 单独模块，process-tree 保持 kill/cancel 职责。  
**理由**: 安全隔离与生命周期 containment 分离，便于 Windows 后续独立实现。

---

## 测试策略

Ubuntu 24.04：
1. workspace 内 write 成功。
2. workspace 外 write 被 EPERM/EACCES 拒绝且目标未改变。
3. workspace 内 symlink 指向外部时 write 被拒绝。
4. 无 Network capability 时 fixture 新建 socket 失败。
5. 有本地 Network capability 的 unit path 可允许 socket 创建。
6. Landlock/seccomp setup failure 在 exec 前映射 Sandbox error。
7. process timeout/cancel/grandchild cleanup 原回归全绿。
8. PTY terminal/read/write/resize/cancel/tree cleanup 在 sandbox 下全绿。

Windows 2025：
- 完整 local-agent process + PTY tests 不改变行为；Linux module 不编译。

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| pre_exec 非 async-signal-safe | 高 | parent prepare；child 只执行 raw syscall/close |
| Landlock ABI 差异 | 高 | require ABI>=3；不足即 fail closed |
| seccomp arch/syscall 表错误 | 高 | cfg arch + audit arch check；Ubuntu fixture 实测 |
| Network capability 绕过 | 高 | 只从不可伪造 VerifiedInvocation 派生 |
| PTY 行为回归 | 中 | 在现有 setsid/dup2 后安装并跑完整 PTY regression |
| Windows 回归 | 中 | cfg 隔离 + Windows 2025 full local-agent tests |

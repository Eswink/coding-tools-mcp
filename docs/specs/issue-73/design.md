# 设计文档：issue-73

## 概述

本设计在 `services/local-agent` 中新增 Ubuntu/Linux child sandbox 层。既有 `ToolRegistry::invoke` 继续负责 LocalAdmission/capability，ExecPolicy 继续负责命令授权；sandbox 只在已获准 child 的 spawn 边界安装，不创造新权限。

**对应需求:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, NFR-1..NFR-5

---

## 技术方案

### 技术选型

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| Filesystem LSM | Landlock | 无特权、可叠加、child 及其后代继承；适合 workspace path-beneath 约束 | FR-2, FR-5 |
| Network syscall boundary | seccomp-BPF | Ubuntu 24.04 目标不能仅依赖 Landlock 覆盖所有 IP socket 类型；seccomp 可按 `socket` syscall domain 拒绝 AF_INET/AF_INET6 | FR-3, FR-5 |
| Spawn integration | parent prepare + child pre-exec install | 避免 fork 后做复杂分配/配置；同一 prepared policy 可供 non-PTY 与 PTY 使用 | FR-1, FR-4 |
| Runtime dependencies | Linux-target-only Rust dependencies | Windows dependency graph与行为不变 | FR-5, NFR-2 |

### 架构设计

```text
ToolRegistry::invoke
  -> LocalAdmission / capability checks
  -> executor + ExecPolicy authorization
  -> SandboxPolicy::for_workspace(canonical workspace)
       -> LinuxSandbox::prepare()
            - validate Landlock hard requirements
            - open/prepare workspace + minimal host read/exec roots
            - compile seccomp program for AF_INET/AF_INET6 denial
  -> ProcessManager::start / PtyManager::start
       -> child pre-exec:
            1. existing process-group/session setup
            2. install Landlock ruleset
            3. install seccomp filter
            4. exec approved program
  -> existing bounded I/O / timeout / cancellation / ProcessTree
```

Sandbox policy is a post-authorization execution constraint. It does not receive conversation IDs, OAuth state or cloud grants.

---

## 数据模型

No persisted data.

| 类型 | 字段 | 约束 | 说明 |
|---|---|---|---|
| `SandboxPolicy` | workspace root, network mode | canonical workspace; network defaults deny | non-secret execution constraint |
| `PreparedSandbox` | prepared Landlock/seccomp state | Linux-only; not serializable | parent-prepared child install state |
| `SandboxError` | kind + static public message | no host path/argv/env | stable failure classification |

---

## API 设计

| 方法/函数 | 签名方向 | 入参 | 出参 | 关联需求 |
|---|---|---|---|---|
| `SandboxPolicy::workspace_default` | construct | canonical workspace | policy/error | FR-2, FR-3 |
| `prepare_linux_sandbox` | parent prepare | policy | prepared state/error | FR-5 |
| `PreparedSandbox::install_child` | child pre-exec | prepared state | io::Result | FR-1, FR-5 |
| `process_tree::spawn_sandboxed` or equivalent narrow seam | non-PTY spawn | Command + prepared sandbox | Child + ProcessTree | FR-1, FR-4 |
| Unix PTY platform spawn integration | PTY spawn | PtySpec + prepared sandbox | existing Spawned | FR-4 |

No public MCP/Tauri API change is required.

---

## 文件结构

```text
services/local-agent/
├── Cargo.toml                                  # Linux-target dependencies only
├── src/
│   ├── lib.rs                                  # module/export wiring
│   ├── sandbox.rs                              # shared policy/error/prepared interface (<500 lines)
│   ├── sandbox_linux.rs                        # Landlock + seccomp implementation (<500 lines)
│   ├── process.rs                              # minimal ProcessManager integration only
│   ├── process_tree.rs                         # minimal Unix spawn seam only
│   ├── pty.rs                                  # minimal policy plumbing only if required
│   └── pty_unix.rs                             # install same prepared sandbox before exec
└── tests/
    └── sandbox_runtime.rs                      # Ubuntu behavioral regression suite (<500 lines)
```

If focused PTY tests exceed the single test file budget, split into `sandbox_runtime.rs` and `sandbox_pty.rs`.

---

## 设计决策

### 决策 1: Landlock + seccomp，而非单一 primitive（FR-2, FR-3, FR-5）

**问题**: filesystem isolation 与“网络默认拒绝”需要在 Ubuntu 24.04 上同时成立。

**选项**
1. Landlock only。
2. seccomp only。
3. Landlock filesystem + seccomp AF_INET/AF_INET6 network denial。
4. 外部 bubblewrap/container helper。

**决策**: 选择 3。

**理由**: Landlock 是无特权 workspace path isolation 的直接内核机制；但目标环境不能把全部 IP 网络拒绝建立在单一 Landlock ABI 假设上。seccomp 只负责 IP socket domain，避免构建庞大 syscall allowlist，也不需要 host 安装 libseccomp daemon/helper。

### 决策 2: Parent prepare，child 只执行有界 install（FR-1, FR-4）

**问题**: Unix `pre_exec` 处于 fork 后环境，不适合复杂 Rust 分配/加锁。

**决策**: workspace canonicalization、Landlock rule preparation、seccomp BPF compile 都在 parent 完成；child closure 只执行已准备 fd/program 的内核安装动作和现有 session/process-group 操作。

### 决策 3: workspace 可写，host runtime 只读/执行（FR-2）

**问题**: 完全禁止 workspace 外读取会导致动态链接程序无法启动。

**决策**: workspace root 允许当前工具需要的 read/write/create/remove/execute；host executable 及动态 loader/library roots只授予 read/execute。不得授权用户 home、SSH、浏览器数据、其他 workspace 等任意 host path。

### 决策 4: Primitive 缺失时拒绝执行，不降级（FR-5）

Landlock compatibility 必须达到设计要求；seccomp install 必须成功。任何 unsupported/partial 状态映射成 stable sandbox-unavailable/spawn error，不运行 payload。

### 决策 5: Windows 保持原实现（FR-5, NFR-2）

所有 sandbox module 的 Linux 实现通过 cfg 隔离；Windows `process_tree_windows.rs`、`pty_windows.rs` 不改语义。

---

## 测试策略

### Ubuntu 24.04
- 正常 workspace read/write 成功。
- absolute path 写 workspace 外失败。
- workspace symlink 指向外部路径，外部 read/write 按 policy 拒绝。
- `socket(AF_INET, ...)` / `socket(AF_INET6, ...)` 失败；覆盖 TCP/UDP creation。
- Landlock unsupported/partial 模拟路径 fail-closed。
- seccomp install failure seam fail-closed。
- timeout、cancel、successful-parent-with-grandchild cleanup 保持现有结果。
- PTY echo/read/write/resize/close 在 sandbox 下通过；PTY child 网络/escape 同样拒绝。
- bounded stdout/stderr 不退化。

### Windows 2025
- existing process runtime + PTY suite 全通过。
- sandbox-specific API 不激活 Linux enforcement，不修改 Windows child creation semantics。

### Review gates
- pinned GitNexus impact before each production symbol edit。
- HIGH/CRITICAL stops production edit until review。
- staged `detect-changes` sees real candidate。
- candidate source hashes + artifacts recorded。

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| pre_exec 中调用非 async-signal-safe 高层代码 | 高 | parent prepare，child 只 install 已准备 kernel state |
| Landlock ABI 部分支持导致假 sandbox | 高 | hard requirement / fully-enforced check，失败即拒绝 |
| seccomp 误伤 Unix IPC/PTY | 中 | 只拒绝 AF_INET/AF_INET6 socket domain，不做 broad syscall allowlist |
| 动态链接程序因 host read 受限无法启动 | 中 | 显式最小 runtime read/exec roots + CI fixture |
| PTY 成为绕过路径 | 高 | PTY/non-PTY 共用同一 SandboxPolicy + 同等负向测试 |
| Windows 行为漂移 | 高 | cfg Linux-only + Windows full regression |

---

## 检查清单

- [x] 技术方案与现有 registry/process/PTTY 架构一致
- [x] 所有 FR 有对应设计
- [x] 文件路径对照真实仓库
- [x] 无持久数据/对外 wire schema 变更
- [x] 关键安全决策已记录
- [x] 测试覆盖正向、逃逸、网络、fail-closed、取消与平台回归

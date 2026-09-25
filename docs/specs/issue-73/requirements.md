# 需求文档：issue-73

## 功能概述

为 `services/local-agent` 增加 Ubuntu-only 本地执行 sandbox。该 sandbox 位于既有本地授权/ExecPolicy 判定之后、真正创建 child 之前，用 Linux 内核原语将已获准命令限制在批准 workspace 的文件系统边界内，并默认拒绝 IPv4/IPv6 网络能力。若 required Linux isolation primitive 无法完整启用，则执行必须 fail-closed，不得静默退化为 unsandboxed execution。

## 历史经验与坑

- **可复用经验**: 现有 `ToolRegistry::invoke` 已先验证 conversation/workspace/capability，并通过不可伪造的 `VerifiedInvocation` 将本地授权与 executor 调用绑定；sandbox 不应复制或替代这层授权。
- **可复用经验**: 现有 `ProcessTree`、PTY lifecycle、bounded stdout/stderr、timeout/cancel 行为已通过 Windows/Ubuntu CI 验证，应作为 sandbox 之外的既有契约保留。
- **必须规避的坑**: 不得把 process group/Job Object 当作 security sandbox；`process_tree.rs` 已明确说明它只做 lifecycle containment。
- **必须规避的坑**: Landlock 对网络能力的覆盖依赖 ABI；Ubuntu 24.04 的目标不能仅靠 Landlock 来宣称“所有网络默认拒绝”。设计必须额外使用 seccomp-BPF 拒绝 AF_INET/AF_INET6 socket 创建，或在该能力不可用时 fail-closed。
- **必须规避的坑**: child-side `pre_exec` 处于 fork 后环境；不能在那里执行可能分配内存、加锁或读取复杂配置的高层逻辑。所有可准备的数据应在 parent 侧完成，child 侧只安装预编译/预打开的隔离状态。

## 术语定义

- **LocalAdmission**: `ToolRegistry::invoke` 在本地验证 conversation、workspace、capability 和期限后产生的授权上下文。
- **ExecPolicy**: 对已获准执行请求做命令前缀/host executable/approval 判定的策略层。
- **SandboxPolicy**: 仅描述已获准 child 的 Linux 隔离要求，不授予命令执行权。
- **PreparedSandbox**: parent 侧准备完成、可在 child `pre_exec` 中以最小 syscall 序列安装的 sandbox 状态。
- **workspace escape**: child 对批准 workspace 外部路径执行未允许的读写/创建/删除/执行等访问。
- **network capability**: child 创建或使用 IPv4/IPv6 网络 socket 的能力；本增量默认拒绝。

---

## 范围边界

**In Scope**
- Ubuntu/Linux only 的本地 child sandbox。
- 对 non-PTY `ProcessManager` 与 Unix PTY 使用同一 sandbox policy。
- workspace 内读写，必要的 host runtime 只读/执行路径，workspace 外任意写入默认拒绝。
- IPv4/IPv6 网络 socket 默认拒绝。
- Landlock/filesystem + seccomp-BPF/network 的 fail-closed capability probe。
- workspace escape、symlink escape、network denial、primitive unavailable、cancel/timeout/process-tree、PTY/non-PTY parity 测试。
- Windows 现有行为与 API 不变的回归验证。

**Out of Scope**
- Windows sandbox。
- Hooks / policy-hooks。
- worktree、snapshot、rollback。
- 云端 authority、OAuth、MCP wire 协议。
- UI、installer、package/release pipeline。
- 提供可配置网络 allowlist。
- 容器 runtime、root privilege、setuid helper、bubblewrap 外部依赖。

---

## 需求列表

### FR-1: 保持授权顺序并在 child 创建前强制 sandbox

**优先级:** Must  
**用户故事:** 作为本地执行系统，我希望 sandbox 只作用于已经通过 LocalAdmission/ExecPolicy 的命令，以便隔离层不会成为新的权限来源。

#### 验收标准（EARS）

1. WHEN 本地请求未通过现有 admission/policy THEN 系统 SHALL 保持原有拒绝行为，并且不会调用 sandbox spawn。
2. WHEN 已获准 non-PTY 或 PTY 命令准备创建 child THEN 系统 SHALL 在 child 执行用户程序之前安装 Ubuntu sandbox。
3. IF sandbox preparation 或 child-side install 失败 THEN 系统 SHALL 返回明确 sandbox/spawn failure，且 SHALL NOT unsandboxed fallback。

### FR-2: 限制文件系统到批准 workspace

**优先级:** Must  
**用户故事:** 作为 workspace owner，我希望获准命令只能修改批准 workspace，以便模型/工具不能通过路径、symlink 或绝对路径逃逸到宿主其他目录。

#### 验收标准（EARS）

1. WHEN child 访问 canonical workspace 内文件 THEN 系统 SHALL 按正常 Unix 权限继续允许读写。
2. WHEN child 尝试写入、创建、删除或重命名 workspace 外路径 THEN 系统 SHALL 由 kernel sandbox 拒绝。
3. WHEN workspace 内 symlink 指向 workspace 外对象 THEN child 对该外部对象的受限访问 SHALL 被拒绝。
4. WHEN child 启动所需可执行文件/动态链接器/共享库位于受信 host runtime root THEN 系统 SHALL 只授予最小 read/execute 权限，不授予 host write 权限。

### FR-3: 默认拒绝 IPv4/IPv6 网络能力

**优先级:** Must  
**用户故事:** 作为本地系统 owner，我希望一般 exec/PTTY child 默认无法访问网络，以便本地命令授权不隐式获得出站/监听能力。

#### 验收标准（EARS）

1. WHEN sandboxed child 调用 `socket(AF_INET,...)` 或 `socket(AF_INET6,...)` THEN 系统 SHALL 返回 kernel-level denial。
2. WHILE network capability 默认关闭 THEN child SHALL NOT 通过 TCP/UDP 新建 IPv4/IPv6 socket。
3. IF seccomp filter 无法安装或目标 arch 不受本实现支持 THEN 系统 SHALL fail-closed，不执行 child payload。
4. Unix domain socket 行为不在本增量中扩大权限；已有 stdin/stdout/PTY fd 仍可使用。

### FR-4: PTY 与 non-PTY 共享隔离语义

**优先级:** Must  
**用户故事:** 作为 runtime maintainer，我希望 PTY 与普通 exec 使用同一 sandbox policy，以避免交互式路径成为绕过通道。

#### 验收标准（EARS）

1. WHEN 同一 approved workspace/command 通过 `ProcessManager` 或 `PtyManager` 启动 THEN 两条路径 SHALL 安装等价 filesystem/network 限制。
2. WHEN PTY child 被 cancel/close/timeout THEN 现有 process-tree cleanup SHALL 保持有效。
3. WHEN non-PTY child output 超限或 timeout THEN 现有 bounded I/O 与 termination classification SHALL 保持不变。

### FR-5: Sandbox 能力检测必须 fail-closed

**优先级:** Must  
**用户故事:** 作为部署者，我希望不支持 required kernel isolation 的 Ubuntu host 明确拒绝执行，以便不会出现“看似 sandbox 实际裸跑”。

#### 验收标准（EARS）

1. WHEN Landlock required filesystem rights不能 fully enforce THEN sandbox preparation SHALL 返回 unsupported/error。
2. WHEN seccomp filter 安装不可用 THEN child SHALL NOT exec 用户 payload。
3. WHEN Windows 构建/运行现有 local-agent THEN 本增量 SHALL 不启用 Linux sandbox，也 SHALL 不改变 Windows process/PTTY semantics。

### FR-6: 对外状态与错误保持最小、可审计

**优先级:** Should  
**用户故事:** 作为上层工具，我希望区分 invalid spec、sandbox unavailable 和 spawn failure，同时不泄露 host 路径/secret。

#### 验收标准（EARS）

1. WHEN sandbox 准备或安装失败 THEN 返回的 public error SHALL 使用稳定类别，不包含绝对 host path、command argv、env 或 secret。
2. Debug 输出 SHALL 仅包含 sandbox capability/state 摘要，不输出 workspace 绝对路径。

---

## 非功能需求

- **NFR-1（安全）**: Ubuntu sandbox 必须同时提供 filesystem enforcement 与 IPv4/IPv6 network denial；任一 required primitive 不完整即 fail-closed。
- **NFR-2（兼容性）**: Windows 2025 现有 process/PTTY 测试必须保持通过，Windows production source 不引入行为变化。
- **NFR-3（性能）**: sandbox parent-side preparation 仅在 spawn 前执行；child-side install 为有界 syscall 序列，不引入轮询、sleep 或网络探测。
- **NFR-4（可维护性）**: 新增 sandbox 实现使用英文文件名；每个新增 Rust 源文件 <500 行；`process.rs` 当前已 741 行，不继续塞入 sandbox 实现。
- **NFR-5（可验证性）**: Ubuntu 24.04 CI 必须验证 workspace escape、symlink escape、network denial、primitive unavailable、cancel/timeout/process-tree、PTY/non-PTY；staged GitNexus detect 不得 false-clean。

---

## 依赖关系

- 已验证：`exec-policy`、`exec-unification`、`native-pty`。
- 代码依赖：`services/local-agent/src/registry.rs`、`process.rs`、`process_tree.rs`、`pty.rs`、`pty_unix.rs`。
- Linux primitive：Landlock 用于 filesystem；seccomp-BPF 用于 AF_INET/AF_INET6 socket 默认拒绝。
- 后续依赖：`policy-hooks` 与 `reproducible-packages` 不能把本 Issue 的 library/runner 结果当作 physical-host PASS。

## 检查清单

- [x] 已消化当前仓库既有 admission、process-tree、PTY 约束
- [x] 需求覆盖核心与边界场景
- [x] 每条需求有稳定 ID
- [x] 验收标准可自动化测试
- [x] 范围边界明确
- [x] 安全与兼容性要求量化
- [x] 依赖关系明确

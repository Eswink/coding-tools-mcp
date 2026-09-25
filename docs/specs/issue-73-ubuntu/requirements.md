# 需求文档：issue-73-ubuntu

## 功能概述

为已通过本地 `LocalAdmission` 与 `ExecPolicy` 的命令增加 Ubuntu-only 执行沙箱。沙箱位于策略批准之后、child exec 之前，默认限制 workspace 外的文件系统写入并禁止新建网络 socket；Linux 隔离原语不可用时必须 fail-closed。现有 Windows 执行语义、PTY/非 PTY I/O、取消与进程树清理保持不变。

## 历史经验与坑

- **可复用经验**: 现有 `process_tree` 只负责生命周期 containment，不能冒充安全沙箱；`VerifiedInvocation` 是不可由安全外部代码伪造的本地授权证明。
- **必须规避的坑**: 不在 `pre_exec` 中构造复杂 Rust 对象或做可能分配的工作；不依赖未打包的外部 `bwrap`；不因 Landlock/seccomp 不可用而降级到 unsandboxed execution；不改变 Windows 行为。

## 术语定义

- **Workspace write confinement**: 系统文件仍可只读访问以支持动态加载与宿主 executable，但写入、创建、删除、rename、truncate 只允许发生在 canonical workspace 内。
- **Network capability**: 仅当不可伪造的本地 `VerifiedInvocation` 对应 admission 包含 `Capability::Network` 时允许 child 创建新 socket；默认拒绝。
- **Sandbox preparation**: 在父进程中创建 Landlock ruleset fd 与 seccomp BPF；child `pre_exec` 只调用预先确定的原始 syscall 安装限制。

---

## 范围边界

**In Scope**
- Ubuntu/Linux 普通 process execution 的 workspace-write sandbox。
- Ubuntu/Linux PTY execution 的同一 sandbox。
- 默认 network deny 与 capability-gated network allow。
- Landlock ABI 与 seccomp 可用性检测和 fail-closed 分类。
- workspace escape、symlink escape、network denial、network allow、cancel/process-tree、PTY/non-PTY、Windows no-change 回归测试。

**Out of Scope**
- Windows sandbox。
- 文件系统读隔离或完整 rootfs virtualization。
- Hooks、worktrees、snapshots、云端授权、UI、安装包。
- 改变 `LocalAdmission` / `ExecPolicy` 决策语义。
- 外部 sandbox daemon 或必须预装的 bubblewrap。

---

## 需求列表

### FR-1: Ubuntu workspace 外写入必须被内核沙箱拒绝

**优先级:** Must  
**用户故事:** 作为本地执行 runtime，我要在 command 已获批准后限制其写作用域，以便模型/命令不能修改 workspace 外宿主文件。

#### 验收标准

1. WHEN Ubuntu child 在 approved workspace 内创建、修改、删除文件 THEN 系统 SHALL 允许该操作。
2. WHEN child 直接写 workspace 外路径 THEN 系统 SHALL 由内核隔离拒绝，而不是由命令约定自律。
3. WHEN workspace 内 symlink 指向 workspace 外目标且 child 通过该 symlink 写入 THEN 系统 SHALL 拒绝写入。
4. IF Landlock ABI 小于所需版本或 ruleset 无法 fully install THEN 系统 SHALL 在 exec 前返回显式 Sandbox failure，且不得启动 unsandboxed child。

### FR-2: 无 Network capability 时禁止新网络 socket

**优先级:** Must  
**用户故事:** 作为本地授权层，我要让网络能力与本地 admission 绑定，以便通过 ProcessExec 不会自动获得网络权限。

#### 验收标准

1. WHEN verified invocation 不含 `Capability::Network` THEN child SHALL 不能创建新 `socket` 或 `socketpair`。
2. WHEN verified invocation 含 `Capability::Network` THEN network syscall filter SHALL 不阻断该 child；文件系统 write confinement 仍生效。
3. IF seccomp filter 无法安装 THEN execution SHALL fail closed before target exec。

### FR-3: 普通 exec 与 PTY 使用同一 Ubuntu sandbox contract

**优先级:** Must  
**用户故事:** 作为 runtime，我要让 PTY 与非 PTY 具有一致隔离，以免交互终端绕过安全边界。

#### 验收标准

1. WHEN `ProcessManager` 启动 child THEN sandbox SHALL 在 child exec 前安装。
2. WHEN `PtyManager` 启动 child THEN 同一 sandbox policy SHALL 在 setsid/stdio 设置完成后、target exec 前安装。
3. WHILE sandbox 生效，现有 bounded I/O、timeout、cancel 与 process-tree cleanup SHALL 保持通过。

### FR-4: Windows 行为保持不变

**优先级:** Must  
**用户故事:** 作为 Windows 用户，我不要 Ubuntu sandbox 增量改变现有 ConPTY/Process 行为。

#### 验收标准

1. WHEN Windows 构建与测试运行 THEN 不编译或调用 Linux Landlock/seccomp implementation。
2. WHEN现有 Windows process/PTY tests 运行 THEN 行为与当前 verified native-PTY baseline 一致。

---

## 非功能需求

- **NFR-1（安全）**: sandbox 安装失败必须显式 fail-closed；不得记录 argv/env/host path 内容到 Debug 错误。
- **NFR-2（兼容性）**: Ubuntu 24.04 runner 上要求 Landlock ABI >= 3 与 seccomp filter 可用；已验证 runner 为 kernel 6.17 / Landlock ABI 7。
- **NFR-3（可维护性）**: Linux sandbox 实现独立英文文件，单文件 <500 行；Windows 文件不改或仅有 compile-only facade wiring。
- **NFR-4（可审计性）**: production symbol 编辑前有 pinned GitNexus impact；提交前 staged detect 必须非 false-clean。

## 依赖关系

- 已 verified：`exec-policy`、`exec-unification`、`native-pty`。
- Linux 原语：Landlock syscall、`PR_SET_NO_NEW_PRIVS`、seccomp BPF。
- 现有 `libc` Unix dependency 可复用；第一增量不要求外部可执行文件。

## 检查清单

- [x] 历史边界与 process-tree 非 sandbox 事实已纳入
- [x] 每条 FR 有稳定 ID
- [x] EARS-style acceptance 可自动验证
- [x] In/Out Scope 明确
- [x] 不把 physical host / real ChatGPT 写成 PASS

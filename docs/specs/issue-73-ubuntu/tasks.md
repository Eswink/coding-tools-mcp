# 任务清单：issue-73-ubuntu

## 概述

实现 Ubuntu-only fail-closed sandbox。所有 production 编辑必须先完成对应 GitNexus impact；HIGH/CRITICAL 需先停下评审。实现不得扩展到 Windows sandbox、Hooks、worktree/snapshot、UI 或 packaging。

---

## 交付物清单（Scope-lock）

- **预计新建文件数**: 3 个（`sandbox.rs`, `sandbox_linux.rs`, `sandbox_runtime.rs`）
- **预计修改文件数**: 7 个以内（`lib.rs`, `registry.rs`, `process.rs`, `process_tree.rs`, `pty.rs`, `pty_unix.rs`, 必要时 fixture）
- **预计新增/修改函数数**: 约 12-18 个
- **交付物逐项列举**:
  1. Linux sandbox facade 与 bounded error surface。
  2. parent-prepared Landlock write ruleset。
  3. parent-prepared seccomp network deny filter。
  4. ProcessManager sandbox wiring。
  5. PtyManager sandbox wiring。
  6. VerifiedInvocation-gated Network grant seam。
  7. Ubuntu workspace/symlink/network/process-tree regression。
  8. Windows no-change regression evidence。

---

## 阶段 1: 准备工作

- [ ] 1.1 固化 primitive 与影响面证据，禁止在未知风险符号上编辑
  - **证据块**: run `36160607897`: Ubuntu kernel 6.17, Landlock ABI 7, seccomp ERRNO available；GitNexus `process_tree::spawn` LOW/lower-bound，`pty_unix::spawn` lower-bound。
  - **涉及文件**: 不改 production；保存 impact/primitive evidence。
  - _需求: FR-1, FR-2, NFR-4_ ｜ _设计: 技术选型_

- [ ] 1.2 对每个计划修改符号执行 fresh GitNexus context/impact
  - **证据块**: 必须覆盖 `ProcessManager::start`, `ExecSpec`, `PtyManager::start`, `PtySpec`, `VerifiedInvocation`, Unix spawn seams。
  - **涉及文件**: 只读；HIGH/CRITICAL 时暂停对应 production edit。
  - _需求: FR-1..4_ ｜ _设计: 架构设计_

---

## 阶段 2: 核心实现

- [ ] 2.1 新增 parent-prepared Linux sandbox primitive，缺失时 fail-closed
  - **证据块**: 当前 `process_tree.rs` 注释明确“lifecycle containment, not a security sandbox”；现有 Unix dependency 已含 `libc`。
  - **涉及文件**: 新建 `src/sandbox.rs` <180 行，`src/sandbox_linux.rs` <500 行；修改 `src/lib.rs` <30 行。
  - _需求: FR-1, FR-2, NFR-1..3_ ｜ _设计: Landlock/seccomp_

- [ ] 2.2 将默认 Linux sandbox 注入普通 process spawn
  - **证据块**: `ProcessManager::start` canonicalize cwd 后构造 Command，随后进入 `process_tree::spawn`。
  - **涉及文件**: `src/process.rs` <100 行，`src/process_tree.rs` <80 行。
  - _需求: FR-1, FR-2, FR-3_ ｜ _设计: child 安装_

- [ ] 2.3 将同一 sandbox 注入 PTY spawn 且保持 TTY 初始化
  - **证据块**: `pty_unix.rs::spawn` 已在单个 `pre_exec` closure 中执行 setsid/TIOCSCTTY/dup2。
  - **涉及文件**: `src/pty.rs` <90 行，`src/pty_unix.rs` <80 行。
  - _需求: FR-2, FR-3, FR-4_ ｜ _设计: PTY wiring_

- [ ] 2.4 将 Network 放行绑定到 VerifiedInvocation，而非 public bool
  - **证据块**: `VerifiedInvocation` 无 public constructor/Clone；`LocalAdmission.capabilities` 仅 crate 内可读。
  - **涉及文件**: `src/registry.rs` <40 行，`src/process.rs`/`src/pty.rs` builder 各 <30 行。
  - _需求: FR-2_ ｜ _设计: 权限来源_

---

## 阶段 3: 集成测试

- [ ] 3.1 验证 workspace write、escape、symlink escape 与 setup fail-closed
  - **证据块**: 现有 `process_runtime.rs` 已覆盖 timeout/cancel/output/tree，新增 sandbox contract 不替代这些测试。
  - **涉及文件**: 新建 `tests/sandbox_runtime.rs` <450 行，必要 fixture 增量 <120 行。
  - _需求: FR-1, NFR-1_ ｜ _设计: 测试策略_

- [ ] 3.2 验证 network deny/allow 与 PTY/process 等价
  - **证据块**: `Capability::Network` 已存在；PTY integration tests 已覆盖 terminal/write/resize/cancel/tree。
  - **涉及文件**: `tests/sandbox_runtime.rs`, `tests/pty_runtime.rs` <80 行增量。
  - _需求: FR-2, FR-3_ ｜ _设计: 测试策略_

- [ ] 3.3 运行 Ubuntu/Windows full regression 与 staged detect
  - **证据块**: Ubuntu exact sandbox tests + local-agent full suite；Windows 2025 完整 local-agent no-change；GitNexus detect 非 false-clean。
  - **涉及文件**: never-merge CI helper only。
  - _需求: FR-1..4, NFR-4_ ｜ _设计: 测试策略_

---

## 检查点

- [ ] 阶段 1 完成后：所有 production 目标符号有 fresh impact，HIGH/CRITICAL 已停审。
- [ ] 阶段 2 完成后：Linux 缺原语无法启动 unsandboxed child；Windows 代码路径无行为变化。
- [ ] 阶段 3 完成后：workspace escape/symlink/network/cancel/process-tree/PTY/Windows 回归全部通过。

---

## 需求覆盖矩阵

| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | Landlock write confinement | 1.1, 1.2, 2.1, 2.2, 3.1 | 未开始 |
| FR-2 | seccomp + VerifiedInvocation | 1.1, 2.1, 2.4, 3.2 | 未开始 |
| FR-3 | process/PTY shared contract | 2.2, 2.3, 3.2 | 未开始 |
| FR-4 | Windows no-change | 2.3, 3.3 | 未开始 |

---

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---:|---|
| services/local-agent/src/sandbox.rs | 新建 | <180 | cfg facade / bounded error |
| services/local-agent/src/sandbox_linux.rs | 新建 | <500 | raw Landlock/seccomp |
| services/local-agent/src/process.rs | 修改 | <100 | prepare/wiring/network grant |
| services/local-agent/src/process_tree.rs | 修改 | <80 | child install |
| services/local-agent/src/pty.rs | 修改 | <90 | sandbox policy |
| services/local-agent/src/pty_unix.rs | 修改 | <80 | child install |
| services/local-agent/src/registry.rs | 修改 | <40 | capability query |
| services/local-agent/src/lib.rs | 修改 | <30 | stable exports |
| services/local-agent/tests/sandbox_runtime.rs | 新建 | <450 | sandbox integration contracts |
| services/local-agent/tests/pty_runtime.rs | 修改 | <80 | PTY equivalence |

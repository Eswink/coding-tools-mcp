# Issue #59 — Native PTY design

## 概述

现有 local Agent 已有普通 pipe execution 与 race-free process-tree ownership，但没有 PTY/ConPTY。
本设计添加内部 PTY session layer，同时保持既有授权和 process ownership 语义。

关键约束：
- Windows 不能使用先 spawn 再 attach Job Object 的 wrapper。
- Linux 必须是 controlling-terminal PTY。
- 不新增公开 Tool。
- 不自动替换现有 ProcessManager。
- 新 PTY module 使用英文文件名且每个文件小于 500 行。

## 技术方案

### Common model: src/pty.rs

定义 PtySize、PtySpec、PtyError、PtyTermination、PtyOutcome、PtyManager、PtySession。

职责：
- request bounds；
- capacity semaphore；
- opaque session ID；
- timeout/cancel/drop supervisor；
- bounded output accounting；
- platform backend facade；
- non-secret Debug。

### IO: src/pty_io.rs

负责：
- bounded master reader；
- single-owner interactive writer；
- output overflow signal；
- bounded reader/writer shutdown；
- merged terminal byte stream。

### Linux backend: src/pty_unix.rs

流程：
1. allocate PTY；
2. set winsize；
3. parent 构造 explicit argv/cwd/env；
4. pre-exec 中 setsid + controlling terminal；
5. child 成为 session/PG leader；
6. parent 关闭 slave；
7. master 交给 common IO；
8. TIOCSWINSZ resize；
9. 终止复用 negative-PGID process-tree semantics。

### Windows backend: src/pty_windows.rs

流程：
1. create anonymous pipes；
2. CreatePseudoConsole；
3. STARTUPINFOEXW attribute list；
4. create kill-on-close Job Object；
5. bounded UTF-16 argv/env/cwd；
6. CreateProcessW suspended；
7. AssignProcessToJobObject(exact hProcess)；
8. ResumeThread(exact hThread)；
9. 返回 owned process/PTY/pipe handles；
10. ResizePseudoConsole。

任何 resume 前失败都 terminate/close，不允许 unmanaged child 执行。

### Minimal process-tree seams

process_tree.rs：
- 仅增加 already-established Unix process group 的内部 ownership/termination seam。

process_tree_windows.rs：
- 仅增加 create unassigned kill-on-close Job Object 与 attach/resume exact suspended process/thread 的内部 seam。

现有普通 spawn(Command) 行为不变。

### Fixture

src/bin/pty_fixture.rs 支持 bounded modes：
- report terminal presence；
- echo bytes/Unicode；
- report size；
- spawn grandchild；
- sleep；
- flood；
- explicit exit。

### Supervisor

1. acquire capacity；
2. platform spawn；
3. start bounded reader；
4. select child completion / timeout / cancel / overflow；
5. forced termination 时 terminate owned tree；
6. bounded wait 确认 child exit；
7. close PTY handles；
8. join bounded reader；
9. publish outcome；
10. release capacity。

## 文件结构

### 新增
- services/local-agent/src/pty.rs
- services/local-agent/src/pty_io.rs
- services/local-agent/src/pty_unix.rs
- services/local-agent/src/pty_windows.rs
- services/local-agent/src/bin/pty_fixture.rs
- services/local-agent/tests/pty_runtime.rs

### 最小修改
- services/local-agent/src/lib.rs
- services/local-agent/src/process_tree.rs
- services/local-agent/src/process_tree_windows.rs
- services/local-agent/Cargo.toml
- services/local-agent/Cargo.lock，仅在 feature resolution 需要时

### 明确不修改
- ToolRegistry public catalog
- cloud gateway
- auth/origin
- sandbox
- worktree/snapshot
- Hooks
- UI
- installer/package
- legacy process.rs，除非 fresh impact 证明无法避免并重新 review

## 数据与错误模型

PTY outcome 包含 retained bytes、total bytes、truncated、output_complete、exit code 和 termination cause。
Termination cause 只使用 exited、timed-out、cancelled、output-limit、io-error、termination-uncertain 等稳定非敏感类别。
Resize-after-terminal 返回稳定 closed-session error。

## Windows argv / env

使用 private bounded Windows argv quoting helper，覆盖 spaces、quotes、trailing backslashes。
使用 explicit Unicode environment block，不继承 ambient env。
Application path 单独传给 CreateProcessW，不构造 shell command string。

## Linux pre-exec

pre-exec 只做 syscall-level async-signal-safe setup；复杂参数、路径、env 在 parent 预先构造。

## 兼容性与回滚

Existing ProcessManager、ExecSpec、ToolRegistry、exec-policy contract 保持不变。
PTY 不自动用于现有 command。
不持久化 PTY session，不支持 restart replay。
Functional commit 必须可单独 revert：移除 PTY modules/fixture/tests、Cargo feature 和小型 process-tree seams 后，ordinary pipe execution 仍工作。

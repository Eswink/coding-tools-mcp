# Issue #59 — Native PTY requirements

## 功能概述

本增量为 local Agent 增加第一个内部 native PTY execution primitive：

- Windows 使用 Windows Pseudo Console（ConPTY）。
- Ubuntu/Linux 使用真实 Unix PTY。
- 不新增公开 MCP Tool，不扩大 local authority、exec-policy、admission 或 no-replay 权限。
- 不包含 sandbox、Hooks、worktree、snapshot、UI、packaging。
- 新增或修改源码文件必须使用英文文件名并满足仓库源码长度限制。

## 需求列表

### FR-1 原生 PTY
WHEN 平台为 Windows，THE SYSTEM SHALL 使用 ConPTY，而不是普通 pipe 模拟终端。
WHEN 平台为 Ubuntu/Linux，THE SYSTEM SHALL 使用真实 PTY 和 controlling-terminal/session 语义。

### FR-2 先归属后执行
WHEN Windows 创建 PTY child，THE SYSTEM SHALL 使用 CREATE_SUSPENDED，并在 child 代码执行前完成 kill-on-close Job Object 归属，再 resume exact primary thread。
WHEN Linux 创建 PTY child，THE SYSTEM SHALL 在 exec 前建立 owned session/process group，使取消和清理仍使用现有 negative-PGID tree semantics。

### FR-3 有界请求
WHEN 请求进入 PTY manager 且尚未 spawn，THE SYSTEM SHALL fail-closed 校验：
- executable 是 absolute path；
- cwd 已存在并 canonical；
- argv 数量 <= 128；
- 单 token <= 4 KiB，argv 总计 <= 64 KiB；
- env <= 64 项，单值 <= 16 KiB，总计 <= 64 KiB；
- 不继承 ambient environment；
- timeout > 0 且 <= 1 hour；
- retained output > 0 且 <= 1 MiB；
- rows/columns 非零且 <= 1000；
- 单次 interactive write <= 64 KiB。

### FR-4 会话 API
WHEN PTY session 成功创建，THE SYSTEM SHALL 提供 opaque session ID、write、resize、output snapshot、total bytes、wait、cancel/close、status、exit code、duration、truncated、output_complete 和 termination cause。
WHEN PTY output 被读取，THE SYSTEM SHALL 按单一 terminal byte stream 表达，不虚构 stdout/stderr 分离。

### FR-5 Windows ConPTY 生命周期
WHEN Windows backend 启动，THE SYSTEM SHALL：
1. 创建 ConPTY input/output pipes；
2. CreatePseudoConsole；
3. 构造 STARTUPINFOEXW + PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE；
4. CreateProcessW 使用 EXTENDED_STARTUPINFO_PRESENT、CREATE_UNICODE_ENVIRONMENT、CREATE_SUSPENDED；
5. 在 resume 前 AssignProcessToJobObject(exact process handle)；
6. ResumeThread(exact primary thread)；
7. ResizePseudoConsole 支持 resize；
8. 部分失败时确定性关闭 process/thread/Job/HPCON/pipes。

### FR-6 Ubuntu/Linux PTY 生命周期
WHEN Linux backend 启动，THE SYSTEM SHALL：
1. allocate PTY master/slave；
2. exec 前设置 initial winsize；
3. pre-exec 只执行 audited syscall-level setsid / controlling-terminal setup；
4. 显式设置 argv/cwd/env；
5. parent spawn 后关闭 slave copies；
6. child session/process-group 成为 owned tree identity；
7. TIOCSWINSZ 支持 resize。

### FR-7 终止与自然退出
WHEN timeout、cancel、close、output overflow 或 session drop 发生，THE SYSTEM SHALL 终止完整 owned process tree，并在发布 terminal outcome 前确认 child 结束。
WHEN parent 自然退出但 descendants 可能仍存活，THE SYSTEM SHALL 执行 owned-tree cleanup，保持现有 non-detach 行为。

### FR-8 输出与容量
WHEN total PTY output 超过 retained limit，THE SYSTEM SHALL 终止 session、最多保留配置字节数，并报告真实 total bytes 与 truncated=true。
WHEN capacity 已耗尽，THE SYSTEM SHALL 在 spawn 前拒绝且不产生 child。

### FR-9 双平台验收
WHEN candidate 进入 VERIFY，THE SYSTEM SHALL 在 Windows Server 2025 与 Ubuntu 24.04 验证 terminal presence、Unicode/byte echo、resize、timeout、cancel/close、output overflow、capacity、drop cleanup、grandchild cleanup、Windows argv quoting 与 Debug redaction。

## 非功能需求

### NFR-1 权限边界
PTY API SHALL 保持 library-internal，不注册公开 Tool，不绕过 local grant、exec-policy、admission 或 no-replay。

### NFR-2 资源所有权
Process/thread/Job/HPCON/pipe/fd SHALL 使用 RAII 或等价单一所有权；部分启动失败不得残留 unmanaged child。

### NFR-3 不泄密
Debug/error SHALL 不包含 raw argv、environment value、workspace absolute path 或 terminal input/output。

### NFR-4 源码规模
本 Issue 新增或修改的 Rust source SHALL 在 rustfmt 后小于 500 行；不得扩张现有 oversized legacy process.rs。

### NFR-5 影响门禁
任何 existing production symbol 编辑前 SHALL 有 pinned GitNexus context/impact；HIGH/CRITICAL 必须先告警并停止 production edit。
提交前 SHALL 运行 staged detect_changes 且不得 false-clean。

### NFR-6 发布纪律
发布前 SHALL fresh-read remote feature ref，只允许 fast-forward/no-force-push。
Runner tests SHALL NOT 被写成 physical installed-host 或 real ChatGPT PASS。

## 依赖关系

- Manifest dependency exec-unification 已 verified。
- 复用 services/local-agent/src/process_tree.rs。
- 复用 services/local-agent/src/process_tree_windows.rs。
- 保持 services/local-agent/src/process.rs 现有行为，不在本 Issue 扩张该超长文件。
- Windows 继续使用现有 windows 0.61 crate，仅增加 ConPTY/pipe/startup attribute 所需 feature。
- Unix 继续使用现有 libc，不引入第二个 PTY wrapper。
- 不依赖 sandbox、Hooks、worktrees、snapshot rollback、cloud authority、UI 或 packaging。

## 验收标准

1. WHEN Windows 2025 执行 fixture，THE SYSTEM SHALL 证明真实 ConPTY、Unicode input/output、resize、cancel 与完整 tree cleanup。
2. WHEN Ubuntu 24.04 执行 fixture，THE SYSTEM SHALL 证明 controlling-terminal PTY、Unicode、resize、cancel 与完整 tree cleanup。
3. WHEN capacity/timeout/output-limit/drop 边界触发，THE SYSTEM SHALL fail closed 且无 detached descendant。
4. WHEN Windows child 开始执行，THE SYSTEM SHALL 已完成 Job Object ownership。
5. WHEN candidate 验证，THE SYSTEM SHALL 通过双平台 focused tests、complete local-Agent tests、candidate Clippy、check 与 staged GitNexus detect。
6. WHEN 交付完成，THE SYSTEM SHALL 记录 exact SHA-256、CI artifacts 与 rollback；installed-host/real-ChatGPT gate 继续 deferred。

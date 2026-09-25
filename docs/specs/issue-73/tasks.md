# 任务清单：issue-73

## 概述

实现 Ubuntu-only local execution sandbox。所有 production 实现必须等 `check_spec` 通过后才能开始；每个 production symbol 编辑前执行 pinned GitNexus upstream impact，HIGH/CRITICAL 先 review。

## 交付物清单（Scope-lock）

- **预计新建文件数**: 3 个 production/test 文件（`sandbox.rs`, `sandbox_linux.rs`, `sandbox_runtime.rs`）；如 PTY 测试超过 500 行可新增 `sandbox_pty.rs`
- **预计修改文件数**: 6 个以内（`Cargo.toml`, `lib.rs`, `process.rs`, `process_tree.rs`, `pty.rs`, `pty_unix.rs` 中仅实际需要者）
- **预计新增/修改函数数**: 约 12–18 个，拆分到独立 sandbox 模块
- **交付物逐项列举**:
  1. `services/local-agent/src/sandbox.rs` — policy/error/prepared interface
  2. `services/local-agent/src/sandbox_linux.rs` — Landlock/seccomp Linux implementation
  3. `services/local-agent/tests/sandbox_runtime.rs` — Ubuntu integration regression
  4. 必要的 spawn plumbing in process/process_tree/PTTY
  5. Linux-target dependency entries in `services/local-agent/Cargo.toml`
  6. Windows/Ubuntu CI evidence、GitNexus detect、hash/rollback receipts

---

## 任务列表

### 阶段 1: 规格与影响面

- [ ] 1.1 校验 sandbox 规格并完成 pre-edit impact gate
  - **证据块**:
    - `services/local-agent/src/registry.rs:172` — `ToolRegistry::invoke` 是本地 admission 入口。
    - `services/local-agent/src/registry.rs:211` — 仅 admission 通过后构造 `VerifiedInvocation`。
    - `services/local-agent/src/executor.rs:9` — 现有注释明确 authorization/sandbox orchestration 在 executor 外部。
    - `services/local-agent/src/process.rs:381` — non-PTY `ProcessManager::start` child 启动入口。
    - `services/local-agent/src/pty_unix.rs:26` — Unix PTY 独立 spawn 入口。
  - **涉及文件**: specs + GitNexus evidence；不改 production
  - _需求: FR-1, FR-4, FR-5_ ｜ _设计: 技术方案 / 设计决策 2_

### 阶段 2: 核心实现

- [ ] 2.1 新增 Linux sandbox policy/preparation，filesystem 与 network primitive 都 fail-closed
  - **证据块**:
    - `services/local-agent/Cargo.toml:24` — 当前 Unix target dependency 只有 `libc`，新增依赖可保持 Linux-target scoped。
    - `services/local-agent/src/process_tree.rs:1` — 文件明确声明 lifecycle containment 不是 security sandbox。
    - `services/local-agent/src/process_tree.rs:44` — 统一 non-PTY Unix child spawn seam。
  - **涉及文件**:
    - 新建 `src/sandbox.rs` <350 行
    - 新建 `src/sandbox_linux.rs` <450 行
    - 修改 `Cargo.toml` <15 行
    - 修改 `src/lib.rs` <10 行
  - _需求: FR-2, FR-3, FR-5, FR-6_ ｜ _设计: 决策 1, 3, 4_

- [ ] 2.2 将 prepared sandbox 接入 non-PTY spawn，同时保持 process-tree/I/O/timeout 契约
  - **证据块**:
    - `services/local-agent/src/process.rs:381` — `start` canonicalize cwd 后才创建 Command。
    - `services/local-agent/src/process.rs:407` — 当前唯一 non-PTY `process_tree::spawn` 调用点。
    - `services/local-agent/src/process_tree.rs:48` — Unix 已在 spawn 前配置 process group。
  - **涉及文件**:
    - `src/process.rs`：只加 policy preparation/plumbing，新增 <35 行；文件已 741 行，禁止加入 sandbox 实现
    - `src/process_tree.rs`：新增/调整 spawn seam <60 行
  - _需求: FR-1, FR-2, FR-3, FR-5_ ｜ _设计: Parent prepare / child install_

- [ ] 2.3 将同一 sandbox 接入 Unix PTY，不改变 Windows PTY
  - **证据块**:
    - `services/local-agent/src/pty.rs:337` — PTY manager start 入口。
    - `services/local-agent/src/pty_unix.rs:26` — Unix PTY platform spawn。
    - `services/local-agent/src/pty_unix.rs:46` — 当前 child `pre_exec` 已做 setsid/TIOCSCTTY/dup2，是安装 prepared sandbox 的受控位置。
  - **涉及文件**:
    - `src/pty.rs` <35 行
    - `src/pty_unix.rs` <45 行
    - Windows files 0 行
  - _需求: FR-4, FR-5_ ｜ _设计: 决策 2, 5_

### 阶段 3: 集成测试与验收

- [ ] 3.1 增加 Ubuntu sandbox 正/负行为与 fail-closed 测试
  - **证据块**:
    - `services/local-agent/tests/process_runtime.rs` 已覆盖 stdout/stderr、env、timeout、cancel、grandchild cleanup、output bound 和 active limit，可复用 fixture/process semantics。
    - 当前 sandbox 搜索无现成 Landlock/seccomp 实现，因此新测试必须证明新隔离边界，而不是把现有 process-tree 当 sandbox。
  - **涉及文件**:
    - 新建 `tests/sandbox_runtime.rs` <450 行
    - 如 PTY 场景使单文件超限，拆分 `tests/sandbox_pty.rs` <300 行
  - **验收点**:
    - workspace write pass
    - outside write denied
    - symlink escape denied
    - IPv4/IPv6 TCP/UDP socket creation denied
    - primitive unavailable fail-closed
    - cancel/timeout/grandchild cleanup pass
    - PTY/non-PTY restrictions一致
  - _需求: FR-2, FR-3, FR-4, FR-5, FR-6_ ｜ _设计: 测试策略_

- [ ] 3.2 执行双平台 regression、GitNexus detect、code review 与 Plan converge
  - **证据块**:
    - 现有 #59 PTY/ProcessManager 已有 Windows 2025 + Ubuntu 24.04 evidence；本增量必须证明 Windows no-change。
  - **涉及文件**: helper workflows/evidence only；所有 `ci/*` never-merge
  - **验收点**:
    - Ubuntu focused sandbox + full local-agent tests
    - Windows existing process + PTY full suite
    - fmt/clippy/check
    - staged detect non-false-clean
    - code_review 无 HIGH/CRITICAL 未解决项
    - Plan converge passed
  - _需求: NFR-2, NFR-5_ ｜ _设计: Review gates_

---

## 检查点

- [ ] 阶段 1 完成后：`check_spec` passed；所有拟编辑 production symbol 有 fresh GitNexus impact。
- [ ] 阶段 2 完成后：candidate 只包含 scope-lock 文件；Linux primitive unavailable 时没有 unsandboxed fallback。
- [ ] 阶段 3 完成后：Ubuntu/Windows 双平台 evidence、code review、converge、source hashes、rollback 全部记录。

---

## 需求覆盖矩阵

| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 架构设计 / 决策 2 | 1.1, 2.2 | 未开始 |
| FR-2 | 决策 1, 3 | 2.1, 2.2, 3.1 | 未开始 |
| FR-3 | 决策 1 | 2.1, 2.2, 3.1 | 未开始 |
| FR-4 | 决策 2, 5 | 2.3, 3.1 | 未开始 |
| FR-5 | 决策 4, 5 | 2.1, 2.2, 2.3, 3.1 | 未开始 |
| FR-6 | 数据模型 / Review gates | 2.1, 3.1 | 未开始 |
| NFR-1 | 技术选型 | 2.1, 3.1 | 未开始 |
| NFR-2 | 决策 5 | 2.3, 3.2 | 未开始 |
| NFR-3 | 决策 2 | 2.1, 2.2 | 未开始 |
| NFR-4 | 文件结构 | 2.1, 2.2, 2.3 | 未开始 |
| NFR-5 | Review gates | 3.2 | 未开始 |

---

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---:|---|
| `services/local-agent/Cargo.toml` | 修改 | +15 | Linux-target sandbox dependencies |
| `services/local-agent/src/lib.rs` | 修改 | +10 | module/export wiring |
| `services/local-agent/src/sandbox.rs` | 新建 | <350 | shared policy/error/prepared contract |
| `services/local-agent/src/sandbox_linux.rs` | 新建 | <450 | Landlock/seccomp implementation |
| `services/local-agent/src/process.rs` | 修改 | +35 | non-PTY preparation/plumbing only |
| `services/local-agent/src/process_tree.rs` | 修改 | +60 | child install seam only |
| `services/local-agent/src/pty.rs` | 修改 | +35 | PTY policy plumbing |
| `services/local-agent/src/pty_unix.rs` | 修改 | +45 | child install seam |
| `services/local-agent/tests/sandbox_runtime.rs` | 新建 | <450 | Ubuntu isolation regression |
| `services/local-agent/tests/sandbox_pty.rs` | 可选新建 | <300 | only if runtime test file would exceed 500 |

---

## 检查清单

- [x] Scope-lock 已锁定
- [x] 每条任务标题具体
- [x] 每条任务含真实源码证据
- [x] 文件与行数预算明确
- [x] `process.rs` 超 500 行，sandbox 实现明确拆到新模块
- [x] 所有任务回链 FR/design
- [x] 需求覆盖矩阵完整
- [x] 阶段 3 对照验收标准
- [x] 无模板占位符、TODO 或省略号交付项

# 任务清单：issue-70-isolated

## 概述

实现内部 WorktreeManager 核心。Scope-lock 只包含 create/list/clean-remove 生命周期与测试；不实现 snapshot rollback、公共 MCP tool、sandbox、PTY、Hooks、cloud、UI 或 packaging。

## 交付物清单（Scope-lock）

- 预计新建文件数：3
- 预计修改文件数：1
- 预计新增/修改函数数：约 18 个
- 交付物：
  1. src-tauri/src/harness/worktree.rs
  2. src-tauri/src/harness/worktree_git.rs
  3. src-tauri/src/harness/worktree_tests.rs
  4. src-tauri/src/harness/mod.rs

## 任务列表

## 阶段 1: 安全边界与 Git 事实模型

- [ ] 1.1 实现 WorktreeManager 构造与 canonical repository / Harness managed-root 校验
  - 证据块：
    - src-tauri/src/tools/context.rs: ToolContext 同时持有 canonical Workspace 与 Harness，Harness root 与 repository workspace 分离。
    - src-tauri/src/harness/state.rs: Harness::new canonicalize workspace，生成 workspace_id，store_root 返回独立 HarnessStore root。
    - src-tauri/src/tools/workspace.rs: 现有安全边界采用 canonical path / symlink fail-closed。
  - 涉及文件：新建 src-tauri/src/harness/worktree.rs，阶段预算 180 行；修改 harness/mod.rs 预算 4 行。
  - 需求：FR-1, FR-5, NFR-2｜设计：技术方案、决策 1、API 设计

- [ ] 1.2 实现 bounded Git argv runner 与非敏感错误模型
  - 证据块：
    - src-tauri/src/tools/git.rs 现有 Git 工具通过 argv 调 git，但 worktree 生命周期不应继续扩大该只读模块。
    - src-tauri/src/harness/store.rs 使用稳定 code + message 错误风格。
  - 涉及文件：新建 worktree_git.rs，预算 150 行；worktree.rs 仅保留 manager/边界逻辑。
  - 需求：FR-2, FR-3, FR-4, FR-5, NFR-1｜设计：技术选型、决策 3

## 阶段 2: 核心生命周期

- [ ] 2.1 实现 detached worktree create、容量限制与失败清理
  - 证据块：Harness store_root + workspace_id 可固定派生 managed root；manifest safe-patch 已 verified，snapshot-rollback 仍为下游 planned。
  - 涉及文件：worktree.rs，预算 80 行。
  - 需求：FR-2, FR-5｜设计：决策 1、决策 2

- [ ] 2.2 实现 registry-backed bounded list
  - 证据块：Git registry 必须通过 worktree list porcelain -z 读取；目录存在不证明 Git ownership。
  - 涉及文件：worktree.rs，预算 55 行。
  - 需求：FR-3, FR-5｜设计：决策 3

- [ ] 2.3 实现 clean-only remove、dirty refusal 与 NotFound
  - 证据块：safe-patch 已建立不确定状态不执行破坏性动作的 fail-closed 模式；本 Issue 禁止 force remove。
  - 涉及文件：worktree.rs，预算 70 行；bounded Git runner 已按预算拆到 worktree_git.rs，禁止重新内联突破限制。
  - 需求：FR-4, FR-5｜设计：决策 4

## 阶段 3: 集成测试与验收

- [ ] 3.1 增加真实 Git create/list/remove 与跨平台路径测试
  - 证据块：docs/project-context/how-to-test.md 要求 Rust cargo test，路径/进程管理需 Windows 兼容验证。
  - 涉及文件：新建 worktree_tests.rs，预算 260 行。
  - 需求：FR-1, FR-2, FR-3, FR-6｜设计：测试策略

- [ ] 3.2 增加 dirty/escape/symlink/capacity/output-limit/Debug redaction 回归
  - 证据块：Workspace protected/symlink 边界禁止链接逃逸；ToolContext/Harness host path 不应作为公开数据暴露。
  - 涉及文件：worktree_tests.rs 追加预算 160 行，总预算 <500 行。
  - 需求：FR-4, FR-5, FR-6, NFR-1, NFR-2, NFR-3｜设计：测试策略

- [ ] 3.3 对照验收标准执行 GitNexus、focused tests、完整相关 Rust 回归和双平台 CI
  - 证据块：AGENTS.md 要求 pre-edit impact、staged detect 非 false-clean、HIGH/CRITICAL 先 review、真实测试证据后发布。
  - 涉及文件：不新增 production 文件；仅 never-merge CI helper/evidence。
  - 需求：FR-1 至 FR-6｜设计：测试策略、风险评估

## 检查点

- [ ] 阶段 1：非法 workspace、Git 不可用、path escape 均在 mutation 前拒绝；Git output 有界。
- [ ] 阶段 2：create/list/remove 仅作用于 Harness managed root；dirty worktree 无法移除；无 force path。
- [ ] 阶段 3：Windows 2025、Ubuntu 24.04 focused + relevant full regression 通过；staged detect 识别真实候选；文件均 <500 行。

## 需求覆盖矩阵

| 需求 ID | 设计章节 | 任务 | 状态 |
|---|---|---|---|
| FR-1 | 技术方案 / API | 1.1, 3.1 | 未开始 |
| FR-2 | 决策 1 / 决策 2 | 1.2, 2.1, 3.1 | 未开始 |
| FR-3 | 决策 3 | 1.2, 2.2, 3.1 | 未开始 |
| FR-4 | 决策 4 | 1.2, 2.3, 3.2 | 未开始 |
| FR-5 | 安全设计 / 风险评估 | 1.1, 1.2, 2.1, 2.2, 2.3, 3.2 | 未开始 |
| FR-6 | 测试策略 | 3.1, 3.2, 3.3 | 未开始 |

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---:|---|
| src-tauri/src/harness/worktree.rs | 新建 | ≤390 | manager、error、create/list/remove |
| src-tauri/src/harness/worktree_git.rs | 新建 | ≤160 | bounded Git argv runner、timeout、stdout/stderr drain |
| src-tauri/src/harness/worktree_tests.rs | 新建 | ≤430 | 真实 Git 生命周期与安全回归 |
| src-tauri/src/harness/mod.rs | 修改 | +5 | private runner module + manager/type export |

## 检查清单

- [x] 交付物锁定为 3 新建 + 1 修改；runner 拆分由源码 <500 行门禁触发。
- [x] 每条任务含真实证据块。
- [x] 每条任务含路径与行数预算。
- [x] 所有任务回链 FR 与 design。
- [x] FR-1 至 FR-6 全覆盖。
- [x] 阶段 3 明确逐条验收。
- [x] 无模板占位与未决实现标记。

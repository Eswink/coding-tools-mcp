# 任务清单：issue-68-safe-patch

## 概述

实现 #68 的有界事务加固。所有实现限定在 patch transaction 内部，不扩展 worktree/snapshot/sandbox/Hook 能力。

## 交付物清单（Scope-lock）

- **预计新建文件数**: 2 个
- **预计修改文件数**: 1 个
- **预计新增/修改函数数**: 约 8–12 个
- **交付物逐项列举**:
  1. `src-tauri/src/tools/patch_transaction.rs`
  2. `src-tauri/src/tools/patch_transaction_tests.rs`
  3. `src-tauri/src/tools/patch.rs`

---

## 任务列表

### 阶段 1: 固定事务边界

- [ ] 1.1 抽取 patch transaction 模块，保持 parser/policy 和 apply_patch 输出契约不变
  - **证据块**: `src-tauri/src/tools/patch.rs:11` 的 `apply_patch` 负责参数、parser、protected/confirm preflight；`patch.rs:410` 起才进入 `commit_staged`。
  - **涉及文件**: `patch.rs` 预计净减少 80–130 行；`patch_transaction.rs` 预计 180–260 行。
  - _需求: FR-1, FR-3_ ｜ _设计: 架构设计、决策 1_

- [ ] 1.2 将 staged/backups/temporary file 索引改为确定性路径顺序
  - **证据块**: `patch.rs:426` 的 `commit_staged_bytes` 当前接收 `HashMap` 并直接迭代，提交顺序不稳定。
  - **涉及文件**: `patch.rs`、`patch_transaction.rs`。
  - _需求: FR-1_ ｜ _设计: 技术选型、数据模型_

### 阶段 2: 完成回滚 journal

- [ ] 2.1 保存并继承已有文件权限，失败时恢复字节与权限
  - **证据块**: `patch.rs:497` 的 `restore_backups` 当前只写回 bytes；`patch.rs:513` 的 `replace_file` 直接 rename temp。
  - **涉及文件**: `patch_transaction.rs`。
  - _需求: FR-2_ ｜ _设计: 决策 3_

- [ ] 2.2 跟踪事务创建目录和 staging 临时文件，失败后 deepest-first 安全清理
  - **证据块**: `workspace.rs:247` 的 `resolve_for_write` 允许不存在父目录；`patch.rs:426` 后续会 `create_dir_all`，当前 journal 不记录这些目录。
  - **涉及文件**: `patch_transaction.rs`。
  - _需求: FR-2_ ｜ _设计: 决策 2_

- [ ] 2.3 增加私有 failure-injection replace seam，不暴露为 MCP/Actions 参数
  - **证据块**: `patch.rs:513` 目前所有 commit 都硬调用 `replace_file`，无法稳定制造第 N 步失败。
  - **涉及文件**: `patch_transaction.rs`。
  - _需求: FR-4, NFR-1_ ｜ _设计: API 设计_

### 阶段 3: 对照验收标准验证

- [ ] 3.1 添加确定性顺序、add/update/delete partial failure、temp/dir cleanup 回归
  - **证据块**: `patch.rs:583` 现有测试只覆盖 dry-run、CRLF、delete+add replacement 与“后续文件预检失败”，尚未覆盖 commit 中途失败。
  - **涉及文件**: `patch_transaction_tests.rs` 预计 220–320 行。
  - _需求: FR-1, FR-2, FR-4_ ｜ _设计: 测试策略_

- [ ] 3.2 验证 protected path/symlink/dry-run/critical delete 既有契约不变
  - **证据块**: `workspace.rs:329` / `:340` 已有 symlink 与 protected-path 拒绝入口，事务层不得绕开。
  - **涉及文件**: 现有测试 + `patch_transaction_tests.rs`。
  - _需求: FR-3_ ｜ _设计: 决策 4、测试策略_

- [ ] 3.3 Windows 2025 与 Ubuntu 24.04 完成 fmt/Clippy/tests/check、GitNexus staged detect 和 rollback 复核
  - **证据块**: AGENTS.md 要求 edit 前 impact、commit 前 detect_changes；pre-edit impact 已为 LOW。
  - **涉及文件**: 上述 3 个源码/测试文件，不增加 CI helper 到 production。
  - _需求: FR-1..FR-4, NFR-2..NFR-4_ ｜ _设计: 测试策略_

---

## 检查点

- [ ] 阶段 1 完成后：parser/policy/output contract 未变化，staged 顺序可观测且确定。
- [ ] 阶段 2 完成后：指定 commit step 故障可重复触发，Workspace 回到事务前字节/权限/目录状态。
- [ ] 阶段 3 完成后：双平台回归、GitNexus detect、SHA-256 和 rollback 证据齐全。

## 需求覆盖矩阵

| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 技术选型、架构设计 | 1.1, 1.2, 3.1, 3.3 | 未开始 |
| FR-2 | TransactionJournal、决策 2/3 | 2.1, 2.2, 3.1, 3.3 | 未开始 |
| FR-3 | API 设计、决策 4 | 1.1, 3.2, 3.3 | 未开始 |
| FR-4 | failure injection、测试策略 | 2.3, 3.1, 3.3 | 未开始 |

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---:|---|
| `src-tauri/src/tools/patch.rs` | 修改 | 净减少 80–130 | 保留 parser/preflight，委托事务模块 |
| `src-tauri/src/tools/patch_transaction.rs` | 新建 | 180–260 | deterministic stage/commit/rollback journal |
| `src-tauri/src/tools/patch_transaction_tests.rs` | 新建 | 220–320 | failure injection 与跨平台事务回归 |

## 检查清单

- [x] 交付物数量已锁定
- [x] 每条任务包含真实现状证据、文件预算和 FR/design 回链
- [x] 单文件预算均低于 500 行
- [x] 阶段 3 逐条覆盖验收标准
- [x] 全文无占位符、TODO 或省略号占位

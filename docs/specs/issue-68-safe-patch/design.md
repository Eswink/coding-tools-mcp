# 设计文档：issue-68-safe-patch

## 概述

本设计覆盖 FR-1、FR-2、FR-3、FR-4。核心策略是不改 patch parser 和 tool dispatch，只将现有事务写入部分抽成有界内部模块，并用确定性数据结构与事务 journal 补齐回滚元数据。

## 技术方案

### 技术选型

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| 路径顺序 | `BTreeMap` | Rust 标准库、确定性排序、无需新依赖 | FR-1 |
| 回滚记录 | 内部 `TransactionJournal` | 显式记录字节、权限、临时文件、创建目录 | FR-2 |
| 故障注入 | 私有 replace callback / test seam | 可指定第 N 次 replace 失败，不增加工具参数 | FR-4 |
| 模块拆分 | `patch_transaction.rs` + `patch_transaction_tests.rs` | `patch.rs` 已 667 行，避免继续膨胀 | NFR-3 |

### 架构设计

```
apply_patch / patch_check
        |
        v
parse + policy preflight        (patch.rs 保持)
        |
        v
BTreeMap<relative_path, bytes?> (稳定路径顺序)
        |
        v
patch_transaction::commit
  1. resolve + snapshot metadata
  2. record missing parent dirs
  3. write temp files + copy original permissions for updates
  4. commit in sorted order
  5. on failure: cleanup temps -> restore files/permissions -> remove created empty dirs
        |
        v
existing structured apply_patch result
```

## 数据模型

| 实体/字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| staged | `BTreeMap<String, Option<Vec<u8>>>` | workspace-relative | `Some` 为 add/update，`None` 为 delete |
| BackupEntry.bytes | `Option<Vec<u8>>` | 原始完整字节 | `None` 表示事务前不存在 |
| BackupEntry.permissions | `Option<fs::Permissions>` | 仅已有普通文件 | 成功更新和 rollback 都需保留 |
| TransactionJournal.created_dirs | `Vec<PathBuf>` | 仅本事务新建 | rollback 时 deepest-first、仅空目录删除 |
| TransactionJournal.temporary_files | `BTreeMap<PathBuf, PathBuf>` | 同 Workspace | 成功和失败都清理 |

## API 设计

| 方法/函数 | 签名方向 | 入参 | 出参 | 关联需求 |
|---|---|---|---|---|
| `commit_staged` | patch.rs 私有适配器 | text staged map | transaction result | FR-1..FR-3 |
| `commit_staged_bytes` | crate 内兼容入口 | byte staged map | backups / error | FR-1..FR-3 |
| `commit_staged_bytes_with_replace` | 私有内部 | staged + replace callback | transaction result | FR-4 |
| `rollback` | transaction 模块私有 | journal | best-effort cleanup | FR-2 |

不新增 MCP/HTTP/Actions 对外接口。

## 文件结构

```
src-tauri/src/tools/
├── patch.rs                       # 修改：parser/preflight + 调用事务模块
├── patch_transaction.rs           # 新增：确定性 stage/commit/rollback
└── patch_transaction_tests.rs     # 新增：failure injection 与事务不变量
```

## 设计决策

### 决策 1: 不在现有 patch.rs 继续堆叠事务逻辑（FR-1/FR-2）

**问题**: `patch.rs` 当前约 667 行，继续增加 journal 与 failure injection 会违反仓库可维护性目标。  
**决策**: 抽取事务层到英文新模块；parser 和 `apply_patch` 的 public behavior 保留在原文件。

### 决策 2: 只删除本事务创建的空目录（FR-2）

**问题**: rollback 不得误删并发创建或事务前存在的目录。  
**决策**: 创建目录前记录不存在的祖先链；rollback deepest-first 使用 `remove_dir`，只有仍为空时才能成功，失败即保留目录，不递归删除。

### 决策 3: 权限随已有目标继承（FR-2）

**问题**: rename 新临时文件可改变已有脚本/文件权限。  
**决策**: snapshot 原权限；已有文件的 temp 在 replace 前设置相同权限；rollback 写回后再次设置权限。新文件保留平台默认创建权限。

### 决策 4: 不改变 Windows replace 的现有语义（FR-3）

**问题**: Windows 现有实现会先删除目标再 rename。  
**决策**: 本增量不引入平台原子替换 API；通过 journal + failure injection 证明 delete 后 rename 失败也能恢复原状态。更强 OS 原子替换留给独立后续。

## 测试策略

- 单测：输入顺序改变时 commit callback 观察到相同路径顺序。
- 单测：第 1/第 2/N 次 replace 失败，验证 add/update/delete 混合事务全部恢复。
- Unix 单测：已有可执行文件 mode 在成功 update 和 rollback 后不变。
- 双平台单测：transaction-created nested directories 在失败后只删除本事务创建且为空的目录。
- 双平台单测：所有 `.harness-stage-*` 临时文件在成功/失败后为零。
- 回归：现有 patch parser、protected path、dry-run、critical delete tests。
- CI：Windows 2025 / Ubuntu 24.04 `cargo fmt --check`、Clippy `-D warnings`、相关/完整 Rust tests、`cargo check`。

## 风险评估

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| rollback 删除并发目录 | 高 | 只记录本事务创建目录，使用非递归 `remove_dir` |
| Windows replace failure 窗口 | 中 | failure injection 覆盖 delete-before-rename 后恢复 |
| 权限跨平台差异 | 中 | 使用 `fs::Permissions`；Unix 额外断言 mode，Windows 验证文件可读/字节恢复 |
| parser 行为回归 | 低 | parser 不移动，现有回归全跑 |

## 检查清单

- [x] 全部 FR 被设计覆盖
- [x] 无新外部依赖和对外 API
- [x] 文件拆分符合英文命名与行数约束
- [x] 回滚、权限、目录和故障注入均有验证策略

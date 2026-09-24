# 需求文档：issue-68-safe-patch

## 功能概述

本功能加固现有 `apply_patch` 的多文件事务提交与回滚，使补丁在 Windows 与 Ubuntu 上具有确定性提交顺序、可验证的失败回滚、权限保留和临时资源清理，同时保持当前 Workspace 写入边界、保护路径、dry-run 与确认语义不变。

## 历史经验与坑

- **可复用经验**: 现有实现已经先解析/预检全部 file patch，再通过临时文件写入和备份恢复完成提交；本次复用这一边界，不重写 unified diff / Codex patch parser。
- **必须规避的坑**: 当前 staged/backups 使用 `HashMap`，提交顺序不稳定；更新文件使用临时文件 rename 可能改变原文件权限；回滚恢复字节但不记录事务创建的父目录；缺少对“第 N 个 commit 故障”的可重复注入验证。

## 术语定义

- **Patch transaction**: 一次 `apply_patch` 调用中所有 add/update/delete 文件的原子提交单元。
- **Pre-existing state**: 事务开始前文件是否存在、原始字节和原始权限。
- **Transaction-created directory**: 事务开始前不存在、仅为本次新增文件创建的目录。
- **Failure injection**: 测试专用、确定性地让指定 replace/commit 步骤失败的内部机制，不暴露为 production API。

---

## 范围边界

**In Scope**
- 加固 `src-tauri/src/tools/patch.rs` 现有提交事务。
- 将事务实现拆分到英文命名内部模块，避免继续扩大已超过 500 行的 `patch.rs`。
- 确定性路径顺序、原始权限保存/恢复、临时文件清理、事务创建目录的失败回滚。
- add/update/delete 混合事务的故障注入测试。
- Windows 2025 与 Ubuntu 24.04 的 fmt、Clippy、Rust 回归和 check。

**Out of Scope**
- 不修改 diff/Codex patch 语法。
- 不增加 worktree、snapshot、undo 历史或跨进程事务。
- 不新增 sandbox、Hooks、Skills 执行、云端权限、UI 或 package 行为。
- 不放宽 `.git/.github`、symlink、Workspace escape、confirm 或 dry-run 规则。

---

## 需求列表

### FR-1: 确定性多文件事务顺序

**优先级:** Must  
**用户故事:** 作为本地编码执行器，我希望同一补丁总以稳定路径顺序提交，以便失败证据、回滚和测试可复现。

#### 验收标准

1. WHEN 多文件 patch 完成预检 THEN 系统 SHALL 以规范化 workspace-relative path 的稳定字典序执行 staging 与 commit。
2. WHEN 输入 file patch 顺序变化但语义相同 THEN 系统 SHALL 保持相同的事务提交顺序。
3. IF 同一路径出现 replacement 语义 THEN 系统 SHALL 保持现有最终 replacement 行为，不通过排序改变语义。

### FR-2: 任意提交点失败后恢复事务前状态

**优先级:** Must  
**用户故事:** 作为 Workspace 所有者，我希望任意一个文件提交失败时之前已写入的文件全部恢复，以免留下半应用补丁。

#### 验收标准

1. WHEN 第 N 个文件 replace/delete 失败 THEN 系统 SHALL 恢复此前所有已提交文件的原始存在状态和字节。
2. WHEN 事务修改已存在文件 THEN 系统 SHALL 在成功提交和失败回滚后保持原文件权限。
3. WHEN 事务新增文件并为它创建父目录 THEN 失败回滚 SHALL 删除新增文件，并仅删除本事务创建且仍为空的目录。
4. WHEN staging 或 commit 失败 THEN 系统 SHALL 删除本事务所有临时 staging 文件。

### FR-3: 保持现有安全与调用契约

**优先级:** Must  
**用户故事:** 作为安全边界维护者，我希望事务加固不改变当前 Workspace/policy 规则。

#### 验收标准

1. WHEN patch 目标是保护路径、Workspace escape 或 write symlink THEN 系统 SHALL 继续 fail-closed。
2. WHEN `dry_run=true` THEN 系统 SHALL 不修改文件、权限或目录。
3. WHEN 删除关键项目文件且未 `confirm=true` THEN 系统 SHALL 保持现有拒绝行为。
4. WHEN 事务成功 THEN `apply_patch` 的现有结构化结果字段 SHALL 保持兼容。

### FR-4: 可重复验证事务故障

**优先级:** Must  
**用户故事:** 作为维护者，我希望测试能在指定 commit 步骤注入失败，以证明回滚而不是只测试预检失败。

#### 验收标准

1. WHEN 测试要求第 N 次 replace 失败 THEN 内部测试 seam SHALL 稳定在该步骤失败且不暴露到 production 工具参数。
2. WHEN failure-injection 测试结束 THEN Workspace SHALL 与事务前快照一致，且不存在 harness-stage 临时文件。
3. WHEN 同一测试在 Windows 与 Ubuntu 运行 THEN SHALL 验证等价的事务不变量。

---

## 非功能需求

- **NFR-1（安全）**: 不新增远程/模型可调用权限；事务测试 seam 仅限 crate 内部或 `cfg(test)`。
- **NFR-2（兼容性）**: 保持现有 `apply_patch` / `patch_check` 输入输出兼容。
- **NFR-3（可维护性）**: 新事务模块和测试文件均使用英文文件名，单文件低于 500 行；现有 667 行 `patch.rs` 不继续承载新的事务实现细节。
- **NFR-4（确定性）**: 文件提交与回滚顺序不依赖 HashMap 随机迭代顺序。

## 依赖关系

- 依赖 manifest 中已 verified 的 `exec-policy`。
- 复用 `Workspace::resolve_for_write`、`reject_write_symlink`、`reject_protected_write_path`。
- 不依赖 #59 PTY、#62 listener、sandbox 或后续 worktree/snapshot。

## 检查清单

- [x] 已明确现有事务骨架与已知缺口
- [x] 需求覆盖成功、失败、安全与跨平台边界
- [x] FR-1..FR-4 均有可自动验证的验收标准
- [x] 范围与后续 worktree/snapshot 明确隔离

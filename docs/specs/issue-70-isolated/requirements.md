# 需求文档：issue-70-isolated

## 功能概述

为 Coding Tools MCP 的受信本地运行时增加有界、仓库归属、可审计的 Git worktree 生命周期核心。当前增量只负责在既有 Workspace 与 Harness 安全边界内创建、列举和安全移除 detached managed worktree，不暴露新的 MCP 公共工具，不实现 snapshot、sandbox、PTY、Hooks、云端权限、UI 或打包。

## 历史经验与坑

- 可复用经验：复用 Workspace 的 canonical root / symlink fail-closed 思路、Harness 的独立应用数据根，以及 safe-patch 已验证的最小 scope、真实双平台回归和 staged GitNexus 交付方式。
- 必须规避的坑：不把工作树放进主仓库造成 untracked 污染；不接受调用方提供任意目标路径；不使用 shell 拼接 Git 命令；不使用 force remove 删除脏 worktree；不在 Debug 或结构化结果中返回 host absolute path 或 Git stderr 原文。

## 术语定义

- Approved workspace：当前 Workspace 已 canonicalize 的受信工作区根。
- Repository root：通过 Git 在 approved workspace 中发现并 canonicalize 的仓库顶层，必须等于或位于 approved workspace 内。
- Harness state root：ToolContext.harness.store_root() 指向的应用拥有数据根，与 repository 工作目录分离。
- Managed root：harness-state/worktrees-v1/workspace-id；调用方不能覆盖。
- Managed worktree：由本模块创建、目录 basename 为合法 opaque ID、Git registry 仍确认归属于 repository root 的 detached worktree。
- Dirty worktree：Git 报告 tracked、staged 或 untracked 变化，或者状态无法在资源边界内可靠判定。

## 范围边界

### In Scope

- 从 approved workspace 发现 canonical repository root，并验证不逃逸 workspace。
- 在 Harness-owned managed root 下创建 detached worktree，使用服务生成的 opaque ID。
- 以有界、稳定、非敏感结构列举本模块管理的 worktrees。
- 仅移除属于 managed root、Git registry 可见且 clean 的 worktree。
- 对 path escape、非法 ID、symlink、非 Git repository、脏树、输出过大和 Git 执行失败 fail closed。
- Windows 2025 与 Ubuntu 24.04 真实 Git 生命周期回归。

### Out of Scope

- Snapshot、checkpoint、历史 revision rollback。
- 自动 commit、merge、rebase、stash、force remove 或 worktree repair。
- Sandbox、ConPTY/PTY、Hooks、云端授权、UI、打包。
- 新 MCP tool schema / registry exposure。
- 用户指定 arbitrary worktree destination 或 Harness state root。

## 需求列表

### FR-1: Canonical repository discovery stays inside approved workspace

优先级：Must

1. WHEN manager 初始化 THEN 系统 SHALL 使用非 shell Git argv 获取 show-toplevel，canonicalize 后确认 repository root 等于或位于 approved workspace 内。
2. IF workspace 不是 Git repository、Git 不可执行、返回路径不可 canonicalize 或逃逸 workspace THEN 系统 SHALL fail closed，并且不创建 managed root。
3. IF repository root 或 managed root 存在 symlink 边界歧义 THEN 系统 SHALL 拒绝生命周期操作。

### FR-2: Create a bounded detached managed worktree

优先级：Must

1. WHEN create 被调用且 managed 数量小于上限 THEN 系统 SHALL 生成 32 位小写 hex opaque ID，并在 harness-state/worktrees-v1/workspace-id/id 创建 detached worktree。
2. WHEN Git worktree add 成功 THEN 系统 SHALL 返回 opaque ID、managed/id 显示路径和有界 HEAD 标识，不返回 host absolute path。
3. IF managed 数量达到 8、目标已存在、Git add 失败或命令输出超过 64 KiB THEN 系统 SHALL fail closed，并清理仅由本次创建的空目录或失败残留。

### FR-3: List only verified managed worktrees with bounded output

优先级：Must

1. WHEN list 被调用 THEN 系统 SHALL 解析 Git worktree registry，仅保留 canonical path 位于 managed root 下且 basename 为合法 opaque ID 的条目。
2. WHEN 返回列表 THEN 系统 SHALL 按 ID 稳定排序，最多返回 8 条，每条只含 ID、managed/id 显示路径、HEAD 标识和 detached 状态。
3. IF Git registry 输出超过 64 KiB、条目不可解析或 managed path 出现 symlink/escape THEN 系统 SHALL fail closed，而不是返回部分可信列表。

### FR-4: Remove only clean managed worktrees

优先级：Must

1. WHEN remove 收到合法 managed ID THEN 系统 SHALL 从固定 managed root 派生目标，禁止调用方传入路径。
2. WHEN worktree 被 Git registry 确认管理且 dirty check 为空 THEN 系统 SHALL 使用非 force git worktree remove 移除，并确认 managed path 不再存在。
3. IF worktree 存在 tracked、staged 或 untracked 变化、状态检查超过边界、ID 不存在、路径不是受管 worktree 或 Git 拒绝移除 THEN 系统 SHALL fail closed，且不得删除文件。
4. WHEN 同一 ID 已不存在 THEN 系统 SHALL 返回稳定 NotFound，而不是匹配其他路径。

### FR-5: Security and observability remain bounded and non-secret

优先级：Must

1. WHEN error/debug/output 被序列化 THEN 系统 SHALL 使用稳定错误类别与 opaque ID，不回显任意 Git stderr、环境变量、Harness absolute root 或 repository absolute root。
2. WHEN Git 子进程执行 THEN 系统 SHALL 使用 argv API、显式 cwd 与输出上限，不通过 shell 拼接用户数据。
3. WHEN 后续公共工具接入 manager THEN manager SHALL 不自行绕过 local admission、capability 或 protected-path 策略。

### FR-6: Cross-platform lifecycle is deterministic

优先级：Must

1. WHEN Windows 2025 与 Ubuntu 24.04 运行真实 Git 测试 THEN create-list-remove、dirty refusal、invalid ID、outside-repo rejection、capacity 和 NotFound SHALL 保持同一逻辑语义。
2. IF 平台路径大小写或分隔符不同 THEN 系统 SHALL 通过 canonical Path API 判断边界，不通过字符串前缀做安全判断。
3. WHEN 现有 Git/read-only tools、Harness 或 safe-patch tests 运行 THEN 系统 SHALL 无行为回归。

## 非功能需求

- NFR-1 资源：最多 8 个 managed worktrees；单次 Git stdout/stderr 合计保留不超过 64 KiB；ID 固定 32 个 ASCII hex 字符。
- NFR-2 安全：无 shell command string、无 arbitrary destination、无 force remove、无绝对路径泄漏；不确定状态一律拒绝。
- NFR-3 兼容：Windows 2025 与 Ubuntu 24.04 同一逻辑契约，不新增平台特定公共 API。
- NFR-4 源码：实现文件和测试文件分别保持 500 行以下。

## 依赖关系

- safe-patch 已 verified，是本 task 的交付依赖，本 Issue 不修改其 parser/transaction。
- 复用 Workspace canonical boundary 与 Harness store_root/workspace_id。
- snapshot-rollback 是下游依赖，本 Issue 不实现。
- tool-discovery 后续决定公共工具 exposure，本 Issue 不修改 registry。

## 检查清单

- [x] 历史经验已转化为 fail-closed、no-force、bounded-output 约束。
- [x] FR-1 到 FR-6 都有可测试验收标准。
- [x] In Scope 与 Out of Scope 明确。
- [x] 资源、安全、兼容和源码规模要求量化。
- [x] 上游与下游依赖明确。

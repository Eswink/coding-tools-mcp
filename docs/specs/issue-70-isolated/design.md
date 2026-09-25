# 设计文档：issue-70-isolated

## 概述

实现内部 WorktreeManager 核心，在 Harness-owned state root 下管理 detached Git worktrees。当前增量不扩展 MCP tool catalog；后续 tool-discovery 与 snapshot-rollback 通过该内部 API 组合能力。这样复用 Workspace/Harness 边界，同时不扩大现有 src-tauri/src/tools/git.rs 的只读职责。

对应需求：FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, NFR-1, NFR-2, NFR-3, NFR-4

## 技术方案

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| 生命周期模块 | src-tauri/src/harness/worktree.rs | Worktree 是 Harness 的隔离执行资源；Harness 已拥有独立 state root | FR-1, FR-2 |
| 测试模块 | src-tauri/src/harness/worktree_tests.rs | 独立文件保证实现与测试均低于 500 行 | FR-6, NFR-4 |
| 模块导出 | 修改 src-tauri/src/harness/mod.rs | 仅导出内部可复用 manager/result 类型，不注册 MCP tool | FR-5 |
| Git 执行 | std::process::Command argv API + bounded pipe reader | 无 shell 拼接；显式 cwd、输出上限和 exit status | FR-2, FR-5 |
| managed root | Harness store root / worktrees-v1 / workspace-id | 与 repository 分离，路径由 runtime 固定派生 | FR-2 |
| worktree mode | detached current HEAD | 不引入 branch ownership / merge 语义 | FR-2 |
| dirty 判定 | bounded git status porcelain including untracked | 任一变更都阻止删除；输出超限即拒绝 | FR-4 |
| registry source | git worktree list porcelain -z | Git registry 是管理事实来源 | FR-3 |

## 架构设计

~~~text
ToolContext
  ├─ Workspace (canonical approved workspace)
  └─ Harness
       ├─ workspace_id()
       └─ store_root()
              │
              ▼
        WorktreeManager
          ├─ discover_repository_root()
          ├─ create_detached()
          ├─ list_managed()
          └─ remove_clean()
              │
              ▼
        bounded Git argv runner
~~~

主仓库、MCP registry、safe-patch parser 与 snapshot 逻辑均不进入该模块。

## 数据模型

不新增数据库或 metadata 文件；Git worktree registry 与 deterministic managed path 是事实来源。

| 实体/字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| ManagedWorktree.id | String | 32 lowercase hex | 服务生成 opaque ID / dir basename |
| ManagedWorktree.display_path | String | managed/id | 不暴露 host absolute path |
| ManagedWorktree.head | String | 最多 64 ASCII hex | Git HEAD identity |
| ManagedWorktree.detached | bool | 第一增量恒 true | 无 branch ownership |
| WorktreeManager.repository_root | PathBuf | canonical 且位于 approved workspace | 内部字段，Debug 不输出 |
| WorktreeManager.managed_root | PathBuf | Harness-owned 固定派生 | 内部字段，Debug 不输出 |

## API 设计

| 方法 | 入参 | 出参 | 关联需求 |
|---|---|---|---|
| WorktreeManager::new | workspace_root, harness_root, workspace_id | Result<Manager> | FR-1 |
| create_detached | 无用户 destination | Result<ManagedWorktree> | FR-2 |
| list | 无 | Result<Vec<ManagedWorktree>> | FR-3 |
| remove_clean | strict opaque ID | Result<()> | FR-4 |
| Debug | 无 | 安全计数/状态 | FR-5 |

内部错误枚举：NotRepository、BoundaryViolation、Capacity、Dirty、NotFound、GitUnavailable、GitFailed、OutputLimit。Display 使用固定非敏感消息，不含 Git stderr 或绝对路径。

## 文件结构

~~~text
src-tauri/src/harness/
├── mod.rs
├── worktree.rs
└── worktree_tests.rs
~~~

预计不修改 tools/git.rs、workspace.rs、registry/schema 或 safe-patch。

## 设计决策

### 决策 1: Managed root 放在 Harness state

repository 内嵌目录会产生 untracked 污染。选择 Harness store / worktrees-v1 / workspace-id；调用方不能提供 destination，也无需修改 .git/info/exclude。

### 决策 2: 第一增量只创建 detached HEAD

不接受任意 branch/ref，避免 branch takeover、merge/rebase 和 snapshot 语义扩张。revision pinning 留给 snapshot-rollback 设计。

### 决策 3: Git registry 是事实来源

list/remove 以 git worktree list porcelain -z 为权威来源；目录存在只作为第二层边界，不足以证明 managed ownership。

### 决策 4: Dirty worktree 永不 force remove

第一增量完全不调用 force；dirty、输出过大或解析失败均拒绝。

### 决策 5: 公共 tool exposure 延后

本 Issue 只交付内部 Harness API。tool-discovery 后续决定公开 surface，并复用既有 admission/capability contract。

## 测试策略

1. 临时真实 Git repository，配置本地 user.name/user.email 并提交初始 HEAD。
2. Windows 2025 与 Ubuntu 24.04 验证 create-list-remove clean 生命周期。
3. tracked、staged、untracked 三类 dirty 分别验证 remove fail closed。
4. 非 repo、repo root 逃逸、非法 ID、managed symlink、capacity=8、unknown ID 全拒绝。
5. list 仅返回合法 managed ID，稳定排序。
6. Debug / error 不含 workspace absolute path、harness root 和 secret fixture。
7. Git output 超过边界时返回 OutputLimit，绝不继续 destructive remove。
8. 完整相关 Rust suite + staged GitNexus detect，确认 safe-patch/git/Harness 无回归。

## 风险评估

| 风险 | 影响 | 缓解 |
|---|---|---|
| Git CLI 跨平台差异 | 中 | Windows/Ubuntu 真实 runner；argv 不走 shell |
| path escape / symlink | 高 | canonical Path API + strict ID + registry/managed-root 双校验 |
| dirty tree 被误删 | 高 | status 必须可靠为空；不使用 force |
| Git 输出过大 | 中 | bounded reader，超限 fail closed |
| orphan managed dir | 中 | Git registry 是事实来源；失败保留可诊断状态，不递归误删 |
| 模块膨胀 | 中 | 实现/测试拆文件，分别 <500 行 |

## 检查清单

- [x] 技术方案与 Workspace/Harness 架构一致。
- [x] FR-1 至 FR-6 全覆盖。
- [x] 文件结构使用当前真实路径。
- [x] API、类型和安全边界明确。
- [x] 关键决策包含理由和替代方案。
- [x] 测试策略可验证验收标准。

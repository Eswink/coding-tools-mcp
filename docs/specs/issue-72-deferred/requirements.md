# 需求文档：issue-72-deferred

## 功能概述

Issue #72 评估并实现最小 Deferred tool discovery：从现有 ToolRegistry 只读发现 Deferred 元数据，同时严格保留 Direct/Deferred/Hidden 分层和本地授权边界。

## 范围边界

### In Scope
- 只读发现 `ToolExposure::Deferred` 条目。
- 稳定 ToolName 排序、固定 entry bound 与 encoded-metadata byte bound。
- 返回明确的 omitted/truncated 状态。
- focused tests 与 Windows/Ubuntu 验证。

### Out of Scope
- 自动执行/提升 Deferred tool。
- 新 LocalAdmission、capability 扩张、policy bypass。
- cloud publication、UI、sandbox、worktree、snapshot、Hooks、PTY、packaging。

## 需求列表

| FR ID | 需求摘要 | 主子规格 |
|---|---|---|
| FR-1 | 发现结果仅包含 Deferred tool，按 ToolName 稳定排序；Direct/Hidden 永不出现。 | deferred-catalog-contract |
| FR-2 | 发现结果受 repository-owned entry/byte 上限约束，并稳定报告是否有 Deferred 条目被省略。 | deferred-catalog-contract |
| FR-3 | discovery 不得执行 executor、构造/复用 VerifiedInvocation、修改 registry、扩大 capability 或要求 LocalAdmission。 | discovery-safety-evaluation |

## 非功能需求

- 继续使用 ToolSpec 已有 name/description/schema 校验上限。
- Debug/output 不得包含 executor 内部、host-global path、secret 或 authority。
- 新 Rust 文件必须英文命名且满足源码长度规则。
- 发布前必须有 staged GitNexus detect、双平台真实测试、code review 和 rollback 证据。

## 依赖关系

- 依赖已 verified 的 `tool-runtime`。
- 子规格依赖见 `spec-manifest.json`。

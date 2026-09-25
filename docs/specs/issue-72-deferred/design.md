# 设计文档：issue-72-deferred

## 概述

现有 ToolRegistry 使用 `BTreeMap` 保存工具并已有 Direct/Deferred/Hidden 分层；`deferred_specs()` 会克隆全部 Deferred ToolSpec，但没有显式的有界 discovery contract。

## 对应需求

- FR-1：visibility 与 deterministic ordering。
- FR-2：entry/metadata byte bounds 与 omitted 状态。
- FR-3：metadata-only / no-execution authority boundary。

## 技术方案

在 local-agent registry 边界新增一个小型 immutable Deferred discovery value，以及专用只读 registry method。

- registry 仍是元数据 SSOT。
- 仅选择 `ToolExposure::Deferred`。
- 直接按现有 `BTreeMap` 顺序遍历，达到固定 entry/byte 上限后停止，不先克隆全量集合。
- result 只持有 cloned validated ToolSpec 与 returned/omitted/metadata-bytes 等非敏感摘要。
- discovery 不调用 `invoke` / `ToolExecutor::execute`，不接触 LocalAdmission。
- 旧 Direct invocation 路径和 Hidden registration 行为不变。

## 文件结构

- `services/local-agent/src/registry.rs`：bounded discovery contract / method。
- `services/local-agent/src/registry_tests.rs`：排序、visibility、bounds、no-execution tests。
- `services/local-agent/src/model.rs`：仅在确有必要时复用/导出常量；优先不改。
- 不新增云端、UI 或运行时文件。

## 设计决策

- 不改变 `ToolSpec` 序列化/authority 语义。
- 不删除现有 `deferred_specs()` compatibility method；新 bounded discovery 是显式评估入口。
- GitNexus 对 `deferred_specs` 为 UNKNOWN/exact、0 resolved callers；结合全仓文本搜索无 production caller，只能作为 lower-confidence evidence，不能视为“未使用证明”。

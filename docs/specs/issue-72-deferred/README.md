# issue-72-deferred

## 原则

只在现有 `services/local-agent` ToolRegistry 上评估并实现一个有界的 Deferred-tool discovery view。本增量不执行工具、不创建 authority、不改变 admission/capability，也不发布 Hidden tools。

## 子规格索引

| ID | 标题 | FR | 依赖 |
|---|---|---|---|
| deferred-catalog-contract | Deferred catalog contract | FR-1, FR-2 | 无 |
| discovery-safety-evaluation | Discovery safety and evaluation | FR-3 | deferred-catalog-contract |

## 依赖关系

`discovery-safety-evaluation` 依赖 `deferred-catalog-contract`。跨模块契约仅限 ToolRegistry/ToolSpec 元数据读取，不引入 wire/cloud/runtime 依赖。

## 里程碑

1. 冻结 deterministic bounded catalog 语义。
2. 完成可见性、截断与 no-execution 安全验证。
3. 完成 Windows 2025 / Ubuntu 24.04 双平台验证与 code review。

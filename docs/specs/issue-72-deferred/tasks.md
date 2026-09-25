# 任务清单：issue-72-deferred

## 交付物清单

- bounded Deferred discovery production contract。
- focused registry regression tests。
- staged GitNexus / Windows 2025 / Ubuntu 24.04 / code-review evidence。

## 任务列表

- [ ] 1. 完成 deferred-catalog-contract/1.1。
- [ ] 2. 完成 discovery-safety-evaluation/1.1。
- [ ] 3. 完成 staged detect、双平台测试、review 与 publish verification。

## 需求覆盖矩阵

| FR ID | 子规格 | 任务引用 | 状态 |
|---|---|---|---|
| FR-1 | deferred-catalog-contract | deferred-catalog-contract/1.1 | 未开始 |
| FR-2 | deferred-catalog-contract | deferred-catalog-contract/1.1 | 未开始 |
| FR-3 | discovery-safety-evaluation | discovery-safety-evaluation/1.1 | 未开始 |

## 文件变更清单

- `services/local-agent/src/registry.rs`
- `services/local-agent/src/registry_tests.rs`
- `services/local-agent/src/model.rs`（仅必要时）

## 子规格任务覆盖矩阵

- `deferred-catalog-contract/1.1` → FR-1, FR-2
- `discovery-safety-evaluation/1.1` → FR-3

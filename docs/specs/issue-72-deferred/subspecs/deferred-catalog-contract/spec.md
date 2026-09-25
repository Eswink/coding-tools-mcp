# 子规格：Deferred catalog contract

## 范围

定义只面向 Deferred tools 的 immutable、deterministic、bounded metadata view。

## 需求回链

- FR-1
- FR-2

## 验收标准（EARS）

1. WHEN registry 同时存在 Direct、Deferred、Hidden tools THEN discovery SHALL 仅返回 Deferred tools，并按 ToolName 升序。
2. WHEN Deferred tool 数量超过 entry bound THEN discovery SHALL 最多返回 bound 数量，并将 omitted 标记为 true。
3. WHEN 下一条 Deferred metadata 会使 encoded-metadata bytes 超出 byte bound THEN discovery SHALL 在加入该条目之前停止，并将 omitted 标记为 true。
4. WHEN caller 读取 discovered item THEN item SHALL 仅包含 cloned validated ToolSpec metadata 与 bounded summary，不包含 executor、admission、host path 或 secret。

## 涉及文件

- `services/local-agent/src/registry.rs`
- `services/local-agent/src/registry_tests.rs`
- `services/local-agent/src/model.rs`（仅必要时）

## 不做项

- 不新增 wire protocol / cloud publication / automatic execution。
- 不修改 LocalAdmission、capability 或 invocation policy。

## 设计要点

直接按 ToolRegistry 的 BTreeMap 顺序边遍历边截断，避免先克隆全量 Deferred 集合。

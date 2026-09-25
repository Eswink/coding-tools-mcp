# 子规格：Discovery safety and evaluation

## 范围

证明 discovery 是 metadata-only，并保持 local authority boundary。

## 需求回链

- FR-3

## 验收标准（EARS）

1. WHEN discovery 被调用 THEN 系统 SHALL 不调用任何 registered executor。
2. WHEN registry 含 Hidden 或 Direct tools THEN discovery SHALL 不返回它们。
3. WHEN 对同一 registry 重复 discovery THEN order、returned metadata 与 omitted 状态 SHALL 稳定一致。
4. WHEN 在 Windows 2025 与 Ubuntu 24.04 验证 THEN focused registry tests 与 relevant local-agent full tests SHALL 通过。

## 涉及文件

- `services/local-agent/src/registry_tests.rs`
- 仅为 catalog contract 必需的 production 文件

## 不做项

- 不新增 authority、capability、policy、network、process 或 persistence 行为。

## 设计要点

使用带原子 execute counter 的 test executor 证明 discovery 不触发 `ToolExecutor::execute`；同时覆盖 entry/byte truncation 和 Hidden/Direct exclusion。

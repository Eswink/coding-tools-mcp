# 子规格：Cloud protocol and offline foundation

## 范围

本子规格负责 FR-1, FR-2, FR-3；依赖 无。详见母规格 design.md 和 issues.md。

## 需求回链

- FR-1
- FR-2
- FR-3

## 验收标准（EARS）

1. WHEN the synthetic worker becomes offline THEN the Gateway SHALL keep discovery and the catalog available without changing catalog bytes (FR-1).
2. WHEN a modern or legacy request is received THEN the adapter SHALL emit the corresponding envelope and reject mismatched metadata (FR-2).
3. WHEN credentials are invalid THEN the HTTP endpoint SHALL reject authentication instead of returning an offline tool result (FR-2).
4. WHEN a foreign conversation calls a business tool THEN the Gateway SHALL return the same permission denial before reading presence (FR-3).
5. WHEN a new approval is requested while offline THEN no pending record SHALL be allocated (FR-3).
6. WHEN execution outcome is unknown THEN the Gateway SHALL return a distinct non-replayable result, not claim non-execution (FR-3).

## 涉及文件

- design.md, threat-model.md, protocol.md
- prototypes/cloud-gateway/*.mjs, tests/cloud-gateway/*.test.mjs
- future cloud Gateway crate and integration tests

## 不做项

本批不切换生产 Connector，不复制令牌到测试，不声称真实 Host 已验证。非本子规格 FR 由 manifest 指定 owner。

## 设计要点

先冻结合同，再做小步实现、测试、review。必须保留数据归属与 fail-closed 边界；协议实验室不能作为 production 启动入口。

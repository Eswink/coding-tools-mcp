# 子规格：Cloud OAuth, local approval and outbound device transport

## 范围

本子规格负责 FR-4, FR-5；依赖 gateway-foundation。详见母规格 design.md 和 issues.md。

## 需求回链

- FR-4
- FR-5

## 验收标准（EARS）

1. WHEN OAuth refresh is requested while the workstation is off THEN the cloud authorization service SHALL process it without contacting the Agent (FR-4).
2. WHEN a cloud ticket lacks a matching active local grant THEN the Agent SHALL deny execution regardless of valid ticket signature (FR-4).
3. WHEN an old socket closes after a new device generation is accepted THEN the Gateway SHALL preserve the replacement connection (FR-5).
4. WHEN a mutation response is lost THEN the system SHALL reconcile the original request ID and SHALL NOT enqueue a fresh execution on reconnect (FR-5).
5. WHEN prior work cannot be proven quiescent THEN a new owner SHALL be blocked by recovery/draining (FR-4, FR-5).

## 涉及文件

- future cloud auth/local approval adapters
- future agent transport and journal

## 不做项

本批不切换生产 Connector，不复制令牌到测试，不声称真实 Host 已验证。非本子规格 FR 由 manifest 指定 owner。

## 设计要点

先冻结合同，再做小步实现、测试、review。必须保留数据归属与 fail-closed 边界；协议实验室不能作为 production 启动入口。

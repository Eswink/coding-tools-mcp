# 子规格：Migration, deployment, packages and real ChatGPT acceptance

## 范围

本子规格负责 FR-8, FR-9；依赖 agent-channel, agent-runtime。详见母规格 design.md 和 issues.md。

## 需求回链

- FR-8
- FR-9

## 验收标准（EARS）

1. WHEN routing is migrated THEN issuer/resource/key/refresh continuity SHALL be checked explicitly and the old executable SHALL remain recoverable (FR-8).
2. WHEN a backup is restored THEN revoked or uncertain local execution authority SHALL not be silently reactivated (FR-8).
3. WHEN both real platforms pass installed tests THEN the record SHALL still distinguish them from real ChatGPT observations (FR-9).
4. WHEN the workstation shuts down while cloud OAuth remains valid THEN a real ChatGPT invocation SHALL be observed for reconnect/OAuth UI before claiming HOST_VALIDATED (FR-9).

## 涉及文件

- future deploy manifests and migration runbook
- acceptance evidence, Windows/Ubuntu package workflows

## 不做项

本批不切换生产 Connector，不复制令牌到测试，不声称真实 Host 已验证。非本子规格 FR 由 manifest 指定 owner。

## 设计要点

先冻结合同，再做小步实现、测试、review。必须保留数据归属与 fail-closed 边界；协议实验室不能作为 production 启动入口。

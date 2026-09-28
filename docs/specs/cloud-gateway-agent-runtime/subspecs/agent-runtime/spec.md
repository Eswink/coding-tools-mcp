# 子规格：Codex-inspired Windows and Ubuntu execution runtime

## 范围

本子规格负责 FR-6, FR-7；依赖 agent-channel。详见母规格 design.md 和 issues.md。

## 需求回链

- FR-6
- FR-7

## 验收标准（EARS）

1. WHEN a tool is invoked through cloud transport THEN the same local executor and authorization ceiling SHALL apply as for the desktop path (FR-6).
2. WHEN a command times out or is cancelled THEN platform-native process controls SHALL report terminal or unknown state without claiming rollback (FR-6).
3. WHEN an OS cannot enforce a requested sandbox policy THEN execution SHALL fail closed instead of silently using weaker isolation (FR-7).
4. WHEN project instructions, Skills or Hooks request greater privilege THEN the runtime SHALL treat them as untrusted content, not a grant (FR-7).

## 涉及文件

- future agent-core crate, native Windows and Ubuntu tests
- future policy, sandbox, skills, patch and trace modules

## 不做项

本批不切换生产 Connector，不复制令牌到测试，不声称真实 Host 已验证。非本子规格 FR 由 manifest 指定 owner。

## 设计要点

先冻结合同，再做小步实现、测试、review。必须保留数据归属与 fail-closed 边界；协议实验室不能作为 production 启动入口。

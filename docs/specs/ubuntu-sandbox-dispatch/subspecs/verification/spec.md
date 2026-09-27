# 子规格：Actual dispatcher and lifecycle acceptance

## 范围

Native host integration owned by verification; production implementation remains blocked this turn.

## 需求回链

- FR-6
- FR-7

## 验收标准（EARS）

FR-6: WHEN synthetic authenticated requests traverse /mcp THEN automated tests SHALL prove workspace read/write and symlink containment, network denial and valid in-workspace execution through the real dispatcher, not only ProcessManager fixtures.

FR-7: WHEN implementation is a candidate for integration THEN automated checks SHALL cover cancellation, timeout, output caps, admission expiry, restart/no-replay, supported toolchains and unchanged Windows behavior, tied to exact commit/tree; missing tests SHALL remain unverified.

## 涉及文件

See parent design.md for the actual dispatcher and constructor paths; no production edit is authorized by this document.

## 不做项

No physical-host testing, cloud-minted local grants, model-controlled disable switches or production rollout.

## 设计要点

Follow the immutable workspace and one-use native permit contract in the parent design.

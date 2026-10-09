# windows-guest-owned-output-freeze

## 原则

此独立草稿补齐 guest 文件数据观测，不授权宿主写入。基础为 diagnostic D750 加冻结 33/producer12/IO11；实际 F2 未知。新增代码尚无 guestmain 调用。生产入口保持 SANDBOX_REQUIRED，snapshot/restore/PR98 边界不变。

## 子规格索引

| ID | 标题 | FR | 依赖 |
|---|---|---|---|
| raw-output-owner | Guest create-only output handle owner | FR-1, FR-2, FR-5 | 无 |
| freeze-output-bytes | Checked writer closure and exact input/output bytes freeze | FR-3, FR-4, FR-5 | raw-output-owner |

## 依赖关系

spec-manifest.json 维护两子规格与 FR 归属；宿主 opened-root/actual permit、真实 guest workload、可取消 IO、HCS 退出和不可 Clone native output issuer 均为后续独立接入。

## 里程碑

先完整规格和 impact；再实现实际 raw HANDLE 机制；本机只做 portable 和 Windows 组件类型检查；原生用例明确 NOTRUN。最后冻结 source/evidence 并独立审查，不 seal 或提交。

# 任务清单：cloud-gateway-agent-runtime

## 交付物清单

子规格维护任务明细。本批仅 gateway-foundation/1.1 与 1.2；其他均未实施。总体工作流保持 active，不将第一批 green 等同全工程收敛。

## 任务列表

M1 完成规格和实验；M2 生产身份与通道；M3 早期真实 Host PoC；M4 工具增强；M5 部署迁移和最终验收。完整依赖由 manifest 与 issues.md 维护。

## 需求覆盖矩阵

| FR ID | 子规格 | 任务引用 | 状态 |
|---|---|---|---|
| FR-1 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-2 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-3 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-4 | agent-channel | agent-channel/2.1 | 未开始 |
| FR-5 | agent-channel | agent-channel/2.2 | 未开始 |
| FR-6 | agent-runtime | agent-runtime/3.1 | 未开始 |
| FR-7 | agent-runtime | agent-runtime/3.2 | 未开始 |
| FR-8 | deployment-acceptance | deployment-acceptance/4.1 | 未开始 |
| FR-9 | deployment-acceptance | deployment-acceptance/4.2 | 未开始 |

## 文件变更清单

只新增本目录、prototypes/cloud-gateway、tests/cloud-gateway 和独立 cloud-gateway workflow。现有 src、src-tauri、package/lock、安装器、AGENTS.md 等不得混入本批变更。

## 子规格任务覆盖矩阵

| 任务引用 | 摘要 | FR |
|---|---|---|
| gateway-foundation/1.1 | Write architecture, threat model and versioned wire contracts | FR-1, FR-2, FR-3 |
| gateway-foundation/1.2 | Implement and test isolated loopback-only protocol lab | FR-1, FR-2, FR-3 |
| gateway-foundation/1.3 | Replace fixture with production Gateway only after channel and OAuth gates | FR-1, FR-2, FR-3 |
| agent-channel/2.1 | Implement production OAuth and signed local grant projection | FR-4 |
| agent-channel/2.2 | Implement enrollment, outbound WSS, fencing and durable request reconciliation | FR-5 |
| agent-runtime/3.1 | Extract shared tool contracts and unify bounded execution/PTY state | FR-6 |
| agent-runtime/3.2 | Add policy/sandbox and bounded project coding capabilities | FR-7 |
| deployment-acceptance/4.1 | Build reversible deployment, backup/restore and origin/OAuth migration | FR-8 |
| deployment-acceptance/4.2 | Run isolated early Host PoC then final native/ChatGPT acceptance | FR-9 |

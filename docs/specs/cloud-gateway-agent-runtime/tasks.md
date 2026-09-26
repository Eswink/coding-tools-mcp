# 任务清单：cloud-gateway-agent-runtime

## 交付物清单

子规格维护任务明细。M1 gateway-foundation/1.1、1.2 已验证；Round 2 新增 agent-channel/2.1、2.2 的身份/签名原语和 deployment-acceptance/4.1 的受限配置蓝图，均为部分实现。生产集成和真实 Host 验收未完成，总体工作流保持 active。

## 任务列表

M1 完成规格和实验；M2 生产身份与通道；M3 早期真实 Host PoC；M4 工具增强；M5 部署迁移和最终验收。完整依赖由 manifest 与 issues.md 维护。

## 需求覆盖矩阵

| FR ID | 子规格 | 任务引用 | 状态 |
|---|---|---|---|
| FR-1 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-2 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-3 | gateway-foundation | gateway-foundation/1.1, gateway-foundation/1.2, gateway-foundation/1.3 | 第一批进行中 |
| FR-4 | agent-channel | agent-channel/2.1 | 身份原语已本地验证；生产授权控制器待集成 |
| FR-5 | agent-channel | agent-channel/2.2 | 注册原语已本地验证；WSS/执行日志待集成 |
| FR-6 | agent-runtime | agent-runtime/3.1 | 未开始 |
| FR-7 | agent-runtime | agent-runtime/3.2 | 未开始 |
| FR-8 | deployment-acceptance | deployment-acceptance/4.1 | 配置蓝图已验证；VPS/恢复/迁移未执行 |
| FR-9 | deployment-acceptance | deployment-acceptance/4.2 | 未开始 |

## 文件变更清单

M1 新增本目录、prototypes/cloud-gateway、tests/cloud-gateway 和独立 cloud-gateway workflow。Round 2 另增 services/cloud-gateway（独立 crate 与锁文件）、deploy/cloud-gateway、tests/cloud-gateway-deployment，及身份 CI；仅扩展旧实验 workflow 的新增目录范围检查。现有 src、src-tauri、根 package/lock、安装器、AGENTS.md 等不得混入变更。

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

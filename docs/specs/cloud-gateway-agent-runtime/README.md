# Cloud Gateway + Local Agent Runtime

状态：IN_PROGRESS；第一批为 NON_PRODUCTION_PROTOCOL_LAB。
基线：`main@758c60a6e74e624e144f9c19c5f19d04d17f7a13`。
分支：`feat/cloud-gateway-agent-runtime`。总跟踪：[GitHub #32](https://github.com/Eswink/coding-tools-mcp/issues/32)。

## 原则

公开 MCP/OAuth 由云服务器回答，本地关机不再等于公开 Connector 关停。云端不是简单反向代理；必须独立完成协议发现、稳定工具目录、OAuth 和权限检查，再根据 Agent 可用性路由。

本地用户仍是执行授权的最终决定者。共享 ChatGPT 登录不等于可靠的员工身份。网关在线也不意味着本地允许执行。无论新的传输如何工作，不能绕过既有 scopes、exclusive owner、执行门控和恢复锁。

本目录记录完整目标，而**第一批只交付规格、协议实验代码和测试**：不提供生产 OAuth、设备注册、真实文件或命令工具。实验身份和执行器均为显式 fixture，不能部署为公网服务；不得把实验通过描述为真实 ChatGPT 重连问题已修复。

## 子规格索引

| ID | 内容 | FR | 依赖 |
|---|---|---|---|
| [gateway-foundation](subspecs/gateway-foundation/spec.md) | 协议与离线语义 | FR-1, FR-2, FR-3 | 无 |
| [agent-channel](subspecs/agent-channel/spec.md) | OAuth、本地授权、设备出站通道 | FR-4, FR-5 | gateway-foundation |
| [agent-runtime](subspecs/agent-runtime/spec.md) | Windows/Ubuntu 工具核心 | FR-6, FR-7 | agent-channel |
| [deployment-acceptance](subspecs/deployment-acceptance/spec.md) | 部署、迁移、真实验收 | FR-8, FR-9 | agent-channel, agent-runtime |

## 依赖关系

以 `spec-manifest.json` 为依赖 SSOT：foundation -> channel -> runtime；部署验收依赖 channel/runtime。M3 提前验证最小安全云路径，不代表放宽最终 gate。

## 里程碑

1. M1：架构与协议实验室，隔离验证而不触碰现有桌面执行链。
2. M2：生产 OAuth、Agent enrollment、双重授权、出站通道。
3. M3：在隔离 VPS 路由完成真实 ChatGPT 的 Agent 离线 PoC，尽早检验产品假设。
4. M4：Codex-inspired 执行核心、PTY、策略、原生沙箱、文件和项目能力。
5. M5：受控切换现有 Connector、双平台安装验收、备份恢复和最终真实 Host 验收。

M3 不等待全部高级工具开发；最终 M5 仍覆盖完整已启用功能。此前口头 ISSUE-010..045 实际是 **36 个 Issue**，见 [issues.md](issues.md)。

## 导航

[需求](requirements.md) · [设计](design.md) · [任务](tasks.md) · [威胁模型](threat-model.md) · [协议](protocol.md) · [研究来源](references.md) · [实际迭代](iterations.md)

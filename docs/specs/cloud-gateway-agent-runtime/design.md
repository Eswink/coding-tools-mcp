# 设计文档：cloud-gateway-agent-runtime

## 概述

目标是 Level C（机器级解耦），不是再要求本机 daemon 永远在线。第一批选择与生产无连接的协议实验室，验证错误分类和暴露面，避免大范围迁移同时掩盖问题。

## 技术方案

```text
ChatGPT -- HTTPS --> Cloud Gateway / OAuth -- authenticated outbound WSS --> Local Agent
                         |                                     |
                    minimal database                    local grant + execution gate
                                                               |
                                                   tools / processes / files
                                                               ^
                                                         desktop local IPC
```

生产候选技术为 Rust/Axum + PostgreSQL + 单 VPS TLS reverse proxy；版本/依赖在生产实现前锁定。Node 标准库实验室不是生产技术栈替换，也不会被打进 Tauri 包。初版每个工作区有独立 opaque Connector 路由；不接受模型指定任意目标主机或本地绝对目录。

## 数据与权力归属

| 数据/权力 | 云端 | 本地 |
|---|---|---|
| OAuth client/refresh families/issuer | 生产权威，独立于 Agent | 不接受云 OAuth token 直接授予工具权 |
| Conversation grant | 最小投影、revocation epoch | 显式用户审批、设备持有的授权证明 |
| Workspace | opaque ID、协议目录版本 | 路径、文件、cwd、进程、任务日志 |
| Presence | 短期 online/suspect/offline lease | 当前连接 generation + execution state |
| 审批 | 只有经过双端校验的记录可转发 | 用户本人通过受限 IPC 决定 |
| 执行票据 | 短期、绑定请求和权限的路由凭据 | 必须再核对本地 grant/epoch/deadline/参数摘要 |

Cloud Gateway 可以看到转发 payload。TLS 不是让网关无法读取数据的端到端加密；默认不记录/持久化不等于云端看不到。MVP 不提供网关完全恶意时的端到端用户意图证明；网关失陷仍可能冒用现有有效授权，必须明确该信任边界。

## 设计决策

- ADR-001：云端终止 MCP 与 OAuth，不用 Nginx 502 fallback 伪造离线工具结果。目录、协议元数据与验证不依赖本地进程。
- ADR-002：OAuth principal -> conversation -> recovery/exclusive/grant/scope -> availability -> local admission。Foreign chat 只获得非披露权限结果。
- ADR-003：本地暂停原子阻止新 admission；已运行任务不是暂停后自动取消。UI 离开、Agent 断线、机器重启各有明确策略；重连默认保持/进入 Offline，不能自动增加授权。
- ADR-004：不承诺分布式 exactly-once。持久化 request ID+参数摘要+结果索引用于去重；无法确认执行是否开始/完成时返回 OUTCOME_UNKNOWN，要求原 ID 查询/人工核对，禁止新 ID 自动重放。
- ADR-005：Agent 断线时禁止把后续 mutation 排队。短暂连接的陈旧关闭事件不能删除新 generation 的在线连接。确认未知旧任务仍在运行前，不允许新 owner 接管。
- ADR-006：local policy 是安全上限；仓库 AGENTS.md/Skills/Hook、云票据和 LLM 文本不能提高权限。Hooks 也必须通过相同执行策略和沙箱。
- ADR-007：令牌到期/撤销仍需正确认证；不能保证 ChatGPT 不因真正认证失败或云端故障显示重连。
- ADR-008：初批只复现协议与本地 authority 的 fixture，不伪装 OAuth/enrollment。实验只绑定 `127.0.0.1`，拒绝 foreign Host/Origin，不访问磁盘、启动程序、接出站设备或改变生产参数。

## 状态模型

ControlPlane = available/degraded/unavailable；Agent = online/suspect/offline；Execution = online/offline/recovery_required；Grant = unauthorized/pending/active/expired/revoked；Owner = free/reserved/active/draining。

Agent 的 presence 不是新 grant，grant 不是进程仍活着的证明，断线不是任务已取消的证明。生产 admission 必须同时约束 cloud/device generation、grant epoch 和 request deadline。网络重连不会自动续期 chat lease。

## 文件结构与当前影响

- 新增：`prototypes/cloud-gateway/{protocol,state,gateway,cli}.mjs`，测试 `tests/cloud-gateway/*.test.mjs`，独立 CI。
- 本批不改：`src-tauri/src/mcp/server.rs:13-78`、`src-tauri/src/mcp/listener.rs`、`src-tauri/src/tools/聊天运行域v1.rs:94-134`、OAuth store、Tauri 前端。
- GitNexus：handle_request LOW；intercept HIGH（调用链经过 call_tool）。因此 extraction 留到专门后续 PR。

## 迁移与回滚

新 route 与旧 Connector 并行验证；切流前核对 issuer/resource/audience/client registration/refresh 存储和签名密钥，不因 URL 一样就宣称 token 连续。无法安全迁移时允许一次明确重授权。没有用户确认的部署目标、域名与安全秘密交付通道，不写 DNS、不替换线上服务。

本批回滚只删除新增实验/文档/CI，不删除原有 OAuth、grant、历史和任务。生产回滚必须阻止两个可写执行平面同时生效，检查数据库 schema 向后兼容与 revoke epoch，恢复备份后默认执行受阻直到本地再次核对。

## 失败与验收

任何 UI 卡片只能作为现象；必须结合 OAuth/MCP/设备请求分类判断原因。工程实验通过 != VPS 上线 != HOST_VALIDATED。真实试验包含 Agent offline 时 access token 自然过期并 refresh、共享账号陌生 chat、本机休眠/重启与网关重启；保留失败证据。

## 对应需求

FR-1/FR-2 由独立 MCP adapter 与稳定目录覆盖；FR-3 由权限优先/错误分类覆盖；FR-4/FR-5 由双端授权、设备通道和请求 fence 覆盖；FR-6/FR-7 由本地工具核心及 OS 执行上限覆盖；FR-8/FR-9 由迁移恢复和双平台真实验收覆盖。

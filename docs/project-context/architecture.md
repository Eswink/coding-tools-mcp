# 架构设计

> 描述[索引](../project-context.md)基线中已存在的源码结构，不表示所有平台或交付门槛已完成。

## 当前项目结构

```text
coding-tools-mcp/
├── src/                         # SvelteKit 页面、组件、IPC 包装和状态
├── src-tauri/
│   ├── src/
│   │   ├── main.rs / lib.rs     # 桌面入口、Tauri 插件及命令注册
│   │   ├── app_state.rs         # 数据可用性、RuntimeSupervisor、本机控制与 Agent
│   │   ├── commands/            # Tauri IPC、本机审批与配置操作
│   │   ├── data/                # 配置迁移、认证加密与持久记录
│   │   ├── auth/               # OAuth、聊天租约/独占授权、云上下文
│   │   ├── runtime/            # MCP / Actions 生命周期及执行门禁
│   │   ├── mcp/ / actions/     # 协议监听器，共用工具内核
│   │   ├── tools/              # 文件、命令、Git、历史、Hooks、根目录协调等
│   │   ├── cloud_application/  # 桌面拥有的 Agent 生命周期与实时投影
│   │   ├── cloud_connection/   # 云连接配置
│   │   ├── tunnel/ / health/   # FRP / Cloudflare 监督与健康检查
│   │   └── platform/           # 平台相关能力
│   └── tests/                  # 当前 Rust 集成/契约测试
├── services/
│   ├── cloud-gateway/          # PostgreSQL、OAuth、MCP、控制通道及四个二进制入口
│   ├── cloud-agent/            # 出站 Agent、身份、授权投影、领取/重放防护
│   └── local-agent/            # 执行、进程树、PTY 与平台隔离能力
├── deploy/cloud-gateway/       # 部署准备材料，不代表真实 VPS 已验收
├── tests/ / scripts/           # 前端、浏览器、拓扑及交付验证
├── vendor/ / patches/          # 已固定的依赖来源及补丁
├── docs/                      # 规格、台账、上下文与历史图谱
└── old/                       # 历史 Python 参考
```

## 桌面执行链路

```text
src/routes/、src/lib/components/
  → src/lib/api/ 的 Tauri invoke
  → src-tauri/src/commands/ → AppState
      ├─ DataStore：配置、工作区与持久数据
      ├─ RuntimeSupervisor：每个工作区的 MCP / Actions 生命周期
      │   → mcp/ 或 actions/ 监听器 → tools::call_tool → 策略与具体工具
      ├─ 本机审批、云连接与 cloud_application 拥有的 Agent
      └─ tunnel/：外部 frpc / cloudflared 进程
```

`RuntimeSupervisor` 按 `(workspace_id, ServiceKind)` 管理状态，实际阶段为 `Stopped / Starting / Running / Stopping / Error`，同时管理 listener、执行门禁和上下文租约。内嵌 MCP 不依赖旧版 Python server；隧道仍可能使用外部客户端，不能将整个系统描述成不含外部依赖的单二进制。

工具公开列表、profile 和 schemas 位于 `src-tauri/src/tools/registry.rs`；执行入口由 `tools/mod.rs` 导出 `platform_dispatch::call_tool`。云 Agent 另有 `services/cloud-agent/src/catalog/` 和原生适配器 `tools/cloud_host/`；不同 catalog/profile 不应套用旧版“17 个工具”的固定计数。

## 云端与本机边界

`services/cloud-gateway` 提供 `coding-tools-gateway`、`coding-tools-agent`、`coding-tools-control-gateway`、`coding-tools-mcp-gateway` 四个二进制入口；`services/cloud-agent` 同时作为桌面依赖使用。PostgreSQL 持久化、OAuth、设备 enrollment、出站 WSS、签名授权投影和本机最终 admission 是分开的边界。

- OAuth 证明连接身份，不授予工作区操作权；本机审批、当前 owner/scope/epoch、撤销与 drain 仍须成立
- 网关可用或 Agent 已连接，不等于本机已授权，也不允许用重连、刷新或重试重新取得已消耗的执行权
- Actions 与 MCP 共用工具内核，但其认证/曝光规则不能当成同一套权限
- Linux 远程执行隔离有独立实现和验收；Windows 强制隔离仍未完成，拒绝执行不能计作正向隔离通过

详细契约见[云执行桥](../specs/cloud-execution-bridge/README.md)和[RC 台账](../releases/next-rc-ledger.md)。

## 数据与密钥

`data/store.rs` / `data/migrate.rs` 通过 Vault 读写配置。逻辑模块与中文文件名的映射位于 `data/mod.rs`：

- `配置加密v6.rs`：AES-256-GCM 认证加密封装
- `配置文件v6.rs`：加密文件读写边界
- `系统密钥v6.rs`：生产系统凭据提供器，单元测试使用隔离替身

`data/profiles.json` 的文件名不意味着明文存储。生产密钥不可用、认证失败或配置版本不支持时，应保留原文件并拒绝降级；`AppState` 可进入 locked 状态，不能重新创建空配置冒充恢复成功。Linux 原生验证需要实际 D-Bus / Secret Service。

## 未完成边界

快照功能相关目录及 UI 已存在，但 Windows 完整支持和 Issue #86 的 opened-root authority 安全门槛仍未完成。真实主机、VPS、ChatGPT 验收仍 deferred。查看[RC 台账](../releases/next-rc-ledger.md)时应区分历史证据与最终候选证据。

---
*返回索引：[../project-context.md](../project-context.md)*

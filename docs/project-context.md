# Coding Tools MCP - 项目上下文

> 源码核对：2026-09-30，基线 `ee2df5828d68ee24c8378c58d9c88093f1e5d530`。本文是开发导航，不是发布验收结论。

## 项目概览

| 属性 | 值 |
|------|-----|
| 仓库 | Eswink/coding-tools-mcp |
| 桌面源码版本 | `0.6.0-rc.4`（当前源码；下一发布版本须明确选择并核对已有 tag/Release） |
| 语言 | Rust + TypeScript / Svelte；Python 用于部分测试及交付脚本 |
| 框架 | Tauri 2 + Svelte 5 / SvelteKit 2 |
| 类型 | 桌面客户端、内嵌 MCP / Actions 服务、云网关与出站 Agent |
| 描述 | 本机管理工作区、审批与工具执行；云端负责身份、协议入口和连接路由，不替代本机授权 |

Rust/Tauri 工程、前端、共享 Agent 和独立网关服务均已存在，不能再按“工程骨架待创建”理解。桌面版本字段来自 `package.json`、npm 锁文件、桌面 Cargo 清单/锁文件及 Tauri 配置；服务 crate 的内部版本与发行版本区分见[技术栈](./project-context/tech-stack.md)。

## 验收边界

- 当前完整交付范围与证据见[下一 RC 台账](./releases/next-rc-ledger.md)，历史测试只证明对应源码与范围，不能视为当前候选全部通过
- Windows 强制执行隔离与完整快照支持仍未完成；Issue #86 的 opened-root authority（已打开根目录句柄与操作授权绑定）安全门槛仍未解决，详情见 RC 台账
- 真实物理主机、VPS 和真实 ChatGPT 账号验收仍为 deferred，不能用合成浏览器或 CI 结果替代
- `0.6.0-rc.4` 是当前桌面源码版本，不代表已批准新 RC、最终安装包或发布就绪

## 文档导航

- [技术栈](./project-context/tech-stack.md)：实际依赖、工具链和版本来源
- [架构设计](./project-context/architecture.md)：当前模块、执行链路和授权边界
- [如何开发](./project-context/how-to-develop.md)：Plan、开发命令、作用域与版本门禁
- [如何编写测试](./project-context/how-to-test.md)：真实测试入口、夹具和证据边界
- [代码图谱洞察](./graph-insights/latest.md)：仍是 **2026-07-13 历史快照**；其中文件状态、密钥存储和测试结果不是当前结论。编辑符号前应获取新鲜图谱证据，本次未重写该生成文件
- [设计系统](./design-system.md)：设计参考；具体 UI 行为以当前组件、样式和对应规格为准

## 当前规格入口

- [云执行桥](./specs/cloud-execution-bridge/README.md)：Epic #32 / Issue #81 范围、本机授权与集成验收
- [云网关与 Agent](./specs/cloud-gateway-agent-runtime/requirements.md)：身份、通道与服务边界
- [最终 RC 打包门禁](./specs/final-rc-packaging-gate/requirements.md)：最终候选的源码、版本和证据要求
- [原桌面重构规格](./specs/rust-desktop-client/requirements.md)：历史设计背景；当前状态以源码和 RC 台账核对

规格中的历史里程碑或测试计数也需绑定其来源提交，不自动升级为当前验收。

## 旧版参考

`old/` 保留 Python / PySide6 实现、`old/docs/profile-v0.1.md` 和旧合规测试，仅用于行为与迁移参考。当前工具 schema、授权语义和回归入口以 Rust 实现及现行测试为准，不能直接套用旧版工具数量或“71 项全 PASS”作为本分支验收。

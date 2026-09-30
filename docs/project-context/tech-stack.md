# 技术栈

> 与[索引](../project-context.md)的源码基线一致；以下是已存在的依赖和工具，不是计划清单。

## 基本信息

| 属性 | 当前来源 |
|------|----------|
| 桌面包 | `coding-tools-mcp-desktop`，`0.6.0-rc.4` |
| Rust | edition 2021；当前完整 RC CI 使用 `1.98.1`，未在桌面清单声明 `rust-version`，不宣称 `1.77+` 已验证 |
| 前端 | Svelte 5、SvelteKit 2、TypeScript 5.6、Vite 6、Tailwind CSS 4 |
| 桌面壳 | Tauri 2，dialog / notification 插件 |
| CI 基础 | Node.js 22、npm、Python 3.12；见 `.github/workflows/dot-rc-integration.yml` |

桌面六个版本字段应一致：`package.json:version`、`package-lock.json:version`、`package-lock.json:packages[""].version`、`src-tauri/Cargo.toml:package.version`、桌面 `Cargo.lock` 中本项目包版本、`src-tauri/tauri.conf.json:version`。

`services/cloud-agent`、`services/cloud-gateway`、`services/local-agent` 各自有 Cargo 清单和锁文件，当前内部 crate 版本为 `0.1.0`。这些值不等于桌面发行版本；最终产品版本须明确选择并完成对齐，不能仅凭桌面六字段一致就宣称产品版本已统一。

## 实际核心依赖

| 类别 | 技术与位置 | 用途 |
|------|------------|------|
| 异步 / HTTP | `tokio`、`axum`、`tower-http` | 桌面监听器及网关服务 |
| MCP 协议 | `src-tauri/src/mcp/`、`services/cloud-gateway/src/mcp/` | 仓库自己的协议处理实现；当前清单没有 `rmcp` |
| Git | 桌面 `git2 = 0.21.0` | 仓库和受管 worktree 操作 |
| 配置保护 | `keyring = 3.6.3`、`ring`、`zeroize` | 系统凭据保存密钥，认证加密保护磁盘配置；Linux 还使用 D-Bus / Secret Service |
| HTTP / WSS 客户端 | `reqwest`、`tokio-tungstenite`、`rustls` | 出站通信和 TLS；具体 feature 以各清单/锁文件为准 |
| 云端持久化 | `sqlx` + PostgreSQL | 身份、授权投影及持久状态；迁移位于 `services/cloud-gateway/migrations/` |
| 序列化 | `serde`、`serde_json` | 配置和协议数据 |
| UI | `@tauri-apps/api`、`@lucide/svelte` | IPC 与图标 |

桌面通过 `[patch.crates-io]` 使用 `vendor/glib-0.18.5` 的精确上游安全修复回移；来源核验与原始 RustSec 报告应保留。该补丁或某次审计通过不意味着全部依赖已无风险。

## 开发与测试工具

| 用途 | 当前入口 |
|------|----------|
| 前端安装 | `npm ci`；CI 使用 `package-lock.json`，仓库亦保留 `pnpm-lock.yaml` |
| 开发 / 构建 | `npm run desktop` / `npm run desktop:build`；`npm run dev` 仅启动 Vite |
| 前端静态检查 | `npm run check`（SvelteKit sync + svelte-check） |
| 前端回归 | `node scripts/前端完整回归v4.mjs`（编译夹具并调用 Node 内置测试运行器） |
| Rust | Cargo、rustfmt、Clippy；各 crate 分别使用其 manifest |
| 浏览器 / 原生 / 交付验证 | Python 驱动、Playwright、平台原生工具及 GitHub Actions |

当前 `package.json` 没有 Vitest、ESLint、Prettier 或 `npm test` 入口；不要把计划工具当成已配置工具。精确依赖版本以相应锁文件为准，测试前提见[如何编写测试](./how-to-test.md)。

---
*返回索引：[../project-context.md](../project-context.md)*

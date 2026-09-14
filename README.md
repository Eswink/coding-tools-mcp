<p align="center">
  <img src="src-tauri/icons/128x128.png" width="80" alt="Coding Tools MCP">
</p>

<h1 align="center">Coding Tools MCP · Eswink</h1>

<p align="center">为 ChatGPT 网页开发会话提供本地工作区、独占授权、长期任务和可恢复的开发记录。</p>

<p align="center">
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest"><img src="https://img.shields.io/github/v/release/Eswink/coding-tools-mcp?label=Release" alt="本仓库正式版本"></a>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420" alt="Ubuntu amd64">
</p>

<p align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.5.0">v0.5.0 下载</a> · <a href="docs/releases/stable-v0.5.0.md">发行说明与验收边界</a></p>

这是 **Eswink/coding-tools-mcp** 维护的桌面客户端，基于 Rust、Tauri 2、Svelte 5 / SvelteKit。它将你选定的本地项目接入 MCP：获得权限的 AI 会话可以读取文件、应用补丁、执行命令、查看任务与日志，并保存开发检查点。

本分支重点面向**个人使用 ChatGPT 持续开发**：OAuth 只证明连接身份；具体聊天还必须在本机核对指纹并批准。默认一个工作区只允许一个聊天拥有操作权限，其他聊天不能抢占，也不会产生新的待审批通知。

## 下载与安装

当前交付版本：**v0.5.0**。正式 Release 状态及 Latest 以[本仓库 Releases](https://github.com/Eswink/coding-tools-mcp/releases/latest)为准；本版本从已验收的原包晋级，不重新生成安装包。

| 平台 | 安装包 | 说明 |
| --- | --- | --- |
| Windows x64 | [MCP_0.5.0_x64-setup.exe](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_x64-setup.exe) | NSIS 安装程序；未商业签名，可能显示未知发布者 |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.5.0_amd64.deb](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_amd64.deb) | 优先推荐；使用已登录的普通桌面用户 |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.5.0_amd64.AppImage](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_amd64.AppImage) | 自动验收覆盖 extract-and-run，不等于所有 FUSE/Wayland 环境均已验证 |

校验文件：[SHA256SUMS_v0.5.0.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/SHA256SUMS_v0.5.0.txt)。本次发行不提供经过本分支验收的 macOS、ARM 或无桌面 Linux Server 安装包。

Ubuntu 下载 DEB 后，在文件所在目录执行：

```bash
sudo apt install ./MCP_0.5.0_amd64.deb
```

安装系统包需要管理员权限，但**不要使用 sudo 启动桌面应用**。Linux 密钥恢复需要当前桌面会话的 D-Bus 与可用、已解锁的 Secret Service。AppImage 可参考原包说明使用 `--appimage-extract-and-run`；不要通过关闭沙箱解决启动问题。

**更新来源提醒：v0.5.0 二进制内置的“检查更新”仍沿用上游仓库地址。升级本分支请使用上面的 Eswink Release 链接，不要将上游提示的版本当成本分支更新。** 修改 README 或 Release 类型不会改变已编译的更新地址。[源码位置](src-tauri/src/update/mod.rs)

## v0.5.0 带来了什么

五个页面统一为深蓝侧栏、分区卡片和清晰的状态层级，支持浅色、深色、跟随系统主题，并保留原有路由：

| 页面 | 实际用途 |
| --- | --- |
| 工作区 | 工作区信息、ChatGPT 启动提示词、聊天审批、MCP / Actions 切换、配置、任务、日志和健康检查 |
| 通用设置 | 主题、应用信息、已有代理与界面维护设置 |
| 共享密钥 | 按真实凭据类型进行遮蔽、查看、复制、重新生成与保存；部分读取失败时对应字段禁止操作 |
| FRP 配置 | 管理 FRP 服务器配置；具体工作区隧道仍在工作区内管理 |
| 软件管理 | 管理实际支持的软件及安装路径，不虚构运行版本、延迟或健康状态 |

同时修复了保存/还原表单后仍出现离开提示、异步确认晚到时错误切换、密钥部分读取失败的绑定问题，以及审批框键盘焦点边界。设计参考中的语言、自启动、提示音、额外软件矩阵等未实现功能没有变成假开关。

实际页面与安装后截图保存在 [UI-evidence_v0.5.0.zip](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/UI-evidence_v0.5.0.zip)。截图使用隔离验收工作区和合成数据，不代表你的实际服务状态。

## 从零接入一个聊天

### 1. 准备工作区和公网入口

安装并启动桌面端，点击“添加工作区”选择项目目录。在工作区中配置 MCP 端口与 **OAuth**，保存后启动服务。本地地址通常形如 `http://127.0.0.1:28766/mcp`，以界面实际端口为准。

本仓库的常用接入方式是公网 HTTPS `/mcp`。可使用 FRP、Cloudflare 隧道，或已有反向代理。软件管理负责识别/安装支持的隧道客户端；FRP 服务器参数在 FRP 配置页管理。不要把 `127.0.0.1` 当成 ChatGPT 云端能直接访问的公网入口。

使用 Nginx 等代理时，除 `/mcp` 外，以下路径必须到达**同一工作区上游**，不能被静态目录或证书验证规则截走：

```text
/.well-known/oauth-authorization-server
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
/oauth/authorize
/oauth/token
```

先执行桌面健康检查。发现文档应返回 JSON；未经认证的 MCP 业务请求仍应要求认证。不要为了消除 OAuth 错误而关闭认证，也不要删除 ACME 证书验证配置。

### 2. 在 ChatGPT 创建 MCP 连接

使用你账户当前提供的开发者模式/自定义 MCP 应用入口；资格、权限和菜单以 [OpenAI 当前说明](https://help.openai.com/en/articles/12584461)为准。以下是**本仓库服务端**的配置契约，不依赖旧版菜单截图。

假定公网 origin 为 `https://mcp.example.com`：

| 配置项 | 值 |
| --- | --- |
| 服务器 URL | `https://mcp.example.com/mcp` |
| 身份验证 | OAuth；使用预配置的 Client ID / Client Secret |
| Client ID / Client Secret | 必须与对应工作区桌面端配置完全一致 |
| 令牌端点认证方式 | 有 Client Secret 时可选 `client_secret_post`，也支持 `client_secret_basic` |
| 授权端点 | `https://mcp.example.com/oauth/authorize`，通常由发现文档填入 |
| Token 端点 | `https://mcp.example.com/oauth/token` |
| Issuer / 授权服务器基础 | `https://mcp.example.com` |
| Resource / 资源 | `https://mcp.example.com/mcp` |
| 作用域 | `mcp`；需要刷新令牌时请求 **`mcp offline_access`** |
| 注册 URL | 留空；本实现不提供动态客户端注册接口 |
| OIDC | 关闭；不要添加 `openid profile email` |

默认作用域可留空，将所需作用域放在基础范围中，最终请求以服务端发现和实际客户端为准。**Callback / Redirect URL 必须将 ChatGPT 页面显示的精确地址登记到工作区 OAuth 配置，不能猜测或只匹配域名。** 首次网页授权的口令按桌面端提示输入，不要发送给聊天模型。

### 3. 在本机批准这个聊天

连接成功不等于可以操作电脑。在使用插件的聊天里先检查 `auth_status`；需要授权时调用 `request_chat_authorization`，申请本次任务必需的 scopes，并显示返回的会话指纹。

切回桌面端，打开审批入口/对应工作区的“ChatGPT 聊天授权”，**核对指纹、检查权限，再批准**。审批窗口和全局待审批入口可用；系统通知是否出现还取决于操作系统设置。待审批请求 90 秒过期。模型不能通过 MCP 给自己批准权限。

获准后，再调用 `server_info`、`get_default_cwd`、`git_status` 等业务工具。完整流程为：

```text
OAuth 连接 → 当前聊天申请 → 本机核对指纹并批准 → 工具访问 → 保存检查点
```

## 独占会话与长期开发

默认独占按**工作区/profile**生效，不是全应用只能打开一个工作区。第一个合法申请获得临时保留；本机批准后成为 Owner。同一工作区的其他聊天收到 `EXCLUSIVE_CHAT_LOCKED`，不创建新的 Pending，也不能自动踢掉 Owner。

释放或租约到期后，如果旧聊天仍有未结束任务，工作区先进入 **draining（排空）**。确认旧任务结束前不转交独占权。其他聊天仍可能在 ChatGPT 菜单中看到插件；服务端能拒绝调用，但不能替 Host 隐藏菜单。

工作区“远程会话安全”可以调整：

| 设置 | 默认值 | 允许范围 |
| --- | --- | --- |
| 独占聊天 | 开启 | 按工作区配置 |
| 待审批时限 | 90 秒 | 固定 |
| Access Token 有效期 | 60 分钟 | 5～480 分钟 |
| Refresh Session 有效期 | 30 天 | 1～90 天 |
| 聊天授权租约 | 24 小时 | 1～720 小时 |
| 空闲自动释放 | 关闭（0） | 0 或 30～1440 分钟，且不超过租约 |

刷新令牌强制轮换并检测旧令牌重放。**客户端决定何时刷新；刷新不会续期聊天租约、转移 Owner 或替代本机批准。** 修改策略需要本机确认，会撤销当前聊天授权并按配置流程重启监听；既有刷新会话不被自动延长。应用完整重启后也需重新批准聊天。单个命令的超时/任务预算与聊天租约是不同限制。

源码依据：[会话策略](src-tauri/src/auth/session_policy.rs)、[独占授权](src-tauri/src/auth/聊天授权v1.rs)、[远程会话设置](src/lib/components/RemoteSessionSettings.svelte)。

## 历史会话：恢复进度，不跨聊天串档

授权后，复制工作区里的“ChatGPT 新会话启动提示词”。`history_session_bootstrap` 保存逐字 `initial_user_input` 并返回 `session_key`、`current_path` 和有界状态；需要细节时，用 `history_session_search` 定位，再用 `history_session_read` 按 `next_cursor` 分页读取。每轮完成后调用 `history_session_checkpoint`，原样传回稳定目标及逐字 `raw_user_input`；只有返回成功且目标一致才算保存。

归档位于项目的 `docs/history-session/`。当前平台聊天身份参与隔离：**同一聊天可以恢复自身记录，新聊天不会因为指向同一目录就自动继承另一个聊天的归档或授权。** 跨聊天交接应由本机操作者明确安排。服务端也不能读取未通过工具参数提交的聊天内容。[提示词实现](src/lib/components/ChatGptSessionPrompt.svelte)

## 功能与安全边界

文件读取/搜索/补丁、命令执行、Git、任务管理、日志、健康检查复用内嵌工具运行时。异步任务应通过返回的任务 ID 查询输出和状态，不能因为聊天租约长就假定进程永远运行。

Actions 仍是单独的 OpenAPI 网关：启动 Actions 服务、使用其实际 `/openapi.json` 与认证配置。**不要将 Actions、MCP OAuth scope 和本机聊天 scopes 当成同一授权体系**；依赖 ChatGPT 会话 metadata 的隔离不能被任意 REST 客户端自动复用。

本系统操作真实目录、进程及当前系统账户可访问的资源。会话绑定与审批是逻辑授权边界，**不是每个聊天独立的容器、文件系统或可信 Host 身份证明**；同一目录的修改仍真实共享。只授予必要权限，不在日志、截图、README、Issue 或对话中放入 Client Secret、授权口令、访问/刷新令牌或未脱敏配置。

## 升级、恢复与已知限制

升级前退出旧程序并备份配置及对应系统账户的密钥恢复材料。不要删除项目/归档来升级 UI，不要同时启动两个版本写入同一配置，也不要强行解除尚未完成的任务排空。加密配置文件本身不保证能跨系统用户恢复；回退使用保留的 v0.4.0 与兼容备份。

v0.5.0 的自动验收覆盖 Windows NSIS 和 Ubuntu 两系统 × 两种包：每组 20 张原生 UI 截图、12 个授权/刷新/排空阶段；Windows 432、Ubuntu 417 项 Rust 测试及各 180 项前端测试通过。实际构建的浏览器测试另含 40 张页面矩阵截图、10 项交互和 8 种状态；其模拟 IPC 不算原生验收。

**正式 Release 是本仓库的发行渠道选择，不意味着消除了所有验证边界。** 真实 ChatGPT 账号长期自动刷新、OS 通知横幅、所有硬件/FUSE/Wayland 场景仍未全部实测；Windows 包未商业签名。原构建工作流在公开附件后的标签查询发生 404，整体失败记录保留；后续只读核验已确认公开文件正确。详见[本版发行与验收说明](docs/releases/stable-v0.5.0.md)。原包中的 Pre-release 字样是晋级前构建记录，不通过替换附件“改写历史”。

## 本地开发与验证

先阅读 [AGENTS.md](AGENTS.md)。使用 Node.js 22、npm、Rust stable 和对应系统的 [Tauri 2 构建前提](https://v2.tauri.app/start/prerequisites/)。

```bash
git clone https://github.com/Eswink/coding-tools-mcp.git
cd coding-tools-mcp
npm ci
npm run desktop
```

Windows 也可使用 `dev-desktop.cmd`。`npm run dev` 只启动 Vite，并非完整 Tauri 桌面应用。仓库完整前端驱动会准备必要的测试编译产物，不应以没有前置编译的裸测试命令替代：

```bash
npm run check
npm run build
node scripts/前端完整回归v4.mjs
cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo rustc --locked --lib --manifest-path src-tauri/Cargo.toml -- -D warnings
python scripts/release_preflight.py
```

| 路径 | 内容 |
| --- | --- |
| `src/routes/`、`src/lib/components/`、`src/lib/styles/` | 页面、组件和界面样式 |
| `src/lib/api/` | Tauri IPC 包装 |
| `src-tauri/src/auth/` | OAuth、独占租约、本机授权与刷新会话 |
| `src-tauri/src/tools/` | 文件、补丁、命令、Git、任务与历史工具 |
| `src-tauri/src/mcp/`、`src-tauri/src/actions/` | MCP 与 OpenAPI 入口 |
| `src-tauri/src/tunnel/` | FRP / Cloudflare 隧道 |
| `tests/`、`src-tauri/tests/`、`scripts/` | 前端、Rust、原生验收与发行校验 |
| `docs/specs/ui-refactor-v1/` | 本次 UI 计划、迭代与发行记录 |

## 来源与许可

本仓库基于 [mybolide/coding-tools-mcp](https://github.com/mybolide/coding-tools-mcp) 演进，保留原作者与贡献者的归属。两者的版本、安装包与发布渠道不可混用。本项目包元数据声明 Apache-2.0；依赖按各自许可分发，原有归属与许可声明不因本次文档整理而改变。

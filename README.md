<p align="center">
  <img src="src-tauri/icons/128x128.png" width="80" alt="Coding Tools MCP">
</p>

<h1 align="center">Coding Tools MCP · Eswink</h1>

<p align="center">为 ChatGPT 网页开发会话提供本地工作区、独占授权、长期任务和可恢复的开发记录。</p>

<p align="center">
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest"><img src="https://img.shields.io/github/v/release/Eswink/coding-tools-mcp?label=Release" alt="本仓库正式版本"></a>
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0"><img src="https://img.shields.io/badge/Stable-v0.7.0-2ea44f" alt="正式版 v0.7.0"></a>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420" alt="Ubuntu amd64">
</p>

<p align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0">v0.7.0 正式版（Latest）</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases">全部 Releases</a></p>

这是 **Eswink/coding-tools-mcp** 维护的桌面客户端，基于 Rust、Tauri 2、Svelte 5 / SvelteKit。它将你选定的本地项目接入 MCP：获得权限的 AI 会话可以读取文件、应用补丁、执行命令、查看任务与日志，并保存开发检查点。

本分支重点面向**个人使用 ChatGPT 持续开发**：OAuth 只证明连接身份；具体聊天还必须在本机核对指纹并批准。默认一个工作区只允许一个聊天拥有操作权限，其他聊天不能抢占，也不会产生新的待审批通知。

## 下载与安装

> **当前正式版：v0.7.0（Latest）**，取代 v0.6.0 以及 0.7.0 的预发布版 rc.1 / rc.2 / rc.3。下载入口：[v0.7.0 Release](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0)（或 [releases/latest](https://github.com/Eswink/coding-tools-mcp/releases/latest)）。升级说明、回退行为与完整已知问题以该 Release 的发行说明为准。

### 桌面端：v0.7.0

| 平台 | 安装包 | SHA256 | 说明 |
| --- | --- | --- | --- |
| Windows x64 | [MCP_0.7.0_x64-setup.exe](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_x64-setup.exe) | `8fa1bc2fcd2fd3a2f81ea7e2de606d4b083e8acc412e5964af38e9f4bdf148e6` | 按用户安装的 NSIS 安装程序；**未签名**，会显示未知发布者 |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0_amd64.deb](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_amd64.deb) | `64341529d69d89204757eea34ea0c6d6ab2097807acad64eebecd26756ed2197` | 优先推荐；使用已登录的普通桌面用户 |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0_amd64.AppImage](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_amd64.AppImage) | `34793babb5eb485d74676ff697263fa31dae0d714f7dfbeb12e2885fb970e7db` | 不等于所有 FUSE/Wayland 环境均已验证 |

校验文件：[SHA256SUMS.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS.txt)（同时覆盖 `cloud-linux-amd64.tar.gz`）。构建来源：tag `v0.7.0`（源码 `36e0c265`），所有二进制均来自打包 run [40814802175](https://github.com/Eswink/coding-tools-mcp/actions/runs/40814802175)，未在本地构建。Linux 包在 Ubuntu 22.04 上构建，并在 Ubuntu 22.04 与 24.04 上通过安装验收；Windows NSIS 通过标准用户安装验收。本次不提供 macOS、ARM 或无桌面 Linux Server 安装包。

**已知问题（摘要）：** Windows 安装包未签名；不提供 macOS 安装包；与 rc.2 / rc.3 相同的 CI 基线失败、仅开发依赖的 deepmerge 告警豁免（2026-11-30 UTC 到期）等，详见 [v0.7.0 发行说明](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0)。

### 云端组件：v0.7.0

| 文件 | SHA256 | 说明 |
| --- | --- | --- |
| [cloud-linux-amd64.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/cloud-linux-amd64.tar.gz) | `137cfa80b5d601b5ff18341d49a59c5968e8459d126dfa2aefb0c9adcc445f7b` | Linux amd64 云端二进制包（gateway / control-gateway / mcp-gateway / agent），附 [archive-receipt.json](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/archive-receipt.json) 与 [versions.json](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/versions.json) |
| [coding-tools-gateway-image-0.7.0.tar](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-image-0.7.0.tar) | `04d4c59ab88a33aeb2dcafe6162debe18c9f344a4a0d789e91602fafc8847fee` | CI 构建的网关运行时镜像（OCI 归档，无 tag），校验文件 [coding-tools-gateway-image-0.7.0.tar.sha256](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-image-0.7.0.tar.sha256) |

云端二进制包用 [SHA256SUMS-cloud.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS-cloud.txt) 校验。镜像标签：`org.opencontainers.image.version=0.7.0`、`org.opencontainers.image.revision=36e0c265a2bb5f93fe61a504468bf584706519e2`。

### 云网关 Docker 部署：v0.7.0

| 文件 | SHA256 |
| --- | --- |
| [coding-tools-gateway-docker-kit-36e0c265.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-docker-kit-36e0c265.tar.gz) | `4cb586324fa27db03ec2f3c869f991555b38a7d24a9bfb89d313b8329bba4867` |

校验文件：[SHA256SUMS-docker-kit.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS-docker-kit.txt)。部署包是 tag 提交上 [deploy/cloud-gateway/docker](deploy/cloud-gateway/docker/README.md) 目录的确定性 `git archive`，复现命令见发行说明。镜像导入后**按镜像 ID 引用**，不要按 tag 引用：

```bash
sha256sum -c coding-tools-gateway-image-0.7.0.tar.sha256
sha256sum -c SHA256SUMS-docker-kit.txt
docker load -i coding-tools-gateway-image-0.7.0.tar
docker image inspect --format '{{.Id}}' sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b
# .env 中写入：CTM_GATEWAY_IMAGE=sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b
```

- 镜像 ID **必须是** `sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b`。`CTM_POSTGRES_IMAGE` / `CTM_INGRESS_IMAGE` 按 `@sha256:` digest 固定，**不要用 `latest` 或任何可变 tag**。
- **部署顺序固定：初始化 → 桌面端设备登记 → `up -d`。**
  1. `ctm_docker.py setup`
  2. `invite-device` → 桌面端 `prove-enrollment` → `redeem-device` → `select-device`（至少一次；没有已登记并选定的设备时，网关以 `provisioning_not_ready` 拒绝启动）
  3. `docker compose up -d` + `ctm_docker.py check`
- 细节见部署包内的 [README](deploy/cloud-gateway/docker/README.md)。

### 从 v0.6.0 升级

- **Windows**：运行 `MCP_0.7.0_x64-setup.exe`（按用户安装，未签名，SmartScreen 可能提示；先核对 SHA256），可直接覆盖安装 v0.6.0 或任一 0.7.0 RC。
- **Linux**：`sudo apt install ./MCP_0.7.0_amd64.deb` 原地升级；或替换 AppImage 后 `chmod +x`。
- **云网关**：导入新镜像，把 `.env` 中的 `CTM_GATEWAY_IMAGE` 改为上面的镜像 ID，然后 `docker compose up -d` 并运行 `ctm_docker.py check`。桌面端与网关应一起升级。
- 桌面端“设置 → 常规 → 检查更新”现在会报告 v0.7.0。
- **回退行为**：桌面端**没有自动更新**，“检查更新”只是手动读取 GitHub `releases/latest` 并弹窗/打开 Release 页面，不会自动下载或安装。若 Latest 切回 v0.6.0，已安装 0.7.0 的用户会看到“当前已是最新版本”并停留在 0.7.0（不提示降级，也不会自动降级）；修复会以 0.7.1 或更高版本发布。

### 历史版本

- **v0.6.0**（上一个稳定版）：[v0.6.0 Release](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.6.0)（附件为 `MCP_0.6.0-rc.4_*` 安装包及 `SHA256SUMS_v0.6.0.txt`、`Verification_v0.6.0.md`）。
- **v0.7.0-rc.1 / rc.2 / rc.3**（历史预发布）：已被 v0.7.0 取代，仅作历史记录，不再推荐安装；见[本仓库 Releases](https://github.com/Eswink/coding-tools-mcp/releases)。
- **gateway-v0.1.0-rc.1**（历史预发布）：只含 VPS 部署包（`kit.py`、RUNBOOK、模板、渲染脚本与接入说明），不含网关二进制或镜像；见 [gateway-v0.1.0-rc.1](https://github.com/Eswink/coding-tools-mcp/releases/tag/gateway-v0.1.0-rc.1)。

### 校验 SHA256

Linux（下载文件与 `SHA256SUMS.txt` 放在同一目录）：

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

Windows PowerShell：

```powershell
Get-FileHash .\MCP_0.7.0_x64-setup.exe -Algorithm SHA256
```

输出必须与上表 / `SHA256SUMS.txt` 完全一致，不一致请勿安装。

### 安装

- **Windows**：运行 `MCP_0.7.0_x64-setup.exe`。安装包未签名，SmartScreen 可能提示“未知发布者”；请先完成 SHA256 校验再选择继续。
- **Ubuntu DEB**：在文件所在目录执行

  ```bash
  sudo apt install ./MCP_0.7.0_amd64.deb
  ```

- **Ubuntu AppImage**：`chmod +x MCP_0.7.0_amd64.AppImage` 后运行；环境不支持 FUSE 时可使用 `--appimage-extract-and-run`。

安装系统包需要管理员权限，但**不要使用 sudo 启动桌面应用**。Linux 密钥恢复需要当前桌面会话的 D-Bus 与可用、已解锁的 Secret Service。不要通过关闭沙箱解决启动问题。

**更新来源提醒：** v0.6.0 起“检查更新”指向本仓库的 `releases/latest`，**只会看到稳定版，不会提示预发布**。v0.5.0 及更早二进制内置的更新地址仍是上游仓库，请勿将上游提示的版本当成本分支更新。[源码位置](src-tauri/src/update/mod.rs)

## 界面与页面

v0.5.0 起五个页面统一为深蓝侧栏、分区卡片和清晰的状态层级，支持浅色、深色、跟随系统主题，并保留原有路由：

| 页面 | 实际用途 |
| --- | --- |
| 工作区 | 工作区信息、ChatGPT 启动提示词、聊天审批、MCP / Actions 切换、配置、任务、日志和健康检查 |
| 通用设置 | 主题、应用信息、已有代理与界面维护设置 |
| 共享密钥 | 按真实凭据类型进行遮蔽、查看、复制、重新生成与保存；部分读取失败时对应字段禁止操作 |
| FRP 配置 | 管理 FRP 服务器配置；具体工作区隧道仍在工作区内管理 |
| 软件管理 | 管理实际支持的软件及安装路径，不虚构运行版本、延迟或健康状态 |

同时修复了保存/还原表单后仍出现离开提示、异步确认晚到时错误切换、密钥部分读取失败的绑定问题，以及审批框键盘焦点边界。设计参考中的语言、自启动、提示音、额外软件矩阵等未实现功能没有变成假开关。

实际页面与安装后截图保存在 [UI-evidence_v0.5.0.zip](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/UI-evidence_v0.5.0.zip)。截图使用隔离验收工作区和合成数据，不代表你的实际服务状态。

## 从零接入一个聊天（方式一：本机直连）

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

## 方式二：经云网关接入 ChatGPT（未经真实环境端到端测试）

v0.7.0 桌面端在工作区中提供“云连接”面板：从本机文件导入云连接配置 JSON 与本机签名私钥 JSON，桌面端以**出站**连接接入云网关；ChatGPT 连接云网关的 MCP 入口，而不是直接访问你的电脑。

- **部署云网关**：使用 v0.7.0 的网关镜像与 Docker 部署包，按上文“云网关 Docker 部署：v0.7.0”和 [部署包 README](deploy/cloud-gateway/docker/README.md) 执行；前置条件为 Docker Engine ≥ 28 与 Compose v2。VPS 手动部署的 `kit.py` 与 [RUNBOOK](deploy/cloud-gateway/kit/RUNBOOK.md) 也在仓库中。`--domain` 必须填你自己的域名（文档中的域名均为占位符）。
- **授权边界不变**：云端、模型和 OAuth 都不能批准本机权限；连接后仍需在本机核对聊天指纹并批准。暂停、撤销以本机为准。
- **接入 ChatGPT 与桌面端**：连接器 URL、OAuth 端点、`register-client` 预登记和桌面端导入步骤见 [接入说明](deploy/cloud-gateway/CONNECT-CHATGPT-AND-DESKTOP.md)（该文档按 rc.2 手动测试编写，镜像与版本以本页 v0.7.0 为准）。
- **当前状态**：**未在真实 VPS / 真实 ChatGPT 上做端到端测试**，限制见下文“已知限制”。

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

升级前退出旧程序并备份配置及对应系统账户的密钥恢复材料。不要删除项目/归档来升级 UI，不要同时启动两个版本写入同一配置，也不要强行解除尚未完成的任务排空。加密配置文件本身不保证能跨系统用户恢复；回退请使用保留的稳定版安装包与兼容备份。

已知限制：

- **完整已知问题见发行说明**：与 rc.2 / rc.3 相同的 CI 基线失败、仅开发依赖的 deepmerge 告警豁免（2026-11-30 UTC 到期）等，见 [v0.7.0 发行说明](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0)。
- **Windows 安装包未签名**。
- **云网关组合未经端到端测试**：v0.7.0 桌面端 + v0.7.0 网关镜像未在真实 VPS / 真实 ChatGPT 上测过，只通过了 CI 内的测试。
- **网关没有动态客户端注册（DCR）**：客户端需由操作员用 `coding-tools-gateway register-client` 预先登记；ChatGPT 是否接受这种方式**尚未验证**。
- **没有 Windows 版 `coding-tools-agent`**：目前只有 Linux amd64 版。
- **`--domain` 必须由你自己填写**：文档和示例中的域名都是占位符，不能直接使用。
- 真实 ChatGPT 账号长期自动刷新、OS 通知横幅、所有硬件/FUSE/Wayland 场景仍未全部实测；不提供 macOS、ARM 安装包。

历史版本的验收记录见 [v0.5.0 发行与验收说明](docs/releases/stable-v0.5.0.md) 及各 Release 附件。

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

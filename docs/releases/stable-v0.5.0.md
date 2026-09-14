# v0.5.0 — Windows / Ubuntu 正式 Release

本次按维护者明确要求，将已公开并验收的 v0.5.0 晋级为正式 **Release / Latest**，不再使用 Pre-release 作为当前发行类型。正式状态以 [Release 页面](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.5.0)和 `stable-promotion-receipt.json` 为准。

## 不变的发布来源

产品提交：`63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076`。Git tree：`01b11a1088d82501a1e579801ce6ac774ab5d43a`。

Release ID：`388174565`。本次仅改变发行名称、说明、正式版标记及 Latest。三个安装包、四个配套附件、版本标签和原发布分支全部保留原身份及字节。后续 README / 发行工具提交与产品提交分开，不将更新后的 main SHA 冒充安装包源码。

| 系统 | 文件 |
| --- | --- |
| Windows x64 | `MCP_0.5.0_x64-setup.exe` |
| Ubuntu 22.04 / 24.04 amd64 | `MCP_0.5.0_amd64.deb`、`MCP_0.5.0_amd64.AppImage` |

下载位置：[v0.5.0 七个原始附件](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.5.0)。安装和连接步骤见本仓库 [README](https://github.com/Eswink/coding-tools-mcp/blob/main/README.md)。不要使用上游仓库安装包替代本分支版本。

## 界面和交互

五页面统一深蓝侧栏、分区卡片、语义状态及浅色/深色/跟随系统主题；保留已有路由、真实后端能力和原生窗口行为。完善保存后草稿状态、切换时迟到结果保护、密钥部分读取失败的禁用处理及审批框焦点。相对 v0.4.0，产品 Rust、IPC API 包装和依赖图不变；不伪造参考图中尚未实现的设置。

OAuth 与本机聊天批准仍分开。默认按工作区独占、指纹核对、权限缩减、Refresh Token 轮换和重放检测、旧任务排空、90 秒待审批截止及重启后重新批准保持不变。需要刷新令牌时客户端请求 `mcp offline_access`，不启用 OIDC。

## 已有验收与晋级检查

[原构建 34810770540](https://github.com/Eswink/coding-tools-mcp/actions/runs/34810770540) 的十六个源码、构建、安装前置作业通过：Windows 432、Ubuntu 417 项 Rust 测试，两端各 180 项前端；40 张页面矩阵截图、10 项交互、8 种状态；五种安装组合各 20 张原生截图和 12 个原生安全阶段。原生与模拟 IPC 浏览器证据分开记录。

原发布作业在附件已公开后，立即读取标签收到 404，因此原工作流整体仍是 failure。这个失败不会被重写。[只读验证 34812656272](https://github.com/Eswink/coding-tools-mcp/actions/runs/34812656272) 随后成功复算验收并匿名核对七个公开附件。

本次晋级再次使用原源码、原证据及未修改的验收器复算上述门禁，核对原工作流身份和结果，晋级前后匿名下载七个附件并校验 SHA-256。晋级写操作仅限本 Release 的元数据，不执行重新打包、上传、删除或修改 Git ref。晋级后确认 `draft=false`、`prerelease=false`、Latest 指向 v0.5.0。

## 安装、升级与真实边界

Windows 安装前退出旧程序，备份配置及系统账户密钥恢复材料；包未商业签名，可能出现未知发布者提示。Ubuntu 使用普通登录桌面用户和可用、已解锁的 Secret Service，不使用 sudo 启动 GUI。DEB 为优先推荐方式，AppImage 自动验收范围为 extract-and-run。

升级不需要删除工作区或历史。不要同时运行两个版本写同一配置，不要在旧任务未结束时强制释放排空状态。完整重启需重新本机批准聊天。回退使用保留的 v0.4.0 和兼容备份。

**v0.5.0 内置更新检查仍指向上游，请从 Eswink/coding-tools-mcp 的 Release 下载更新。** 本次元数据晋级不改变这个编译期行为。

正式发行不扩大验收证据：真实 ChatGPT 账号长期自动刷新、系统通知横幅、所有硬件/FUSE/Wayland、macOS/ARM/无桌面环境并未全部验证。会话隔离不是逐聊天独立操作系统沙箱。未合并的独立 PR #11 不包含在本版，线上 Nginx 和用户凭据未改动。

原附件 `Verification_v0.5.0.md`、`Release-scope_v0.5.0.json` 中的 Pre-release 字样，是晋级前构建阶段的不可变记录，**只在发行渠道描述上由本说明及当前 Release 状态取代**；其测试、来源和限制仍有效。不能通过覆盖附件消除这个时间差异。

## Stable promotion summary (English)

v0.5.0 is promoted to a full Release and Latest under the maintainer's explicit authorization. The seven existing assets and product source 63261e0 remain unchanged. Documentation/tooling commits are not binary-source revisions. Promotion recomputes original source/UI/native gates, verifies the original failed publication run and its successful prerequisites, and anonymously checks every public asset before and after a metadata-only PATCH. The original pre-release verification attachments remain intact as build-time records. Windows is unsigned; real-account long-duration ChatGPT refresh, OS notification banners and untested graphics/hardware platforms retain their stated limits. The built-in v0.5.0 updater still targets upstream; use this fork's Release links.

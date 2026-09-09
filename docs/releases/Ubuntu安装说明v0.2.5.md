# v0.2.5 · Ubuntu 图形桌面版

新增 Ubuntu x86_64/amd64 图形桌面发行包：DEB（优先）和 AppImage。沿用 Windows 版的工作区、MCP、Actions、固定入口、加密配置和持久异步任务面板，不是一个另起炉灶的命令行工具。

Windows v0.2.4 的用户本机验收已由用户于 2026-09-09 确认；本版不覆盖该 Release、不移动旧标签。v0.2.5 本次仅交付 Ubuntu 安装包，Windows 源码仍执行回归，但不声称已重新构建 Windows v0.2.5 安装包。

## 支持范围与桌面条件

构建基线 Ubuntu 22.04 amd64；发布门禁要求同一安装包分别在 Ubuntu 22.04、24.04 通过安装和原生 GUI 验收。需要已登录的图形桌面、D-Bus 用户会话以及已解锁的 Secret Service 密钥环，Ubuntu Desktop 的 GNOME Keyring 是推荐配置。以普通用户运行，不要 `sudo` 启动应用。

本版不是无桌面的 Ubuntu Server 后台服务；ARM64、Ubuntu 20.04、其他发行版、Ubuntu 26.04 和纯 Wayland 会话不在本轮已验证范围。CI 图形验收使用 X11/Xvfb 和软件渲染，不代表已覆盖所有显卡、桌面扩展或显示服务器组合。测试不会关闭 WebKit 沙箱。

## 安装 DEB（推荐）

在 Release 下载 `MCP_0.2.5_amd64.deb` 和 `SHA256SUMS_v0.2.5.txt`。先进入下载目录，核对所下载文件的 SHA-256，再安装：

```bash
sha256sum MCP_0.2.5_amd64.deb
# 将结果与 SHA256SUMS_v0.2.5.txt 对应行逐字核对。
sudo apt update
sudo apt install ./MCP_0.2.5_amd64.deb
```

安装后从应用菜单搜索 **Coding Tools MCP**，或在终端执行：

```bash
coding-tools-mcp-desktop
```

安装包声明 WebKitGTK/GTK、托盘和 Secret Service 等运行依赖；无需另外安装 Node.js 或 Rust 才能打开界面。执行科研/开发命令时，Python、Git、对应构建工具及工作区环境仍需由使用者自行配置。

卸载包而保留用户配置：

```bash
sudo apt remove coding-tools-mcp-desktop
```

如安装时系统显示的包名不同，以 `dpkg-deb -f MCP_0.2.5_amd64.deb Package` 输出为准。不要手动删除密钥环来“清空配置”。

## 使用 AppImage

下载 `MCP_0.2.5_amd64.AppImage` 并核对摘要：

```bash
sha256sum MCP_0.2.5_amd64.AppImage
chmod +x MCP_0.2.5_amd64.AppImage
./MCP_0.2.5_amd64.AppImage
```

AppImage 也需要图形桌面、D-Bus 和已解锁的 Secret Service；不是完全不依赖系统服务的便携版。缺少这些服务时，先在 Ubuntu Desktop 安装 `gnome-keyring dbus-user-session libayatana-appindicator3-1` 并正常登录桌面。DEB 会由 apt 处理声明依赖，故优先推荐 DEB。

若系统提示缺少 FUSE，可使用运行时提供的解压运行方式，而不是关闭 WebKit 沙箱或以 root 运行：

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./MCP_0.2.5_amd64.AppImage
```

本轮 AppImage 原生 CI 明确使用 **extract-and-run**，不把它等同于已验证全部机器上的 FUSE 挂载模式。AppImage 不自动安装应用菜单入口；需要菜单/卸载集成时使用 DEB。

## 工作区、系统密钥与升级

配置默认位于 `$XDG_CONFIG_HOME/coding-tools-mcp-desktop`，未设置该变量时通常为 `~/.config/coding-tools-mcp-desktop`。任务记录也受系统凭据密钥保护。升级前关闭旧应用，离线备份配置及原系统账户密钥恢复材料；不要将备份、Token、私钥、密钥环文件上传 GitHub 或粘贴到日志。

Windows 加密配置不能简单复制到 Ubuntu 后继续解密；不同账户或丢失密钥环时亦然。请在 Ubuntu 建立工作区并重新配置授权资料。密钥不可用时应保留原文件并排查凭据服务，不能以明文存储或删除旧数据作为自动降级。

图形应用从应用菜单启动时可能不继承 `.bashrc`/Conda/nvm 的 PATH；需要这些工具时，先在正确环境的终端启动应用，或按工作区配置使用可解析的命令路径。不要把 GUI 可以打开等同于所有外部开发工具已经安装。

GNOME 托盘可见性取决于桌面启用的 AppIndicator 支持。本轮验证窗口和业务路径，不声称验证了所有桌面的托盘扩展；未确认托盘可见前，不要依赖“隐藏到托盘”找回窗口。关闭应用时使用应用的退出操作。

## 发布门禁与证据边界

发布只允许已合并的 `main` 精确 SHA；版本、包内元数据、安装后的原生版本和六处项目版本一致才可发布。流程要求 Windows/Linux 完整 Rust、生产零编译警告、原生密钥跨进程回归、前端与发布脚本测试通过；之后检查两个 Ubuntu 版本的 DEB 真实安装载荷、桌面入口、运行库、真实 Tauri/WebKit 窗口、真实 IPC 工作区、实际 MCP/Actions HTTP 异步命令、幂等、取消、任务面板及加密记录重启恢复。

原生验收的工作区由真实 Tauri IPC 建立，任务通过本地服务 HTTP 提交，面板由原生 WebDriver 点击。它没有 mock 后端，也没有给产品插入测试插件，但不覆盖原生文件选择对话框、全部菜单/设置、真实公网 TLS/OAuth/ChatGPT、长期实耗压力或全部显卡环境。既有 12 项浏览器面板 mock 回归仍单独保留，不能代替原生验收。

只有全部门禁通过，才公开 **预发布** Release。附件按顺序上传并核对大小/摘要；公开后再匿名下载复核。`Ubuntu-evidence_v0.2.5.zip` 保存来源、原生结果和截图；公开下载回执另保存在 Actions 工件中。工作流定义不是执行通过证明，结果以实际运行和附件为准。源码未提供商业软件签名，下载时核对 Release 的 SHA-256。

本轮仍须用户在自己的 Ubuntu 桌面完成本机验收；遇到异常保留版本、Ubuntu 版本、显示会话类型、步骤和脱敏日志，切勿提供密钥明文。

## 上游依据

- Tauri Debian：<https://v2.tauri.app/distribute/debian/>
- Tauri AppImage：<https://v2.tauri.app/distribute/appimage/>
- Tauri 原生 WebDriver：<https://v2.tauri.app/develop/tests/webdriver/manual-setup/>
- tauri-driver 固定版本 2.0.6：<https://v2.tauri.app/release/tauri-driver/>

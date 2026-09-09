# Ubuntu修复自审v6：包内GIO模块ABI

## v5真实复审：90分，打回

运行34362067522，source5a7d475c。Ubuntu22.04 DEB/AppImage、Ubuntu24.04 DEB均完成8组原生验收，宿主Python配置及工作区cwd断言通过；24.04 AppImage在侧栏点击时RemoteDisconnected，仅完成1组。Windows/Linux完整基线通过不等于4组合都通过，35/25/20/10=90分打回。原生工件10108524484与10108505151均下载核对摘要及原始JSON。

24.04 AppImage日志同时包含宿主libgiolibproxy加载新libcurl/旧libnghttp2的符号错误，以及宿主libdconfsettings需要新GLib符号g_assertion_message_cmpint失败。实际GTK hook仅设置GIO_EXTRA_MODULES，GLib仍扫描其编译时宿主目录。该ABI混用已证实；旧v2也出现这些警告而曾推进到2组，因此不能将此次WebDriver断连唯一归因为该冲突。修正这条确定错误的加载路径后必须再次真实验收，不通过重试、跳过点击或增大超时掩盖。

## v6最小修复

AppImage入口同时将GIO_MODULE_DIR与GIO_EXTRA_MODULES设置为实际包内usr/lib/x86_64-linux-gnu/gio/modules，阻止宿主新插件链接包内旧GLib。只作用于AppImage进程环境，不修改系统目录；保留专用Python环境、PATH、GTK包装、GUI cwd与工作区命令契约。

包内真正的libgiognutls.so必须存在、路径不逃逸、ELF为Linux amd64，摘要及大小记录到入口来源证明。不是将模块目录指向空目录，不使用dummy TLS backend、不关闭证书验证/沙箱、不清空用户Python环境。GNOME系统代理及任意外部动态链接工具组合不因本测试宣称全认证。

## 先红后绿与实际模块验证

新增3项离线回归覆盖宿主模块目录不能泄入AppImage、Python/PATH仍保留、包内TLS模块缺失/错误架构必须拒绝。先红后绿，总119项本地Python通过。Windows在新增套件仅跳过1项Linux进程入口用例，原有12项Linux专属跳过保留，均不计通过。

从已下载真实AppImage提取的GIO/GLib/GnuTLS模块，在隔离子进程按修正后的路径实际加载：g_tls_backend_get_default返回GTlsBackendGnutls，g_tls_backend_supports_tls为true，stderr为空。这不是原生GUI、HTTPS网络或完整代理验收，只证明没有通过丢弃TLS后端绕过问题。

修改前现有verify图谱impact LOW；修改范围为入口、打包校验、回归和本记录4文件，共享Rust/TS/Svelte和依赖图不变。候选自审38/28/20/10=96仅准入CI。最终准确SHA必须通过4份原生8组、完整基线、同端口20轮、前端/密钥/来源门禁，再合并及main重建发布、匿名下载核验。任何真实失败继续打回。

官方GIO环境语义：https://docs.gtk.org/gio/overview.html 。本次评分均执行者自审，不是独立第三方审批；后续运行和发布状态在PR #4回填，当前不能宣称已发布。

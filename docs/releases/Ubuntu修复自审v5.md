# Ubuntu修复自审v5：WebKit发行版路径

## 实际失败与否证

v3源码d4bdbe24，运行34359406073。Ubuntu24原生工件10107485203的DEB全部8组通过且宿主Python配置保留；AppImage无法建立原生会话，WebKit报找不到相对路径 `././/lib/x86_64-linux-gnu/webkit2gtk-4.1/WebKitNetworkProcess`。包内自定义入口摘要校验通过不等于窗口可启动。v4源码96d16cda仅修复Windows编码，不会消除这个AppImage问题，必须继续打回。本轮将该运行完整复审为83分（30/23/20/10），此前90分只反映当时已发现的Windows编码失败，不掩盖后续原生失败。

曾考虑设置WEBKIT_EXEC_PATH绝对路径；官方ProcessExecutablePathGLib.cpp仅在ENABLE(DEVELOPER_MODE)下读取它，实际包内libwebkit2gtk-4.1.so.0也无该环境变量字符串，故否证该方案，不用无效环境变量“修复”。真实包内库的PKGLIBEXECDIR已由打包器改为相对路径，原通用AppRun会切换到APPDIR/usr；v3保留调用者cwd的假设不兼容这个发行版布局。

## 最小修复

AppImage专用脚本保留PythonHOME/PythonPATH/PATH不变、GTK包装、参数及退出码，但恢复上游AppRun的图形进程cwd=APPDIR/usr；不修改WebKit二进制、系统路径或沙箱。之前v3记录中“GUI cwd保持”的候选设计由本决定替代。工具命令的cwd仍由现有Rust执行引擎显式设置为工作区；在真实MCP/Actions Python模块断言中补充os.getcwd()==隔离工作区，避免图形cwd误传到科研命令。

实际AppImage解包校验增强：WebKitNetworkProcess、WebKitWebProcess和injected-bundle共享库必须存在、未越出包目录、ELF Linux amd64正确；子进程必须可执行。来源记录保存三个文件SHA256/大小及图形cwd契约，任一检查失败阻断上传。没有改变DEB/Windows产品函数、依赖图或原生8组业务断言。

## 回归与自审

新增5项路径/布局回归，先红后绿，覆盖调用者在包外目录、缺失子进程、错误架构、执行权限和三份文件摘要。旧参数/环境测试仍保留，明确把GUI cwd预期修正为上游契约；工作区cwd由更强的原生业务断言证明而非忽略。实际已下载AppImage提取的三份WebKit文件也通过布局检查，不能把这个静态结果说成GUI成功。

本地116项Python回归全部通过，新增5项、既有111项。Windows中既有10项Linux入口用例和新增2项Linux权限/进程用例跳过，跳过不计通过；其他通用门禁仍执行。修改前verify、原生run、旧cwd测试的GitNexus upstream均LOW；FTS离线扩展不可用。自审38/28/20/10=96仅批准CI候选；四份当前SHA原生结果与所有跨平台门禁必须实际通过，才允许合并，合并后同main重建发布再匿名下载校验。

本文件是提交前检查点。逐轮实际结果、自审评分和最终发布回执继续写入PR #4；不是独立第三方审批，不宣称当前已发布。阈值95且无阻断，任一失败继续打回。

来源：官方 https://github.com/WebKit/WebKit/blob/main/Source/WebKit/Shared/glib/ProcessExecutablePathGLib.cpp；真实v3原生日志及从v2真实AppImage提取的WebKit ELF布局。Ubuntu22/24 amd64、X11/Xvfb、AppImage extract-and-run之外的平台/显示/GPU/FUSE组合仍未认证。

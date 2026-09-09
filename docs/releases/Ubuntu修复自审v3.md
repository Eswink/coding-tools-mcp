# Ubuntu修复自审v3：AppImage宿主Python环境

## v2真实运行复审：83分，打回

源码c0a7b5e02664836be8ad60b6a8c03afeffc49233，Ubuntu运行34354987103。严格PR基线34354992756、安全存储34354992824、源码34354992841、来源34354992896均成功；旧预检条件skipped不计通过。Windows/Linux完整Rust、各20轮同端口重启步骤成功。原始d853的两个失败记录保留。

Ubuntu22.04原生工件10105607466与24.04工件10105592428已下载核对ZIP摘要及原始JSON。DEB两平台均完成8组真实GUI/IPC/HTTP/取消/重启验收，原Portal显示错误消失；AppImage两平台均完成2组后失败。实际AppRun.wrapped向宿主Python注入AppDir/usr作为PYTHONHOME，覆盖有效系统Python配置，导致encodings缺失和exit1；不是服务超时、鉴权或导航错误。v2真实复审30/23/20/10=83，存在阻断，禁止合并发布；此前96是进入CI的候选分，不是最终通过。

## v3设计决定

不通过python -E、清空测试环境或删除AppImage门禁掩盖问题。Ubuntu专用配置使用Tauri beforeBundleCommand和useLocalToolsDir，在cargo metadata返回的target/.tauri中安装版本化的专用启动脚本。仅接受已核对CLI2.11.4和Linux amd64；CLI版本、包内包装或入口摘要变化即失败，要求重新审查。不会覆盖用户全局Tauri缓存；正常重复构建从Git源重建入口，旧缓存不是隐藏前提。

保留linuxdeploy生成的GTK hook、APPDIR及GUI/WebKit需要的包内动态库；保留用户动态库路径后缀。专用入口不覆写或清空PYTHONHOME、PYTHONPATH、PATH，不注入Qt/Python通用模板；参数、cwd、退出码保留。不修改共享Rust/TypeScript/Svelte产品函数或依赖图，DEB和Windows不替换运行入口。该修复并不保证所有外部动态链接程序或Conda环境组合，仍以明确原生场景和用户本机验收为边界。

打包后从实际AppImage完整解包，验证AppRun.wrapped与已审查源码逐字节一致、可执行权限及GTK包装仍存在；来源SHA、最终AppImage摘要和入口摘要记录为入口校验v3.json并纳入发布证据。该过程发生在安装包来源生成和上传之前，失败不能继续。

## 回归与自审

- 新增入口/门禁15项本地回归通过，Linux下无跳过；Windows仅跳过10项Linux入口进程专属用例，其余通用门禁仍执行，不将跳过算通过。
- 全部Python离线回归110项通过（15新增、95既有）。入口配置缺失先红后绿。
- 使用从真实v2安装包提取的旧AppRun ELF，和相同临时工作区/真实宿主Python做对照：旧入口exit1并缺encodings，新入口exit0输出host-python-ok。此证据是实际启动器/宿主Python对照，不等于完整GUI验证。
- 覆盖未设置、空字符串及有效自定义PYTHONHOME/PYTHONPATH；原PATH、虚拟环境、Unicode/空格/引号参数、cwd、退出码、缺失载荷、工具目录软链和未审查CLI版本。
- 原生GUI保留全部8组，并额外使用有效宿主Python home和自定义模块路径验证真实MCP/Actions命令；只有成功才置host_python_environment_preserved。发布门禁明确拒绝缺失或false的该证据，不只查看原生报告外层passed。
- 修改前GitNexus：原生run/compose/夹具setUp为LOW，validate_reports为MEDIUM（9直接依赖，均脚本/测试，无产品流程）。FTS离线扩展不可用，不冒充全文图谱审批。

初稿自审发现Cargo metadata的工作目录需与Tauri保持一致，避免相对CARGO_TARGET_DIR错位，94分打回；新增目录回归先红后绿，显式使用src-tauri作为cwd。

本地修订自审38/28/20/10=96，只批准进入真实CI。尚未在此提交前记录中宣布AppImage原生、合并或Release成功。真实运行失败即打回，超过95分也不能绕过门禁；后续结果逐轮追加到PR #4审核记录。自审不是独立第三方评审。

## 上游依据与风险控制

Tauri bundler的linuxdeploy实现从local_tools_directory/.tauri读取AppRun-x86_64；CLI配置useLocalToolsDir将目录绑定cargo target_directory；beforeBundleCommand运行于frontend目录。上述内部接点通过锁定CLI和包内摘要门禁保护，不假设未来版本不变。

- https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle/linux/appimage/linuxdeploy.rs
- https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-cli/src/interface/mod.rs
- https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-cli/src/bundle.rs

未关闭WebKit沙箱、未使用root运行GUI、未输出全部环境或用户配置。仍需两个Ubuntu版本、两种格式完整原生验收与所有候选检查，通过后才合并；最终main SHA重新构建验证再发布，公开后匿名下载校验。ARM64、26.04、无桌面Server、完整FUSE/Wayland/GPU、完整原生文件选择器和公网长期压力不在本轮认证范围。

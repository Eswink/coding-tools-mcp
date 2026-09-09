# Ubuntu修复自审v2

## 范围与判定

目标：修复PR #4的原生GUI及Linux基线，完成Ubuntu22.04/24.04 amd64 DEB/AppImage验收后，由已合并main精确SHA构建发布v0.2.5。保留Windows v0.2.4。基线为d853813ff066906d770825ad251ab9b5b31bed77，源码tree56e665196d8d3ef95d2d47d30c7d3852b5173ef3。

自审按正确性40、回归30、发布来源20、范围控制10评分，95分且无阻断才接受该轮。代码候选评分仅批准进入CI，不批准合并或发布。分数是执行者自审，不是独立第三方审批。任何真实门禁失败均打回，无论分数多少；历史失败不删除。

## 迭代记录

| 轮次 | 发现与证据 | 自审分 | 决定 |
|---|---|---:|---|
| v1首轮复核 | 34348014504原生测试刷新后停首页；Portal激活缺DISPLAY；34348012392 Linux同端口重启bind报AddrInUse。其他成功作业不能覆盖失败。 | 55（20/10/15/10） | 打回 |
| v2本地初稿 | 原生侧栏导航及归档负向回归已修；自审发现重启后任务按钮含状态/耗时，整段文本精确匹配仍会失败。 | 88（33/25/20/10） | 打回，补任务列表内request_id子元素定位及回归 |
| v2修订候选 | 11项新增离线回归与84项既有回归共95项通过；Python语法、Bash与工作流脚本检查通过。保留原生8组及所有业务断言，新增双平台20轮同端口重启回归。 | 96（38/28/20/10） | 接受进入真实CI；原生/跨平台/发布门禁尚未通过，不得合并发布 |

当前文件为提交前检查点，后续真实CI、每轮评分、合并及发布结果须在PR #4评论和最终交付记录追加，不用本表替代实际结果。

## 根因与最小修复

1. 原生测试将IPC创建后的页面刷新误当作工作区选择；截图和失败断言停首页。修复使用真实WebDriver点击侧栏并校验/workspace/id，再执行后续HTTP/IPC测试；应用重启后重新选工作区与正确任务，核验中文日志。离线Mock只测试验收辅助函数，不是原生GUI通过证据。
2. 原会话dbus-run-session包裹xvfb-run，激活服务没有DISPLAY/XAUTHORITY。修复Xvfb先启动、D-Bus后启动，显式传播显示/XDG允许列表；原生测试前检查Portal FileChooser和GTK backend。无沙箱关闭、无root应用、无全环境变量输出。
3. Rust失败在第二次同端口bind。原夹具先探测临时端口再释放，且shadow旧reqwest Client不会立即释放连接池；原日志不能唯一确定竞争socket归属。std非Windows绑定已设置SO_REUSEADDR，不将该选项缺失伪称真因。修复只改测试：生产bind直接占用测试端口，初始夹具有限尝试；旧Client显式drop；同端口重启仍只尝试一次，幂等键、输出和截止断言不变，并验证已占端口必须拒绝。完整并行Rust回归和双平台20次重复提供验证，不盲目重跑失败CI碰绿。
4. 证据ZIP不能依赖下载mtime或附带的候选发布目录。固定ZIP元数据，显式逐文件白名单，禁止软链逃逸和异常大文件；相同输入字节归档稳定，不宣称两次独立编译必然字节一致。
5. DEB实测包名coding-tools-mcp，二进制命令coding-tools-mcp-desktop；修正卸载说明及来源字段文档。

## 门禁和边界

95项为本地Python离线回归，不是Rust或Ubuntu原生测试。容器未安装Rust工具链，原生Ubuntu/Windows及打包必须通过Actions。两个Ubuntu各DEB/AppImage均须完成8组原生测试，任一格式失败仍尝试另一格式留证但作业必须失败。发布作业仍依赖validate、build、native、acceptance全部成功，且仅显式发布分支与main同SHA允许公开并匿名重新下载摘要验证。

GitNexus修改前Rust测试、native run和compose upstream影响均LOW，无产品流程；其FTS离线扩展不可用。mcp-probe-kit code_review/gentest返回审查指导，语义核查由执行者完成。未修改共享Rust/TypeScript/Svelte产品函数或依赖图。ARM64、Ubuntu26.04、无桌面Server、全部Wayland/GPU、FUSE完整模式与公网长期压力未认证。

## 原始来源

- 原生失败：https://github.com/Eswink/coding-tools-mcp/actions/runs/34348014504
- PR Linux基线失败：https://github.com/Eswink/coding-tools-mcp/actions/runs/34348012392
- D-Bus激活环境：https://dbus.freedesktop.org/doc/dbus-update-activation-environment.1.html
- Rust非WindowsSO_REUSEADDR实现：https://doc.rust-lang.org/src/std/sys/net/connection/socket/mod.rs.html

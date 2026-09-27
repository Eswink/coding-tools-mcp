# 需求文档：desktop-sandbox-enforcement
## 功能概述
从9b2639d继续#73，消除生产桌面exec路径与已验证LinuxSandbox库之间的接线缺口。不是整个云网关路线图完成声明。
## 需求列表
### FR-1：固定宿主工作区
ToolContext保存由本地配置构造的LinuxSandbox或失败状态，后台快照与会话域复用同一目录句柄，不从模型入参重新构造。
- [ ] WHEN 工作区路径被替换 THEN 系统 SHALL 保留原目录边界或在执行前拒绝，不能扩大访问。
### FR-2：实际执行强制隔离
沿用唯一call_tool、原策略、任务及会话存储。所有Linux子进程（包含旧tty标志和异步任务）必须执行Landlock/seccomp准备；失败为明确安全错误，不重试无沙箱。
- [ ] WHEN 原始MCP探针执行 THEN 系统 SHALL 通过4项授权控制和7项隔离断言，断言保持原样。
### FR-3：本地授权
在已完成桌面策略检查后、子进程启动前签发并提交现有不透明LocalAdmissionTicket；远程入参不能创建许可。
- [ ] WHEN 授权/工作区generation改变 THEN 系统 SHALL 拒绝新子进程；保持已有在途排空语义。
### FR-4：环境与元数据
Linux子进程不继承桌面环境，HOME/TMPDIR均绑定工作区，网络始终拒绝。模型沙箱覆盖字段拒绝。成功执行与原生内建诊断分别如实标记是否隔离。
- [ ] WHEN 仅检查环境 THEN 系统 SHALL 报告强制策略及尚未探测的内核可用性，而非伪造通过。
### FR-5：生命周期与兼容
所有Linux子进程由进程组管理；保留现有任务去重、取消、撤销排空、过期、重启不重放和输出语义。Windows生产行为不变；旧桌面tty标志不冒充新增原生PTY。
- [ ] WHEN 双平台现有完整回归运行 THEN 系统 SHALL 无新增失败，Linux补充固定根、环境、默认隔离测试。
### FR-6：交付
固定源码树、锁定依赖、保留失败证据，专项与完整原生CI后才允许并入功能分支。main、生产部署和稳定Release不变。
- [ ] WHEN 工程验证通过 THEN 系统 SHALL 记录准确范围，不将其他未完成路线图或实机观察标为通过。
## 非功能需求
默认拒绝、错误不泄露底层路径和环境、无新远程授权入口。
## 范围之外
Windows新沙箱、云端业务桥接、Hooks/worktrees/snapshots、安装包与实机验收不由本增量证明。

## 依赖关系
依赖已提交9b2639d的LinuxSandbox、桌面ChatAuthorizer两阶段票据、现有ToolContext/SessionStore/ExecTaskStore；不引入云授权来源。

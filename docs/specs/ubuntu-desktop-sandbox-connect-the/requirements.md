# 需求文档：ubuntu-desktop-sandbox-connect-the

## 功能概述
为 Epic #32 / Issue #73 接通实际 Ubuntu 桌面远程命令执行的操作系统隔离。基线为 9b2639d47aaecc0a903124404c9c97cbf1f806d6。已验收的 LinuxSandbox 和库级 SandboxedDispatch 不等于桌面执行接线；本增量复用桌面的私有 LocalAdmissionPermit，不开放库级授权铸造器。真实工作站、VPS 和 ChatGPT 观察仍由实机验收确认。

## 历史经验与坑
现有库的文件描述符绑定、Landlock、seccomp 与进程树监督已经有原生测试，必须复用而非复制。票据过期检查必须位于最终准入边界，不能只在等待锁之前检查。图谱可能把 Rust 同名方法连接到无关符号；图谱零调用不等于没有调用。辅助工作流和未提交工作树测试必须与最终候选源码身份区分。

## 术语定义
- 本地许可：仅桌面当前有效授权、工作区执行状态和不可反序列化票据共同产生的进程内对象。
- 执行边界：子进程执行用户代码前完成的 Landlock / seccomp 限制，不是命令字符串过滤。
- 已提交工作：在本地准入线性化点获准的工作；取消不等于没有执行或没有副作用。

## 范围边界
纳入 Linux x86_64 的远程 exec_command、exec_health_check 和由 start_exec_task 调用的命令启动路径；覆盖普通进程及既有交互管道模式、输出读取、终止、授权失效及准入超时。Windows 和非远程桌面命令保留既有行为。桌面真正 PTY 替换、Git/Harness 的全部隐式子进程、Windows 沙箱、云端业务接线、Hooks、worktrees、快照、安装包及发布不属于本增量；不得因本增量通过就关闭整体预发布门禁。

## 需求列表
### FR-1：最终准入时重新验证票据时限
**优先级：Must。** 作为工作区所有者，我需要过期票据不能在等待状态锁或执行锁之后继续获得许可。
1. WHEN 票据在等待授权状态锁或执行状态锁期间过期 THEN 系统 SHALL 返回 LOCAL_ADMISSION_EXPIRED，且不保留在途许可。
2. WHEN 持久执行围栏写入耗时超过票据期限 THEN 系统 SHALL 拒绝返回执行许可；保守的恢复围栏可以保留，不得据此启动子进程。
3. WHEN 票据仍有效且全部身份、权限、代际条件满足 THEN 系统 SHALL 保持原有准入行为。

### FR-2：不可由远程数据创造的宿主绑定
**优先级：Must。** 作为工作区所有者，我需要已批准的工作区对象和现有本地许可共同控制执行。
1. WHEN Linux 远程命令准备启动 THEN 系统 SHALL 验证 exec.run、files.read 和 files.write，固定工作区句柄，并在策略与沙箱准备后完成最终本地准入。
2. IF 缺少任一权限、身份不匹配、授权被撤销或执行代际改变 THEN 系统 SHALL 在启动前拒绝，不接受 authorized、grant_id、sandbox=false 等替代字段。
3. WHILE 已提交操作运行 THE 系统 SHALL 保持许可与进程所有权，直到清理得到确认；未确认终止不得释放恢复围栏。

### FR-3：强制内核隔离和主机策略
**优先级：Must。** 作为工作区所有者，我需要真实进程不能读写工作区外文件或使用未批准网络。
1. WHEN 已批准的命令创建子进程 THEN 系统 SHALL 无条件附加固定沙箱，清除继承环境，只加入明确的宿主环境值，并保留现有命令策略和 ExecPolicy 决策。
2. IF 内核原语不可用、主机有特权、cwd 逃逸或启动隔离失败 THEN 系统 SHALL 失败关闭，不重试无沙箱执行。
3. WHEN 工作区原路径被重命名并由另一目录替换 THEN 系统 SHALL 不把新目录当作原批准对象。

### FR-4：撤销、时限、取消和会话清理
**优先级：Must。** 作为工作区所有者，我需要调用取消或授权失效不会遗留未管理子孙进程。
1. WHEN 操作已提交后授权撤销或单调时钟期限到达 THEN 系统 SHALL 终止进程树，保留已执行或不确定结果，不自动重放。
2. WHEN Pause 发生在操作提交之后 THEN 系统 SHALL 保持原有已提交操作语义；Pause 不是 Revoke。
3. WHEN HTTP 调用结束或调用 future 被取消 THEN 系统 SHALL 保持已创建会话的受限监督和超时，不丢失子进程所有权。
4. IF 同一工作区已有八个受限活动命令 THEN 系统 SHALL 拒绝新活动命令，不建立无限等待队列。

### FR-5：兼容性和准确可观测性
**优先级：Must。** 作为测试者，我需要真实区分内建诊断、隔离子进程、隔离失败和既有 Windows 行为。
1. WHEN 返回执行结果或读取会话 THEN 系统 SHALL 保留准确的 sandbox_enforced、执行边界、命令退出及清理状态。
2. WHEN 环境检查尚未实际建立内核限制 THEN 系统 SHALL 不把工作区句柄创建成功描述为内核隔离验收通过。
3. WHEN 使用异步任务 THEN 系统 SHALL 保留 request_id 去重、输出游标、任务取消、操作记录及重启不重放语义。
4. WHILE 使用既有桌面交互管道模式 THE 系统 SHALL 不声称它已经变成真正 PTY。

### FR-6：可审计原生验收
**优先级：Must。** 作为维护者，我需要从最终提交和真实测试验证本增量。
1. WHEN 修复 FR-1 THEN 系统 SHALL 先证明旧代码在新增回归失败，再证明修正代码通过。
2. WHEN 宣布工程验收 THEN 系统 SHALL 提供同一最终提交的 Ubuntu 与 Windows 原生回归、受影响测试、范围检查、代码审查和源码身份。
3. WHILE 准备或验证工作 THE 系统 SHALL 不修改 main、生产配置或密钥，不将物理验收标为通过，不把辅助工具包标作预发布安装包。

## 非功能需求
NFR-1：共用最多八个活动隔离槽位；输入、argv 与每流保留输出有硬上限。NFR-2：新错误消息与 Debug 不泄露凭据、命令内容或工作区绝对路径。NFR-3：新模块少于 500 行；现有大文件仅做受审查的局部改动，不为格式化扩大差异。NFR-4：无法确认清理时保持失败和不确定状态。

## 依赖关系
依赖桌面 ChatAuthorizer、WorkspaceExecutionGate、ExecSession、异步任务持久记录以及 services/local-agent 的 LinuxSandbox 和 ExecPolicy。底层需要 Linux x86_64、Landlock ABI3+、openat2、close_range、seccomp；限制和未验证工具链兼容性不因接线消失。

## 检查清单
- [x] FR-1 至 FR-6 均有可测验收条件，并明确范围及依赖。
- [x] 未把库测试、辅助 CI、计划或图谱结论当作正式预发布完成。
- [ ] 最终提交上的原生测试与实际实现逐项核验完成。

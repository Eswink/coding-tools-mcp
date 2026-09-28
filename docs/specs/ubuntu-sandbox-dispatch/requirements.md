# 需求文档：ubuntu-sandbox-dispatch
## 功能概述
Issue #73 在416af97库级增量之后，新增共享运行时的强制沙箱调度入口。真实工作站/VPS/ChatGPT验收继续延期。现有LocalAdmission不能从外部构造；不得为了演示执行而公开授权铸造器。本增量实现可供可信本地桥接调用的真实注册表和子进程路径，不宣称已接入桌面授权或云端业务派发。
## 需求列表
### FR-1：本地准入和固定工作区
宿主提供已有的不可反序列化LocalAdmission、批准的工作区路径和ExecPolicy。构造器验证准入身份/能力/有效期并保留目录句柄。实际调用必须同时匹配宿主绑定、注册表的身份和能力检查、generation和有效期；云端或模型数据不产生许可。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：跨会话、工作区、generation、过期和能力不足调用均在子进程之前拒绝，无副作用。
### FR-2：强制策略和严格参数
仅注册sandbox_exec和sandbox_pty。内部无条件附加固定LinuxSandbox，不暴露可选策略、环境透传或disable开关。参数为有界argv、相对cwd、有限timeout、stdin和终端尺寸；拒绝未知字段及路径逃逸。ExecPolicy的Forbidden/Prompt/未匹配均拒绝，当前入口不新增批准机制。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：缺失授权策略不能构造入口；模型sandbox=false、绝对/上级cwd和注入环境均拒绝。内核不可用不能退回无沙箱。
### FR-3：撤销、过期与取消
宿主撤销与启动提交用同一锁线性化。撤销赢先则不得启动；已提交操作收到取消并保留不确定/已执行语义。等待队列和活动任务有硬上限。取消调用或丢弃宿主不得遗留无管理子进程。撤销不可恢复；新宿主不复用旧宿主的请求状态。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：未poll无执行、等待启动时撤销、运行中撤销、future取消、失效后调用和有限期到期有自动回归；不将内存状态作为持久授权恢复依据。
### FR-4：真实内核和生命周期
通过真实ToolRegistry、ExecPolicy及ProcessManager/PtyManager执行，使用持续保留的工作区策略。保护越界读写、网络、子孙进程，有界输出、超时及PTY基本输入/尺寸保持。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：Ubuntu24.04内核测试必须实际执行；Windows既有运行时回归不变，Linux专用步骤按条件跳过。
### FR-5：受限兼容性
验证shell/Python的工作区操作、PTY和输出截断；明确未验证的构建系统和既有chmod/xattr限制，不修改内核过滤器以迎合工具链。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：明确正向兼容用例及失败/限制清单，禁止声称全部工具链支持。
### FR-6：交付和边界
固定工具和源码，真实暂存图谱、fmt/Clippy/锁定Rust测试、已发布候选与父PR回归，保存失败记录和回滚。main、部署、密钥、Windows、云/桌面授权代码不变。宿主真实LocalAdmission桥接接线仍另行实施，#73不因此关闭。
- [ ] WHEN 执行对应场景 THEN 系统 SHALL 满足：无force push，只用普通revert回滚，不删除持久授权数据。
## 非功能需求
安全默认拒绝；最大8活动调用、64KiB输入及每流4KiB输出；仅Linux x86_64支持底层沙箱，其余请求拒绝。错误和Debug脱敏。
## 范围之外
公开授权构造器、Tauri/云WebSocket业务挂载、持久化授权模型变更、网络放行、Hooks/worktrees/UI/安装器、物理验收。

## 依赖关系
依赖416af97的LinuxSandbox、已有LocalAdmission/ExecPolicy/ToolRegistry/进程管理器。真实本地授权生产桥接未实现，不作为已交付内容。

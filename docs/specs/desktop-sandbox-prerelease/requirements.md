# 需求文档：desktop-sandbox-prerelease
## 功能概述
从 9b2639d47aaecc0a903124404c9c97cbf1f806d6 继续实际桌面执行隔离，最终为本地实机验收准备可校验的预发布产物。物理工作站、VPS 和真实 ChatGPT 观察延期，不作为已通过的工程证据。
## 范围边界
本增量接入 Linux 实际 MCP/Actions 共用执行链，保留 Windows 与本地可信调用的既有语义；不从模型或云端铸造授权，不合并 main，不部署在线服务。完整路线图和预发布准入分别核对，不因本增量通过便关闭全部工程。
## 需求列表
### FR-1：固定宿主工作区
WHEN 宿主创建 ToolContext THEN 系统 SHALL 固定本地选择的目录对象，并让会话及后台快照共享此对象，而不是在每次模型调用时重新选择根目录。
### FR-2：强制子进程隔离
WHEN 已获本地授权的 Linux 远程执行到达子进程启动 THEN 系统 SHALL 复用已验证的 LinuxSandbox，在 exec 前设置隔离；配置缺失、内核不支持和带权限宿主 SHALL 拒绝执行，禁止回退。
### FR-3：保留授权和生命周期
WHEN 执行开始 THEN 系统 SHALL 在最后提交点复核原有本地授权票据，保持暂停、撤销、会话隔离、后台工作和重启恢复语义。已提交工作保留既有 draining 语义；本地取消与期限终止 SHALL 清理整个受限进程组，不能误报未发生副作用。
### FR-4：拒绝模型控制与真实元数据
WHEN 入参出现未声明的隔离开关或环境变量 THEN 系统 SHALL 在执行前拒绝；成功启动的子进程返回真实 sandbox_enforced 状态；内建诊断、启动失败和未探测环境 SHALL 不伪报隔离已生效。
### FR-5：实际协议与兼容性验收
WHEN 运行自动验收 THEN 系统 SHALL 通过 PR77 原样的四项控制和七项实际 /mcp 隔离断言，以及新增目录替换、后台任务、取消、stdin、期限、环境和工具链回归；Windows完整基线和Linux库级回归同时保持通过。
### FR-6：可复核交付
WHEN 生成预发布产物 THEN 系统 SHALL 绑定源码SHA、版本、构建日志与SHA256清单，提供本地测试和回滚说明；未完成路线图、未运行检查、图谱限制与实机延期 SHALL 明确列出，不包装成整体已完成。
## 非功能需求
不在 pre_exec 内分配内存或锁定互斥量；错误不泄露路径/凭据；现有输出/期限/并发上限不放宽；系统运行库只读，网络禁止，清空父环境。支持普通用户 Linux x86_64；其他不支持条件必须失败关闭。
## 依赖关系
现有 ChatAuthorizer issue_local_admission_ticket/commit_local_admission、工作区执行门、会话进程树和 Local Agent LinuxSandbox。其他路线图工程仍由各自门槛约束。

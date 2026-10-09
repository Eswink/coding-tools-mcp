# Windows 实际请求调用链

## 功能概述
本增量把 HostAgent 实际持久 claim 与本机安装的 host 实例绑定到执行调用。它是 Windows 工作区输入/输出生产调用链的前提，不是新的权限、VM 或回写资格。实际 F2 未知，本增量只在独立草稿 checkout 验证；已有冻结 7/17/9/12/11/12 路径不改。

## 需求列表
### FR-1 实际 claim 上下文
WHEN Worker 在实际 HostJournal 成功持久 claim 后，系统 SHALL 签发不可 Clone、不可 Deserialize、不可外部构造的 ClaimedDispatch；它强持有实际 journal 与实际安装的 host，绑定完整 request、peer、参数摘要和 deadline。WHEN 请求不同、host 实例不同、pending claim 不存在/已完成/poisoned 或过期时，系统 SHALL 拒绝验证。

### FR-2 实际调用与兼容
WHEN Worker 执行已 claim 请求时，系统 SHALL 调用 additive LocalHost::execute_claimed，携带真正的 opaque permit 和上下文；旧 LocalHost 的 execute 实现 SHALL 保持默认兼容。WHEN NativeLiveHost 接收调用时，系统 SHALL 在克隆 host 和 native blocking 之前核对实际 host 实例，在产生真实 WorkScope 的同一调用处持有上下文。未知结果 SHALL 不自动 complete journal 或形成可重放 authority。

### FR-3 后续 Windows 具体 owner 边界
WHEN Windows 私有工作区 caller 可用时，系统 SHALL 只把实际 ClaimedDispatch 与实际本机三 scope permit 一起移入非泛型 WorkspaceRunGrant，并绑定精确 execution request ID、conversation、native host/profile/source/根/会话和显式输入输出路径。任意 WorkScope、generic G、JSON、Go bool、InputCompletion 或 CloneCompletion SHALL 不产生授权、wholeVM retirement 或输出 issuer。缺少实际 VM/guest/全部 IO retirement 时生产执行与输出 SHALL 继续拒绝。

## 非功能需求
- 所有 metadata/代码/测试只写隔离 checkout 或外部 evidence；不 seal、不提交推送、不移植根候选。
- 编辑前 GitNexus 只使用 never、index-only、drop-embeddings 的已审本地方式；不重试被拒绝的扩展导出操作。
- 真实 Agent crate 运行 fail-first 与成功回归；Windows owner/fulldesktop/native 未运行必须明确 NOTRUN。
- 不修改 snapshot/restore/background_snapshot/PR98、公开工具 schema、共享 ToolContext；不操作真实用户机器、HCS/VM、ACL/网络/凭据或安装编译器。

## 依赖关系
实际 HostJournal claim/complete、LocalHost opaque Permit、NativeLiveHost/native_drain、冻结 opened-root/InputLease/owned_run。后续实际 GuestMain、creation-owned HCS 与 opened write root 独立增量，不由本规格凭数据补齐。canonical63 本增量闭合 0 项。

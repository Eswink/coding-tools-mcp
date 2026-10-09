# 显式 Windows 工作区 IO 与具体权限 owner

## 功能概述
第二独立增量把 exec_command 的显式 workspace_io 纳入完整请求摘要，把真实 HostAgent claim 与实际本机三 scope permit 移入具体 WorkspaceRunGrant/InputLease。它继续实现实际 producer 链；尚无 creation-owned HCS/wholeVM/全部 IO 退休证明，所以不会执行 VM 命令、接受输出或启用生产资格。已有首 caller10、7/17/9/producer12/IO11/guest-output12/stable5 和根候选不改。

## 需求列表
### FR-1 显式有界合同
WHEN exec_command 请求包含 workspace_io 时，系统 SHALL 只接受恰好 input、output_parent、output_leaf 三个字符串；输入和父目录 SHALL 是严格相对的现有目录链名称，叶名 SHALL 是单个合法 Windows 名称。系统 SHALL 拒绝绝对/UNC/drive/ADS/设备/遍历/空段/末尾点空格/控制字符/未知键、超长/超深路径；命令/参数仍受完整 4096 byte request bound。workspace_io 模式 SHALL 限制 workdir 为 '.'、tty=false、有限 cmd/stdin。缺少 workspace_io 的原参数/default/hash行为 SHALL 保持兼容。

### FR-2 完整 scope 与摘要
WHEN workspace_io 出现时，Agent/Gateway static catalog SHALL 要求 exec.run、files.read、files.write 全部 scope，primary scope 仍为 exec.run；任何 IO 字段变化 SHALL 改变同一规范请求摘要。WHEN workspace_io 不存在时原 scope SHALL 保持 exec.run。系统 SHALL 不从 shell 字符串、泛型参数、传输 JSON 或 Go bool 推断路径授权。

### FR-3 实际 native caller/permit/input
WHEN 实际 Worker claim 进入 NativeLiveHost 的已绑定 callback 后，系统 SHALL 只消费同请求的不可复制 claim、真实 native prepared ticket、真实 WorkScope；在当前 authority、peer、profile、完整 binding/deadline/cancel 检查后 commit 实际三 scope LocalAdmissionPermit。系统 SHALL 把 claim 和 permit 一起放进非泛型 WorkspaceRunGrant，并由已有 Retained 持有实际 root authority/InputLease/immutable transfer/guards；operation SHALL 等于实际 request_id，所有 source/host/profile/caller/session/路径绑定 SHALL 保持原值。任何未确认 close/panic SHALL 保 whole-owned package，不仅 bool/fence。snapshot/restore/PR98 SHALL 不参与此授权。

### FR-4 缺少 VM/output 时持续拒绝
WHEN 真实 wholeVM/全部 IO 退休/guest FID+hash/同源 image/runtime/不可 Clone output issuer 尚未成立时，系统 SHALL 返回有界拒绝诊断，不执行 VM、写 host output 或替换现有文件。旧/local 非 claimed exec_command 对 workspace_io SHALL 在任何执行/工作区路径效果前拒绝。跨平台不支持的模式 SHALL 拒绝，不能静默忽略参数。后续实际 GuestMain 与 creation-owned HCS 增量 SHALL 独立继续，不能把 preflight 的 VM_UNAVAILABLE 算目标完成。

## 非功能需求
编辑前 fresh local-only GitNexus never/index-only/drop-embeddings；人工权限/共享合同 HIGH 风险报告。实际 Agent 合同与兼容回归、fail-first 和必要源检查留原件。Windows native/fullHost 未运行如实 NOTRUN。无安装编译器/OS依赖、ACL/网络/凭据/用户或生产/HCS运行。实际 F2未知，不seal/提交推送/移植root/WF/sourceprofile。

## 依赖关系
首 actual caller10 与真实 HostJournal、NativeLiveHost、LocalAdmissionTicket/Permit、冻结 opened-root/InputLease/Retained/owned_run。新数据合同不产生 image、HCS 或输出权限；canonical63 closure=0。

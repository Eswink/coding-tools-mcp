# 具体 workspace_io 调用设计

## 概述
对应需求：FR-1、FR-2、FR-3、FR-4。新字段是被摘要绑定的数据；只有真实 claim 与本机 opaque permit 形成具体 owned caller。不能由数据对象获得 native grant。

## 技术方案
1. Agent catalog 增加闭合 optional workspace_io schema 和显式 workspace_scopes metadata；scopes_for 根据字段存在选择完整三 scope，不把 malformed 值当原单 scope。公共 data parser 验证严格 Windows 名称、1024 byte path/64 components/255 UTF16 leaf，workspace mode cmd<=2048 byte、stdin<=1024 byte、workdir='.'、tty=false；不 rewrite 路径或默认字段。
2. NativeLivePermit 保存 ordinary PreparedCall 或新的 Windows WorkspaceAdmission ticket。普通旧 execute 不接受 workspace ticket；只有 execute_claimed 的实际 instance check 后，actual native blocking callback 可以进入 workspace method。Linux unsupported workspace_io 先拒绝；旧/local exec::exec_command 对任何 workspace_io 在效果之前拒绝。
3. WorkspaceAdmission 只持实际 native ticket/current authority/RemoteRequest/完整 ExecutionBinding/IO data/deadline。admit 阶段不读取输入或创建输出。native commit 入口核对同一 actual claim/request/current peer/profile/authority，commit 三 scope permit 前后重新检查 deadline/cancel/current identity。
4. concrete WorkspaceRunGrant 新字段持不可 Clone ClaimedDispatch，request_id 作为 operation。真实 root authority/InputLease/Transfer 由已有 owned_run 移入 Retained。旧 private diagnostic grant 允许显式 None，但不能走新的实际 claimed factory。unknown/panic whole box 保 token/actualpermit/context/root/bytes/handles；checked source close 后才释放。
5. 结果仅是有界 preflight 拒绝。actual guest workload、private cancellable transport、creation-owned HCS/wholeVM IO retirement 和 opened write root 尚未成立，不 mint OutputSeal、不借 Completion/Go witness。保留已有 output create-only、不 overwrite、latecancel/unknown effects 规则。

## 文件结构
services/cloud-agent/src/catalog.rs、catalog/exec_run.json、新 catalog/workspace_io.rs 与具名 tests；src-tauri/src/tools/cloud_host/live.rs、live/claimed_call.rs、windows_workspace.rs/新的 workspace admission 子模块；exec.rs 的早期 fail-closed guard；三规格和 outside receipts。禁止修改 background_snapshot/ToolContext/ChatDomains.scoped/snapshot/restore/PR98。

## 验证与待项
真实 Agent parser/scope/hash/default 负例和完整回归；static native source/full desktop 类型检查尝试保持缺stock工具的事实。Windows2025 后续必须同实际 committed F2/rawparent/fullcensus/actor/run/attempt，测试真实 ticket/claim/permission/pauseABA/closeunknown/panic/inputFID；不能用旧38或组件 PE/types 替代。

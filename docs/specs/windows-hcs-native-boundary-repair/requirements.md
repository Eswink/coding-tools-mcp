# 创建所得 HCS 原生边界修正需求

## 功能概述
仅在新隔离源码修复独立审查已确认的 allocator 后取消、VM raw JSON 视图不一致与 LocalSize padding 初始化前置条件。冻结 creation16、Guest11/root/旧 Plan 和 PR98/snapshot 保持不变。所有现有真实 Claim/三 scope permit/root/input/HCS 整包 owner 与未知/panic retention 继续成立。原封包及失败/环境阻断全部保存。

## 需求列表
- FR-1 首次效果：实际 HcsCreateOperation 返回后、任何 HcsCreateComputeSystem effects 前重新检查实际取消和 Instant deadline。拒绝时不得 attempted/create；只有真实仅分配 operation、从未调用 compute API 且 system/result/其它 slots 为空的具体 owner 才可调用 void HcsCloseOperation 并恢复无对象状态。取消不是退役授权，未知或可能 VM effect 必须整包保留。
- FR-2 有界原生结果：LocalSize 仅 allocation bound，不是初始化或字符串长度证明。不得形成整个 rounded allocation 的 Rust u16 slice；仅通过当前进程 ReadProcessMemory 向已初始化局部字节复制每个 unit，要求 BOOL 非0与实际 bytesRead=2，在 NUL 停止。deadline、复制失败、越界、无 NUL、UTF16/JSON/LocalFree 失败一律整包 unknown。pseudo current process 不 open/duplicate/close，不改变权限、不读其它进程。
- FR-3 真实数据模型：有限 typed Configuration/VirtualMachine/Topology 每层 deny_unknown_fields 与结构字段 duplicate reject；不使用 serde_json Value 折叠后再发送 original raw JSON。外部接口、设备/boot/disk/GuestState/绝对路径等未获 actual asset owner 字段拒绝。hash/ENV/native source 只 provenance；当前 fixture constructor 明确 ASSET_OWNER_UNPROVEN DENY，不能启动 VM。
- FR-4 权限保留：实际 whole grant/claim/permit/context/authority/input bytes/native system/operations/results 从 registry-before-effects 到 checked retirement；测试 data/fake allocator/boolean 不 mint issuer。新的 checkpoint/data reader 纯逻辑不证明 wholeVM/native/fullHost。existing output overwrite/snapshot restore/PR98取消持续DENY。
- FR-5 验证：portable duplicate config、有限 prefix-reader/checkpoint 失败先行后修复，当前 data/Retained/registry必要回归；Windows actual allocator/no-compute effects、LocalAlloc initialized-prefix/rounded tail及全NativeHost/HCS/WSS必须未来同源 nativeCI。缺 compiler/系统依赖不安装；本地不跑HCS/Windows/VM、不seal/推送/F2、不碰用户或生产机器。

## 非功能需求
编辑前 GitNexus LOCAL never/index-only/drop-embeddings 的7 exactUID与人工HIGH，Probe3spec/check/root cause 在代码前闭合。所有日志与修正前 source retained。生产、GuestIO、HostOutputIssuer、actualF2、canonical63均未qualified；后续必须接真实 opened asset/image owner和Guest/privateIO producer，不能以该DENY称工作区完成。

## 验收标准
WHEN operation 分配期间取消或过期，系统 SHALL 在 create 前拒绝并只退役确证无VM的实际 operation。WHEN LocalSize 存在 padding，系统 SHALL 不在 Rust 假定 padding initialized。WHEN raw JSON 存在 nested duplicate/unknown asset paths，系统 SHALL reject，不由 metadata 授native效果。

## 依赖关系
冻结 creation16 的 actual Claim/permit/Retained、primary HCS/Kernel32 SDK，typed data/portable fixture crate 与新native同源CI。actualimage/root asset owner与GuestIO/issuer仍缺，constructor保持DENY。

# 设计文档：windows-foundation-new

## 概述

对应需求 FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, NFR-1, NFR-2, NFR-3。基线是D6+73真实源码；以下是新设计，不是旧40文件内容推断。

## 技术方案

### 技术选型

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| 输入 | 复用实际Nt相对open/root authority | 避免字符串路径授权 | FR-1, FR-2 |
| byte owner | 有限Vec块、非Clone结构、显式独立复制 | 保持原输入与detach并存 | FR-2, FR-3 |
| transfer | SHA256/有界identity/offset状态 | 仅数据契约 | FR-3 |
| owner | 原actual grant和Retained整体owner | 未知状态不提前释放授权 | FR-4 |
| 输出 | 尚无close issuer，固定拒绝入口 | 缺实际证据不扩大写回 | FR-4 |

### 架构设计

NativeToolHost拥有独立WindowsInputAuthority；WorkspaceRunGrant仍持actual Claim和三scopepermit。InputLease通过authority.acquire持有根与祖先句柄，再逐组件打开输入，opened先登记后验证。读取前后identity,size,cursor必须一致，大小1MiB封顶；ImmutableChunks保持原始字节。transfer生成独立不可变副本，不共享可变文件句柄。不接现有snapshot/rootwork身份作为文件授权。

## 数据模型

| 实体 | 内容 | 不变量 |
|---|---|---|
| InputLease | root/input owner、original chunks、read cursor/info、poisoned/unknown/retired | 每个handle先注册，关闭未知永不判定完成 |
| RunBinding | host/profile/caller/source/session/operation/input/output names | 全字段有限，source为actual source SHA；无权限 |
| InputTransfer | binding/size/hash/独立chunks | 非Clone、只能在checked close后清空 |
| OutputStage | 无实际issuer，固定默认deny | 数据字段/cleanup诊断不是seal |

## API 设计

| 函数 | 契约 | 需求 |
|---|---|---|
| InputLease::prepare(authority,host,profile,relative,deadline,cancelled) | 打开/验证/有界完整读；错误保留已取得资源 | FR-1, FR-2 |
| InputLease::transfer(binding,deadline,cancelled) | 逐块受限复制到独立owner，与读input路径精确相同 | FR-3 |
| InputLease::summary/revalidate/retire | 实际根identity/大小/hash；重验；所有handle逆序checked close | FR-2, FR-4 |
| WindowsInputAuthority production registration | exacthost/profile/context.workspace.root，非snapshot | FR-1 |
| outputstage deny entry | 未actualcloseissuer永不写文件 | FR-4 |

## 设计决策

### 决策1：运行与资产生产副作用分开（FR-5）

原16assert positive先构造fixture，然后创建Harness，然后只申请exec.run/files.read/files.write。其constructor不能在host尚不存在时创造新stage permission。三scope旧入口只允许消费已由获准的一次性GitHub CI provisioning实际生产、固定原生句柄/根/生命周期、非Clone且单次移交的OwnedBootAssets。registry键只有exact source/runner/configdigest及当前host/request绑定检查，不能构造资源/权限。缺实际owner继续deny。

新增在线unpack/create/scratch副作用必须由单独vm.assets.stage real localticket+actualClaim授权，其实际生产owner在执行时仍持生产Claim/permit，并在绑定同源host/profile/root/session、真实执行Claim后单次移交；执行仍保留独立三scope grant。禁止caller bool、config/env/hash、预先路径、已存在systemid替代actualowner。

具体boot producer与CI bootstrap不在missing40路径中；需要独立有限新增路径、fresh impact、source-qualified compiler及明确image/HCS实验验证。当前foundation不能宣称让原positive通过，native与发布仍BLOCKED。

### 决策2：拒绝以diagnostic作为writeback授权（FR-4）

输出stage缺少实际VM+所有IO+输出资源checkedclose issuer，本增量保留failclosed；不创建synthetic seal。将来producer单独规格，不放宽production默认deny。

## 文件结构

以下40是旧丢失路径身份，本轮将写新内容；总Plan额外三MD规格受同一范围管理。

- docs/specs/independent-unqualified-windows/design.md
- docs/specs/independent-unqualified-windows/requirements.md
- docs/specs/independent-unqualified-windows/tasks.md
- docs/specs/windows-execution-opened-root/design.md
- docs/specs/windows-execution-opened-root/requirements.md
- docs/specs/windows-execution-opened-root/tasks.md
- docs/specs/windows-execution-transfer/design.md
- docs/specs/windows-execution-transfer/requirements.md
- docs/specs/windows-execution-transfer/tasks.md
- docs/specs/windows-owned-workspace-run/design.md
- docs/specs/windows-owned-workspace-run/requirements.md
- docs/specs/windows-owned-workspace-run/tasks.md
- docs/specs/windows-private-workspace-stream/design.md
- docs/specs/windows-private-workspace-stream/requirements.md
- docs/specs/windows-private-workspace-stream/tasks.md
- services/windows-vm-broker/transfer.go
- services/windows-vm-broker/transfer_identity_linux_test.go
- services/windows-vm-broker/transfer_identity_windows.go
- services/windows-vm-broker/transfer_test.go
- src-tauri/src/tools/cloud_host.rs
- src-tauri/src/tools/cloud_host/tests.rs
- src-tauri/src/tools/cloud_host/windows_input.rs
- src-tauri/src/tools/cloud_host/windows_input_tests.rs
- src-tauri/src/tools/cloud_host/windows_workspace_tests.rs
- src-tauri/src/tools/windows_vm.rs
- src-tauri/src/tools/windows_vm/input/chunk_tests.rs
- src-tauri/src/tools/windows_vm/input/chunks.rs
- src-tauri/src/tools/windows_vm/input/lease.rs
- src-tauri/src/tools/windows_vm/input/mod.rs
- src-tauri/src/tools/windows_vm/input/owner.rs
- src-tauri/src/tools/windows_vm/input/publication_tests.rs
- src-tauri/src/tools/windows_vm/input/tests.rs
- src-tauri/src/tools/windows_vm/input/transfer.rs
- src-tauri/src/tools/windows_vm/input/transfer_tests.rs
- src-tauri/src/tools/windows_vm/output_stage/gate.rs
- src-tauri/src/tools/windows_vm/output_stage/mod.rs
- src-tauri/src/tools/windows_vm/output_stage/native_tests.rs
- src-tauri/src/tools/windows_vm/output_stage/nt.rs
- src-tauri/src/tools/windows_vm/output_stage/owner.rs
- src-tauri/src/tools/windows_vm/output_stage/tests.rs

## 测试策略

FR-1/2：非法相对名、root host/profile冲突、reparse/hardlink/卷冲突、打开错误注册、读取cursor/size变化、取消/deadline、checkedclose unknown及whole owner保持。
FR-3：空/1MiB上限、hash、offset、重复结束、identity全字段冲突、Detached owner在originalcheckedclose前不清空；GoLinux仅metadata/state，不原生VM。
FR-4/5：默认output deny；protected原positive全文字节/16assert/三scope严格守卫；真正一次性Windows positive须在actualproducer存在后运行，不能skip/xfail/改断言。
FR-6：实际parse仅语法，编译器只在source-qualified一次性GitHub CI；保存全部实际失败，required测试全过后detect_changes/gencommit小步提交。

## 错误处理

同步固定磁盘读返回前不能假称已取消IO；保持wholeowner。prepare/read/revalidate失败poison当前lease，仍需retire。CloseHandle未知不重试rawvalue；既有Retained未知路径保留实际permit/claim/handles/bytes/root/context。

## 安全与兼容

PR98取消10操作和snapshot pause完全保持；生产NativeHost、GuestIO、输出均默认deny。只新增本范围功能和有界测试。四defaultscopes、九prompt/catalog、原positive字节未改变。

## 实施计划

先InputLease/chunks/transfer注册和必要新测试，再Go data-only，再output defaultdeny接线，最后审查producer独立具体scope。不在实现前改source符号；每新符号unknown impact与已有高风险入口impact均保存。无需借历史测试。所有40分组文档保留新实现声明。

## 输出6路径本轮精确边界（FR-4）

输出writer的真实closed-VM/all-IO/actualoutputissuer尚不存在，因此本轮6文件实现固定publication refusal、有限data plan parser和明确不可构造的ClosedVmAndIoOwner私有proof类型。该类型没有constructor/Clone/Deserialize，metadata/config/布尔不能产生该值；不把存在此类型作为实际closeproof。公开入口永远固定拒绝，不执行open/write/rename/remove。nt.rs只定义未来句柄写入之前必须检查的数据边界，不导入unsafe原生写API。owner.rs只有不可构造的真实closed-owner槽，没有假issuer。所有生产写回仍NOTIMPLEMENTED/BLOCKED，source40路径写齐不等于用户安全回写功能完成。

跨 sibling cloud_host::windows_workspace 的现有73 consumer路径需要crate-private模块可见性；只改变注册visibility，不改变Grant字段/构造权限、原current逻辑和三scope，不公开HTTP/外部crate。

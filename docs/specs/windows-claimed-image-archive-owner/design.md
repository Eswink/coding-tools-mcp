# 真实 Claim 所属镜像归档 owner 设计

## 概述

覆盖 FR-1 至 FR-6/NFR-1 至3。修改实际 cfg(test) HCS工程caller，不把有界data组件称为生产工作区完成；正常 NativeHostdispatch仍DENY。

## 技术方案

归档选择器是 exact relative parent data，按现 path规则校验并通过 one-shot CreationFixture注册传入。实际 caller仍先 current claim/request/三scope ticket→commit→nonClone WorkspaceRunGrant。OwnedCreatedHcsWorkspace加入具体 ImageArchiveLease，Retained registry-before-effects在 acquire/root/read之前成立。run_claimed_creation_fixture先 InputLease/InputTransfer，再 native archive prepare；root identity严格join原input root。固定归档通过后仍显式 BOOT_ASSET_OWNER_UNPROVEN，在任何HcsCreateOperation/Compute效果之前拒绝。

## 架构设计

NativeToolHost→WorkspaceAdmission(actual ticket)→claimed callback→actual WorkspaceRunGrant→Retained<OwnedCreatedHcsWorkspace>→InputLease与ImageArchiveLease。Manifest/fixture不含permit；archive state是 data proof。关闭按 archives checkedclose→input checkedclose→transfer clear→guards complete→retire wholeBox，任一失败/unknown/panic保wholeBox。无 archive owner的原fixture维持ASSET_OWNER_UNPROVEN，不追加可执行路径。

## 模块设计

新增 hcs/archive_data.rs，仅固定manifest与bounded hash/cursor/EOF状态和portable测试，不接rawhandle/permission。新增 hcs/archives.rs仅当前Windows cfg(test) parent，使用input::nt/root实际retained句柄。fixture.rs加入相对selector data constructor并保持旧constructor拒绝；fixture_registry.rs仅补 data-only test构造字段；hcs.rs持有具体lease并在真实caller处理。原root/nt/lease/grant/Claim源码不改；所有现API调用先freshimpact。

## 数据模型

固定 ManifestEntry=leaf、size、SHA256，不Deserialize/任意外部factory。ArchiveHasher记录next_offset/expected size/hash/sticky error/EOF和Sha256状态；没有source permission。ImageArchiveLease持root链、每个具体Opened/info/cursor/hash data，非Clone。资产证明不能返回原路径供HCS使用。wholeOwner仍持实际非Clone grant/claim/permit、Arc原context/authority、InputLease/InputTransfer、opaque actualHCS SYSTEM/operations。

## API 设计

ImageArchiveLease.prepare只从实际authority、actualgrant host/profile、严格selector和deadline/cancelled读取；retire仅实际checkedclose。CreationFixture::for_current_disposable_runner_with_archives只造source/runner/hash-bound selection data，不能造 permission。ArchiveHasher.push(offset,bytes)及finish只验证数据，在未知/完成后拒绝复用。

## 文件结构

本folder3spec；修改input/owned_run/hcs.rs、hcs/fixture.rs、hcs/fixture_registry.rs；新增hcs/archive_data.rs与hcs/archives.rs。必要Windows native tests放archives.rs内或独立child，文件≤500行；预算总8paths，超出必须准确记录。

## 设计决策

选择真实readonly归档 producer先接actualgrant，而不复用旧Go path/import privileges。源档哈希能证明本次读取流，不证明映射排除或之后路径重用；因此不传bootpath，不给HCS配置新增Devices/GuestState字段。后续必须 creation-owned immutable copy/import后的有限boot资源、同owner scratch和Guest启动配置，并以实际源/权限/runtimeCI审查。

## 错误处理

任何源info/cursor/hash/EOF/取消失败sticky reject。只读无文件作用且全部关闭已确认时可退役permission；未知close/panic整包retain。同步read前后期限不是阻塞中断，future actualcancelIO adapter仍必需。无法安全产出bootowner时保持明确deny而不放宽到ENV/rawJSON。

## 安全性考虑

相对NT访问、fullFID和share不是permission issuer。actualGrant来自真实native三scope commit并保actualClaim。目录/VM/输出退役不由read成功或JSON推导。不得改paused snapshot/PR98；不调Admin/privileges/ACL/network/用户机器或prod。

## 风险评估

Native权限链人工HIGH、HCS生命周期既有CRITICAL；graphLOW仅下界。3GiB fixed archives需有界时间与真实native兼容验证；磁盘同步阻塞取消、existing writable mapping及imported boot producer仍未闭合。组件source/typing不称fullHost或F2。

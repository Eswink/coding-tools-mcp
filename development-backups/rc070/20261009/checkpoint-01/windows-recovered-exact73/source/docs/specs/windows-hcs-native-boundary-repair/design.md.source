# 创建所得 HCS 原生边界修正设计

## 架构设计
actual Claim→committed WorkspaceRunGrant→Retained<OwnedCreatedHcsWorkspace> 不变。Create slot0 allocation 后调用共享 checkpoint；其失败分支仅调用所有 actual native invariants 已满足的 no-compute-operation retirement，未知保 wholeBox。Start/Terminate/wholeExit 的 existing sticky uncertainty 边界不放宽。

## 模块设计
native.rs 接 actual allocator/compute API/void operation close与Kernel32 ReadProcessMemory+GetCurrentProcess。新增 boundary.rs 仅纯 checkpoint 与 bounded initialized-copy decoder，接 reader FnMut(index)->Result<u16>；它不接受原始 pointer、permission、VM ID 或 retirement evidence。native reader 每次实际复制2bytes到已初始化局部array，实际 bytesRead exact2且allocation offset checked。fixture.rs 的 typed VM 只允许当前已支持 ComputeTopology 空有限对象；未知 VM assets 字段全部拒绝，constructor ASSET_OWNER_UNPROVEN，下一 actualopened/image asset issuer 独立接入。

## 数据模型
不可Clone CreatedSystem、CreationFixture、actualClaim/permit/lease owner 保留。Allocation/result实际rawpointer仅native owner持有；pure Vec<String> decoder 没有权限。新asset producer 不在本修复中伪造；存在的 engineering hash/environment 不满足asset授权。

## 错误处理
Native result失败未知→uncertain→wholeowner Retained。postallocator reject只有从未调用computesystem才close真实operation；void返回只说明调用返回，不造HRESULT。任何config不支持/资产owner缺失在真实native effect之前DENY。cancel/expiry aftercreate保持旧unknown并不声称VM已停。

## 安全性考虑
原16是source STATICBLOCKED，component passes不能提升native。此修复不更改snapshot/restore constructor、PR98、ACL/network/admin/compiler或源profile/workflow。具体image/ancestor/root/Guest/allIO/outputissuer仍待真实 producer 与F2同源nativeCI。

## 概述
修复当前source-reviewed实际原生边界，不改变whole concrete permission ownership。对应需求：FR-1、FR-2、FR-3、FR-4、FR-5。

## 技术方案
FR-1 actualallocator后共享checkpoint；FR-2 当前process Kernel32复制unit到已初始化array并在NUL停；FR-3 全有限typedserde字段不保存Value并拒绝assetowner缺失；FR-4 concrete整包retention不放宽；FR-5 portable实际旧source失败先行、新native后续同源验证。

## 文件结构
现native.rs/fixture.rs与新boundary.rs。spec3文档位于当前新folder。cfg(test) native boundary tests仅当前WindowsCI，未运行不记passed。

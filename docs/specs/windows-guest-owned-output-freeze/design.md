# 设计文档：windows-guest-owned-output-freeze

## 概述

FR-1/FR-2 产生仅 guest realm 的具体 raw owner；FR-3/FR-4 将实际读取字节与原输入/父/输出完整身份绑定；FR-5 对不确定寿命和数据不授予授权保持拒绝。

## 技术方案

效果前将 concrete guestOwnedOutput 注册强引用。DuplicateHandle SAME_ACCESS、inherit=false 持实际父，relative NtCreateFile 固定 "." 重开 directory shareRW/noDELETE 并核完整身份。输出叶仅 guestLeaf 子集，FILE_CREATE，noReparse、NON_DIRECTORY、同步；writer WRITE_DATA/READ_ATTRIBUTES/SYNCHRONIZE，shareRW；原 pin READ_DATA/READ_ATTRIBUTES/SYNCHRONIZE，shareRW，同 fullID、volume、links1、size0。所有 native raw handles 无 os.File finalizer。

freeze 是未注册 data-only primitive，不接受 fake completion。未来 caller 必须真实停止 command；本函数无法证明 command 或 wholeVM 退出。重新 input.observeInput 后 Flush writer、checked CloseHandle writer、相对 FILE_OPEN readonly/shareREAD，必须匹配原 pin 完整 ID/size/link/type。strict open 失败不重试降权或删除。读前后 parent/pin/frozenRead identity、size/cursor 及 cancel，32KiB bounded chunk/1MiB total，单字节精确 EOF，SHA256，实际 input 再校验。读取字节不可变副本与 guestInputEvidence/output FILE_ID_INFO 一起留在 owner；一次 private encoded output stream 不产生原生 authority。

所有失败 sticky，createMayHaveEffect 保留；unknown close 保 raw handle 数值及父/子/字节，不能重用/重试；panic registry 强引用保留，后续不接受成功。不访问任意宿主 share，不更改 ACL、网络、凭据。所有关闭成功后才 clear immutable/delete registry。input 原 owner 由原 registry 独立持有，output 不把其借用当 actual host permit；未来 caller 必须具体整包拥有 grant/authority/input/VM/output，并确认全部 source/input/VM handle 关闭。

## 文件结构

新增 services/windows-vm-broker/guest_workspace_output_windows.go、guest_workspace_output_io_windows.go、guest_workspace_output_native_test.go；本目录母规格与两子规格。已有源码逐字不改，生产、VM/HCS 与 guestmain 不接入。

## 设计决策

重复 ABI 于新私有 helper，避免改冻结 input helper；参数只允许固定点 parent 或已验 leaf，无绝对 NT 路径。来源、操作完整 binding 摘要只是数据 checksum，不是 capability。未来 actual F2 native runner 必须测试 full source、原 38 当前源码、新 source exact inventories 与 raw logs；旧组件 PASS 不借给此源。Windows compiler/toolchain 不安装或更改宿主。

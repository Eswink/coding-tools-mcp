# 实际 Guest workspace 技术设计

## 概述
此次把实际 GuestMain 新模式与现有 native data owners 相接，不把 data evidence提升权限。用新的纯逻辑控制/模式选择器支撑可本地跑的 fail-first；新Windows-only执行模块实际调现有句柄producer。

## 技术方案
FR-1：新 workspaceGuestControl 只含有限 command/stdin/input leaf/output leaf/source/session/operation/binding/input size/hash/timeout；控制长度前缀4字节、JSON4096上限，拒重复和未知字段、无 lossyUnicode/path归一化。binding/hash/source是 data，必须由以后 host concrete owner对真实approval/request/input manifest逐字绑定，不自己提供permission。真实 main 模式选择器保持旧入口。
FR-2：新增 input freezeForWorkload；pin/read存 actual注册 owner字段且 native返回直接赋owner字段；未知返回不重用handle；只允许已经写满、真实EOF/hash验证的叶名对象，hash/FID不变。Readonly input禁止再次writeChunk。
FR-3：新 guestWorkspaceRun whole owner强registry在效果前（满/冲突拒绝）；目录根只固定guest workspace下的独立随机operation临时目录，原parent os.File连同原rawHANDLE值强保留；未知close不自动清注册或Delete目录。输入承接physicalEOF，输出 FILE_CREATE/noReparse，stdout writer每chunk检查原FID/size/cancellation与1MiB限额；cmd仅fixed PowerShell -EncodedCommand，工作目录固定 operation root。
FR-4：os.exec.Cmd 的真实 Wait等process及IOgoroutines；timeout/WaitDelay/ErrWaitDelay失败；不声称descendant/wholeVM已退役。完成后既有freeze/wire产direction2 bytes和实际guestFileID；将wire/原输入/实际command/metadata保存在whole owner后再checkedclose；只有三组资源均确认close才返回data，发布失败仍保留wholeowner直到真实VM owner介入。成功返回只data，不是retirement witness。
FR-5：宿主dispatcher/preflight/sourceprofile/权限/VM owner不更改。下一native Rust owner必须实际HcsCreateComputeSystem返回HCS_SYSTEM，S_OK启动与HcsWaitForOperationResult成功分开，HcsWaitForComputeSystemExit actualhandle确认wholeexit；HcsCloseComputeSystem void不假造HRESULT；还需allIO/root/sourcecheckedclose及concrete非Clonegrant才能有issuer。

Cmd.Wait 的 internal parentIOPipes closeDescriptors 不检查 Close 返回值，因此即使真实命令退出和 copying join 成功，command_resources_unconfirmed 始终 true。成功 DATA publication 也不解除整包 registry，不清 command/inputBytes/outputWire/metadata；只取消 deadline context 并用 publicationConsumed 拒绝 replay。这不是资源退役确认。后续 creation-owned wholeVM exit 和宿主实际全部 I/O checked close 之前仍不能有 host output issuer。

## 文件结构
services/windows-vm-broker 新portable control/selector/tests、Windows guestcaller及native source-only tests；guest_windows.go main、guest_workspace_file_windows.go input readonly state/close；本3spec。必要newleaf/helper须 exact freshimpact既有symbols先行。生产root/snapshot/PR98/broker/HCS/protocol旧模式和已冻结包保持字节不变。

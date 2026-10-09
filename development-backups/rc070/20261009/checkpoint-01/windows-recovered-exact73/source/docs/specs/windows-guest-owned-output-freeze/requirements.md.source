# 需求文档：windows-guest-owned-output-freeze

## 功能概述

创建 guest 新输出文件并绑定实际父/输入/输出 FILE_ID_INFO，全句柄 owner 在执行写入窗口后拒绝存活普通 writer 并有界观测输出；输出仅数据证据。没有完整调用链和 Windows 实测前不得声称生产工作区安全回写。

## 范围边界

仅新增 guest output 私有文件机制与精确测试/证据；不改已有冻结源码、guestmain、VM 启动、协议旧预算、permission、snapshot、工作流或宿主权限。已有目标一律拒绝，取消/关闭未知保留可能已创建副作用。

## 需求列表

| FR ID | 需求摘要 | 主子规格 |
|---|---|---|
| FR-1 | WHEN 实际父和已观测输入绑定有效，系统 SHALL 在效果前持有 raw owner，独立重复实际父句柄，并相对固定点重开 noDELETE 父 pin、逐项核 fullvolume64/FID128。 | raw-output-owner |
| FR-2 | WHEN 创建输出，系统 SHALL 用相对 NT FILE_CREATE/noReparse，只容许新普通单链接文件，持 own writer 与 readonly pin，二者 shareREAD/WRITE 且 denyDELETE。 | raw-output-owner |
| FR-3 | WHEN 请求冻结，系统 SHALL 先重新观测原实际输入，再 checked-close ownwriter，使用相对 readonly shareREAD 重开并比较原 pin/output/parent 完整身份；任何存活 writer 冲突 SHALL 拒绝。 | freeze-output-bytes |
| FR-4 | WHILE 读取，系统 SHALL 检查取消、最大 1MiB、每次 32KiB、实际 size/cursor/EOF、同句柄 SHA256 与读取前后身份；前后重新核实际输入，产出一次有界 output-direction 数据流。 | freeze-output-bytes |
| FR-5 | IF 失败关闭、取消、panic 或身份异常，系统 SHALL sticky 拒绝证据并保留整包 raw owner/不可变字节与可能创建副作用；仅全部 CloseHandle 成功 SHALL 释放 registry，且任何 Go 数据 SHALL NOT mint host grant/retirement seal。 | raw-output-owner, freeze-output-bytes |

## 非功能需求

所有新文件低于 500 行。原生共享模式、相对点目录、硬链接、游标和关闭仅真实 Windows 临时 fixture 能验证，本机不运行。readonly 共享不是存活 writable mapping 或 VM/process 退役证明。同步 ReadFile/Flush 取消检查不是中断能力，未来 owned IO adapter 必须补齐实际取消/完成证据。当前生产资格、actualF2、canonical63 闭合皆为 0/unknown。

## 依赖关系

复用冻结 IO11 的 guestRawInfo、guestLeaf、guestInputEvidence、guestOwnedFile.observeInput 与 workspaceStream v2 data encoder；原字段不改。未来 producer 必须由实际 guest workload/wholeVM owner 串联，不能以 API 调用或布尔值证明 workload 退出。

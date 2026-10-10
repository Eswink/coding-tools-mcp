# Guest create-only output handle owner

## 功能概述

负责 FR-1/FR-2/FR-5 的实际 raw owner，不授权宿主。

## 需求列表

WHEN input 已完整观测且实际父 fullID 一致，系统 SHALL registry reserve 再独立 duplicate 父句柄、相对固定点重开 parent noDELETE pin。WHEN 新输出创建，系统 SHALL 相对 FILE_CREATE 并比较普通 links1 fullvolume/FID，持 writer 和 readonly original pin，拒绝已有文件。IF 原生返回异常/关闭未知，系统 SHALL retain whole owner/原始 handle/可能已创建效果，不能清空或删除。

## 技术方案

新私有 NT helper 仅固定点 parent 或 guestLeaf；NO_REPARSE，raw owner无 finalizer，registry bound256。关闭成功才逐个清零 handle；unknown sticky 保所有尚未确认 handle。

## 非功能需求

真实 Windows fixtures NOTRUN；不能以 os.File 及任意调用者目录当 host opened-root grant。

## 范围

本子规格仅实现 guest 临时执行目录的实际数据句柄机制。

## 需求回链

FR-1/FR-2/FR-5 在本子规格负责范围与母规格表逐项对应。

## 涉及文件

services/windows-vm-broker/guest_workspace_output_windows.go 与 guest_workspace_output_native_test.go。

## 不做项

不接 guestmain、command/wholeVM retirement、host authority/issuer；不改 frozen root/snapshot/PR98 或工作流。

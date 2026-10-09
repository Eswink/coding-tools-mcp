# Checked writer closure and exact input/output bytes freeze

## 功能概述

负责 FR-3/FR-4/FR-5，依赖 raw-output-owner，产出 guest 数据 snapshot。

## 需求列表

WHEN 请求冻结，系统 SHALL 实际 input 重新 read/hash 后 flush/check close 自身 writer、strict readonly shareREAD reopen 同 leaf/fullID，再 bounded read/hash/cursor/EOF 并前后复核 input。IF 存活普通 writer、取消、身份变化或未知关闭，系统 SHALL sticky reject 并保 whole owner；数据 SHALL NOT 表示 wholeVM/host permit。WHEN 返回 wire，系统 SHALL single-use bounded direction2/binding/actualhash stream。

## 技术方案

frozenRead 和 originalPin 同实际 fullID 且 size<=1MiB/links1/type；32KiB 同句柄读和 exact EOF，取消在每次 native 调用前后。同步 IO 阻塞仍需 future cancellation adapter；readonly share 不证明 writable mapped section 已退役。

## 非功能需求

未来 command/VM producer 和 concrete host output issuer 未实现；生产保持拒绝，不接 snapshot/restore。

## 范围

本子规格仅实现 guest 临时执行目录的实际数据句柄机制。

## 需求回链

FR-3/FR-4/FR-5 在本子规格负责范围与母规格表逐项对应。

## 涉及文件

services/windows-vm-broker/guest_workspace_output_io_windows.go 与 guest_workspace_output_native_test.go。

## 不做项

不接 guestmain、command/wholeVM retirement、host authority/issuer；不改 frozen root/snapshot/PR98 或工作流。

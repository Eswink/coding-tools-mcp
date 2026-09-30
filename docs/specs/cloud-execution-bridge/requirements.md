# 需求文档：cloud-execution-bridge

## 功能概述

云端保持MCP/OAuth可用，本地拥有工作区、授权和副作用。实际工具派发与结果回收不能停留在EXECUTION_NOT_CONNECTED或合成回包。

## 范围边界

In Scope：Issue81全部生产桥接与故障验证，完整Epic32依赖不可豁免。
Out of Scope：未经授权的生产基础设施或凭据修改；本轮不把实机观察标为已通过。

## 需求列表

| FR ID | 需求 | 主子规格 |
|---|---|---|
| FR-1 | 请求与回执绑定 | dispatch-core |
| FR-2 | 一次性派发与持久不重放 | dispatch-core |
| FR-3 | 有界队列与独立心跳 | dispatch-core |
| FR-4 | 本地真实授权与批准 | local-authority |
| FR-5 | 实际工具执行入口 | local-authority |
| FR-6 | 批准请求与重启恢复 | local-authority |
| FR-7 | 完整故障验收 | integration-gates |
| FR-8 | 完整计划门槛 | integration-gates |

### FR-1：请求与回执绑定
WHEN 云端派发请求或收到回执 THEN 系统 SHALL 校验请求ID、参数规范摘要、固定connector/device、通道boot/session/generation、grant/authority epoch、作用域和截止时间；任何不一致不得执行或披露结果。

### FR-2：一次性派发与持久不重放
WHEN 同一请求被并发领取、取消、断线或进程重启 THEN 系统 SHALL 在数据库线性化边界最多领取一次；失败的重复领取不得改变另一执行者状态；不确定结果不得自动重放。

### FR-3：有界队列与独立心跳
WHEN 在线Agent声明兼容派发能力 THEN 系统 SHALL 使用有界内存通道、超时及容量限制传递请求；离线不得排队；等待结果时心跳和关闭仍可处理。

### FR-4：本地真实授权与批准
WHEN 本地用户批准或撤销会话 THEN 系统 SHALL 从现有桌面授权服务派生签名投影；云端OAuth、心跳、模型参数均不得创建本地grant、变更工作区或扩大作用域。

### FR-5：实际工具执行入口
WHEN 经认证的Agent收到工具请求 THEN 系统 SHALL 在真正执行前再次提交本地准入并走已有受管工具执行器；不支持的隔离能力必须拒绝，不得回退到无沙箱。

### FR-6：批准请求与重启恢复
WHEN 在线且没有外来独占或恢复阻断的会话请求授权 THEN 系统 SHALL 仅创建有界本地待批准记录；离线、排空或外来请求不得制造通知风暴；重启不得复用过期权限。

### FR-7：完整故障验收
WHEN 执行工程验收 THEN 系统 SHALL 使用真实TCP/WSS/PostgreSQL及本地工具测试覆盖批准、撤销、过期、ABA、并发、取消、断线、重连和旧回包；区分Windows与Ubuntu。

### FR-8：完整计划门槛
WHEN 请求预发布 THEN 系统 SHALL 要求Issue81和Windows沙箱、Hooks、worktree、快照、部署及完整打包全部工程门槛；实机/VPS/ChatGPT延期不是PASS，桌面预发布不替代完整云网关计划。

## 非功能需求

有界32并发，16KiB控制帧，参数/结果上限4096/8192字节。数据库只记录摘要与状态，不持久化命令、路径或输出。调试日志不输出凭据、会话或payload。所有时间必须在最终锁后复查。

## 依赖关系

既有#35、#47、#49、#50、#51是基础，不是端到端完成。依赖见spec-manifest.json。

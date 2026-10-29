# 子规格：持久领取及认证路由

## 范围

完成FR-1, FR-2, FR-3；不缩减完整云网关计划。

## 需求回链

- FR-1
- FR-2
- FR-3

## 验收标准（EARS）

### FR-1
WHEN 云端派发请求或收到回执 THEN 系统 SHALL 校验请求ID、参数规范摘要、固定connector/device、通道boot/session/generation、grant/authority epoch、作用域和截止时间；任何不一致不得执行或披露结果。

### FR-2
WHEN 同一请求被并发领取、取消、断线或进程重启 THEN 系统 SHALL 在数据库线性化边界最多领取一次；失败的重复领取不得改变另一执行者状态；不确定结果不得自动重放。

### FR-3
WHEN 在线Agent声明兼容派发能力 THEN 系统 SHALL 使用有界内存通道、超时及容量限制传递请求；离线不得排队；等待结果时心跳和关闭仍可处理。

## 涉及文件

services/cloud-gateway、src-tauri、tools/delivery以及对应测试。

## 不做项

不将基础库或合成peer回包冒充生产host接线，不修改云端生产凭据或部署。

## 设计要点

所有输出绑定真实源码和执行记录，静态审查不替代编译与原生验证；未完成条件显式保留。

# 子规格：故障与发布验收

## 范围

完成FR-7, FR-8；不缩减完整云网关计划。

## 需求回链

- FR-7
- FR-8

## 验收标准（EARS）

### FR-7
WHEN 执行工程验收 THEN 系统 SHALL 使用真实TCP/WSS/PostgreSQL及本地工具测试覆盖批准、撤销、过期、ABA、并发、取消、断线、重连和旧回包；区分Windows与Ubuntu。

### FR-8
WHEN 请求预发布 THEN 系统 SHALL 要求Issue81和Windows沙箱、Hooks、worktree、快照、部署及完整打包全部工程门槛；实机/VPS/ChatGPT延期不是PASS，桌面预发布不替代完整云网关计划。

## 涉及文件

services/cloud-gateway、src-tauri、tools/delivery以及对应测试。

## 不做项

不将基础库或合成peer回包冒充生产host接线，不修改云端生产凭据或部署。

## 设计要点

所有输出绑定真实源码和执行记录，静态审查不替代编译与原生验证；未完成条件显式保留。

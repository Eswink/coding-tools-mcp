# 设计文档：cloud-execution-bridge

## 概述
云网关公开MCP请求与本地工作区执行严格分层；请求先检查OAuth、会话、独占和作用域，再查询设备可用性。现有桌面批准是唯一grant来源。

## 技术方案
FR-1：ExecutionBinding绑定固定设备、会话世代、grant、规范参数摘要和期限；派发和回执做独立边界验证。
FR-2：AdmissionStore在行锁和当前设备/投影/通道锁内将Admitted改为Running。只有赢得领取的调用持有不确定性清理守卫；输掉竞争不能写另一调用的状态。锁后时间复查，未确认结果只记录Unknown，不重放。
FR-3：每Controller持有一个固定路由，以RAII注册身份比较关闭；32容量令牌、有限内存通道、独立WebSocket心跳，关闭旧路由不影响新路由。
FR-4：本地host桥接现有授权服务，投影只能从本地快照生成；不接受远程grant或批准声明。
FR-5：本地最终准入后调用已有工具执行入口和平台隔离，不另建通用云shell。
FR-6：本地待批准和恢复状态由既有服务拥有；重复、外来、离线请求不创建命令队列。
FR-7：先保留失败证据，再校正测试夹具或生产实现。真实数据库/套接字测试独立于纯状态测试和真实主机观察。
FR-8：新增完整生产桥接门槛作为后续整包依赖；未完成工程保留planned/blocked，不能标为deferred真实测试。

## 文件结构
services/cloud-gateway/src/admission：持久化状态和领取。
services/cloud-gateway/src/execution：有界路由、绑定、回包。
services/cloud-gateway/src/channel：认证通道与世代。
services/cloud-gateway/src/agent、src-tauri：仍需生产本地host桥接。
tools/delivery/manifest.json：完整计划工程门槛。

## 设计决策
恢复候选不等于已发布。传输测试中的可信fixture peer不等于桌面原生批准；未连接真实host前不得关闭Issue81。请求侧取消可能已有副作用，不能将其说成未执行。结果撤销后不披露。

## 测试策略
FR-1/FR-2纯Rust及真实PG并发/过期负例；FR-3真实WebSocket能力、心跳和重连；FR-4/FR-5/FR-6本地批准和实际执行测试；FR-7锁定双平台完整回归；FR-8交付状态/依赖测试。

## 风险与回滚
图谱Rust调用解析及FTS有限，零调用结果不证明无影响。未验证代码留在候选；回滚采用普通revert且保留持久账本、撤销和不确定状态。不重置共享历史，不清除授权或不确定任务。

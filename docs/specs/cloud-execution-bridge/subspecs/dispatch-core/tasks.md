# 子任务：持久领取及认证路由

- [ ] 1.1 请求与回执绑定并记录对应原生测试和真实源码。
  - 证据块：Issue #81；恢复候选source.json及原始失败日志。
  - 涉及文件：services/cloud-gateway/src/execution、services/cloud-gateway/tests/execution_postgres.rs
  - _需求: FR-1_

- [ ] 1.2 一次性派发与持久不重放并记录对应原生测试和真实源码。
  - 证据块：Issue #81；恢复候选source.json及原始失败日志。
  - 涉及文件：services/cloud-gateway/src/execution、services/cloud-gateway/tests/execution_postgres.rs
  - _需求: FR-2_

- [ ] 1.3 有界队列与独立心跳并记录对应原生测试和真实源码。
  - 证据块：Issue #81；恢复候选source.json及原始失败日志。
  - 涉及文件：services/cloud-gateway/src/execution、services/cloud-gateway/tests/execution_postgres.rs
  - _需求: FR-3_

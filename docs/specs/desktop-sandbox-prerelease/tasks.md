# 任务清单：desktop-sandbox-prerelease
## 交付物清单
Linux桌面适配器、固定上下文、原样协议断言及新增回归、只读CI、源码/包身份、实机测试及回滚说明；完整路线图仍独立验收。
## 任务列表
- [x] 1. FR-1至FR-6 恢复精确基线、核对现有Plan和新建本增量检查点，执行预编辑影响分析。
  - 证据：context.rs构造器未保存隔离策略；exec.rs默认command.spawn；PR77四项控制通过而七项隔离失败。
  - 文件：本规格，每份不超过150行。
- [x] 2. FR-1至FR-6 固定方案、范围和验证边界并通过规格检查。
- [ ] 3. FR-1/FR-2/FR-3 实现Linux适配、固定目录、最后准入与受管进程组。
  - 证据：已存在ChatAuthorizer::issue_local_admission_ticket及commit_local_admission但实际run_command未调用。
  - 文件：新linux_sandbox.rs少于300行；已有exec.rs只修改已审查入口，不全文件重构。
- [ ] 4. FR-4/FR-5 实现参数/元数据及原样MCP断言和后台取消回归。
  - 证据：exec_command原来恒定sandbox_enforced=false；tests/cloud-gateway/ubuntu_sandbox_dispatch.rs保留原样。
  - 文件：新增linux_sandbox_tests.rs少于400行；三份复用探针不修改。
- [ ] 5. FR-5/FR-6 完成双平台原生编译/测试/审查及包构建和出处校验。
- [ ] 6. FR-6 逐项核对预发布及完整路线图，按实际结果交付，不将延期/失败标为通过。
## 需求覆盖矩阵
| 需求 | 任务 |
|---|---|
| FR-1 | 1,2,3,4 |
| FR-2 | 2,3,4 |
| FR-3 | 2,3,4 |
| FR-4 | 2,4 |
| FR-5 | 4,5 |
| FR-6 | 1,5,6 |
## 文件变更清单
设计列出的Linux接入和精确path依赖、新增协议/生命周期测试及独立CI；不修改内核过滤策略、Windows执行实现、main或在线服务。
## 完成标准
所有对应自动断言真实执行通过；源码与产物身份一致；未完成工程、实机观察及图谱覆盖限制明确保留。

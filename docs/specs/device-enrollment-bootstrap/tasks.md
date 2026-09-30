# 任务清单：device-enrollment-bootstrap
## 概述
Ship bounded enrollment bootstrap without modifying local approval or transport authority.
## 交付物清单（Scope-lock）
New:3 production modules,2 test files,3 spec files,1 operator document. Modified:service/mod.rs,service/cli.rs,agent/cli.rs,device_postgres.rs,run_agent_process.py. About18 new helpers,2 entrypoint routing changes. Production modules each under500lines.
## 任务列表
- [x] 1.1 Add protected document IO and explicit CLI routing, never echo secret input
  - **证据块**: service/cli.rs:20 commands allowlist lacks enrollment; agent/cli.rs:52 run only existing recovery operations; service/input.rs:58 GatewayConfig::read already provides protected input
  - **涉及文件**: service/enrollment_io.rs(200lines), service/cli.rs(+6), agent/cli.rs(+6), service/mod.rs(+5)
  - _需求: FR-1, FR-2, FR-3_ ｜ _设计: API 设计_
- [x] 2.1 Reuse invitation transactions and local key proof; output existing native configuration
  - **证据块**: device.rs:42 create_device_invitation expires300seconds; device.rs:59 redeem verifies signature before locking and consumes once; cloud_connection/mod.rs:44 requires version1 public config
  - **涉及文件**: service/enrollment.rs(230lines), enrollment_device.rs(150lines)
  - _需求: FR-1, FR-2, FR-3_ ｜ _设计: 数据模型_
- [ ] 3.1 Prove shipped from-empty-state bootstrap and preserve security regression evidence
  - **证据块**: tests/run_agent_process.py:204 invokes example agent_fixture; tests/device_postgres.rs:50 race currently shares one key
  - **涉及文件**: tests/enrollment_contracts.rs(200lines), tests/run_enrollment_process.py(200lines), tests/run_agent_process.py(+35), tests/device_postgres.rs(+90), ENROLLMENT.md(90lines)
  - _需求: FR-4_ ｜ _设计: 测试策略_
## 检查点
- [ ] Spec and exact CLI impacts reviewed before edits
- [ ] Red-first command contracts fail for absent commands
- [ ] Current portable and actualPG/WSS tests pass; no unexecuted claim
## 需求覆盖矩阵
|需求 ID|设计章节|任务编号|状态|
|---|---|---|---|
|FR-1|API 设计|1.1,2.1|pending|
|FR-2|API 设计|1.1,2.1|pending|
|FR-3|数据模型|1.1,2.1|pending|
|FR-4|测试策略|3.1|pending|
## 文件变更清单
Exact paths and line budgets listed per task; no migration/dependency/desktop source edits.
## 检查清单
- [x] Scope and requirement links recorded
- [ ] Test and review receipts recorded before convergence

## Verification checkpoint
11 portable CLI contracts,8 real PostgreSQL process cases,25 retained WSS process cases, strict all-target Clippy and324 full gateway Rust cases passed before final common-identity grammar check. That final check has its own unit test and final focused/process reruns; cumulative platform CI remains pending. Initial baseline generate-key command exited1 with agent_invalid_arguments; no source-reconstruction claim is made for the prebuilt red witness. No physical-host or production acceptance claim.

# 实际 claim 调用设计

## 概述
Worker 是唯一 issuer。它已验证 authenticated peer、实际本机 view 与请求，随后在排他 journal 持久 claim，再传入实际 opaque host permit。新的 ClaimedDispatch 不是权限，必须和本机 permit 同时存在。

## 技术方案
对应需求：FR-1、FR-2、FR-3。
1. Worker 的 journal 使用 Arc<Mutex<HostJournal>>，保持原 journal 格式与 exclusive file lock。新增只读 pending 查询，poison 和完整 binding 不符拒绝。
2. ClaimedDispatch 私有字段保存原 ExecutionRequest、actual journal Arc、actual host Arc（类型擦除只用于严格实例比对）。构造仅 host 模块 Worker 可用；外部只能消费和验证。verify_for 比对真正安装的 host 地址、完整 binding、Value 参数、canonical hash、peer/deadline 和实际 journal pending。
3. LocalHost::execute_claimed 默认先验证后将上下文移动进旧 execute future，保留旧实现兼容。Worker 路由到新增方法。NativeLiveHost 显式 override：在 self.clone 之前严格实例比对；上下文移动进实际 native blocking callback，与实际 WorkScope 同调用生成 private caller 包。
4. Windows concrete owner 接入点单独持有 ClaimedDispatch、真实 LocalAdmissionPermit 和当前 context/root authority，任何 false close/panic 仍由已有 Retained 保存全包。不从 command 猜路径；显式 IO intent 必须绑定实际 request 参数并经本机授权，未完成时不调用生产 workspace 执行。
5. 不对已有 execute_scoped/background_snapshot 注入新共享字段。新 caller 只为 future private workspace 路径提供可核对的实际来源，普通工具行为保持原代码。

## 文件结构
services/cloud-agent/src/agent/host/claimed.rs、mod.rs、authority.rs、journal.rs、claimed_tests.rs；src-tauri/src/tools/cloud_host/live.rs 与新的 private caller 模块，必要的 windows_workspace.rs additive concrete ownership（仅本草稿副本）。三份本规格与外部原始测试/patch/source census。

## 风险与待项
跨 LocalHost/HostAgent 改动是人工 HIGH/权限交叉可能 CRITICAL，即使索引 Rust LOW 或 UNKNOWN。必须验证 issuer 顺序、exact request/host、journal 排他寿命、legacy compatibility。Windows native、whole HCS、guest 调用和 output 仍无资格；F2/actor/source/CI 绑定未知。

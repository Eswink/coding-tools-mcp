# Offline-safe Connector Lifecycle — Project Plan

Status: ROUND 1 SYNTHETIC HARNESS COMPLETE; REAL-HOST VALIDATION DEFERRED; ROUND 2 DESIGN ACTIVE.  
Date: 2026-09-20  
Base: `main` @ `823cbdeba68bbdd832d93f4636f701ddb98474f1`  
Branch: `plan/offline-safe-connector-lifecycle`

## Problem statement

当前工作区的 MCP transport、OAuth endpoints、聊天授权和本地执行能力共享同一工作区运行时生命周期。用户停止本地工作区后，`stop_mcp_service` 会停止 listener，随后停止 tunnel；ChatGPT 侧因此只能观察到 endpoint 不可达、认证端点不可达或 transport failure，而无法区分“工作区有意离线”和“连接需要重新授权”。

这会造成两个产品问题：

1. 已安装但当前不使用该项目的 ChatGPT 会话可能看到“连接已过期 / 重新连接”类 UI。
2. 公司多人环境中，非当前项目操作者会被引导去点击重连，即使他们并不知道该项目，也不应参与本机授权。

本项目的既有会话隔离、exclusive lease、local approval、scope 和 draining 规则必须继续成立；本轮不能通过延长 token、放宽授权或暴露项目 metadata 来掩盖 transport 生命周期问题。

## Verified current code boundary

当前源码确认：

- `src-tauri/src/mcp/listener.rs`：同一个工作区 listener 同时承载 `/mcp`、OAuth discovery、`/oauth/authorize`、`/oauth/token`。
- `src-tauri/src/commands/runtime.rs::stop_mcp_service`：停止 MCP listener 后停止该工作区 MCP tunnel。
- `src-tauri/src/auth/session_policy.rs`：OAuth/chat duration 与本地聊天 lease 是独立策略。
- `src-tauri/src/auth/聊天授权v1.rs`：聊天绑定、exclusive owner、pending/active/revoked、draining 和 scope 只在请求到达服务端后生效。
- `src-tauri/src/mcp/server.rs`：tool schema 和 MCP instructions 当前把聊天授权错误作为 tool 层语义处理。

因此本轮的首要架构原则是：

> **Workspace execution offline MUST NOT automatically mean Connector transport/authentication disconnected.**

## Goals

1. 本地工作区停止时，优先让 ChatGPT 仍看到稳定、协议合法的 connector，而不是连接断裂。
2. 将 transport/authentication、workspace availability、chat authorization 三类状态拆开建模。
3. 未授权会话不能因为工作区 offline/locked 获知本地项目路径、owner、任务、机器名或其他项目 metadata。
4. 保留当前 exclusive conversation、refresh token、draining、durable task/recovery 的安全边界。
5. 通过真实 ChatGPT host 行为验证，而不是仅凭 Rust/HTTP 单测推断 UI 不再出现“重新连接”。
6. 所有结论都以当前代码、真实测试和可复查证据为准；失败不得改写为 PASS。

## Non-goals

- 不在本轮承诺隐藏 ChatGPT UI 中已安装 App 的名称或菜单项。
- 不把共享一个 OpenAI 登录账号解释为可靠的员工身份。
- 不通过永久 access token、无限 refresh token 或禁用 OAuth 修复 UX。
- 不动态改变已发布 tool schema 来模拟 offline。
- 不在 Round 1 未确认 host 行为之前直接部署远端 broker。
- 不在本计划阶段修改 release、installer、生产反向代理或公开部署。

## State model

### Connector transport state

```text
Available
Degraded
Unavailable
```

该状态描述 MCP/OAuth control surface 是否可达，不描述本地文件是否可执行。

### Workspace availability state

```text
Online
Starting
Offline
Draining
RecoveryRequired
```

### Chat authorization state

保持既有模型：

```text
Unauthorized
Pending
Active
Expired
Revoked
```

以及 owner phase：

```text
Free
Reserved
Active
Draining
```

三者必须正交。例如合法状态：

```text
Connector: Available
Workspace: Offline
Chat: Active

=> tool execution denied as WORKSPACE_OFFLINE
=> no OAuth reconnect challenge
=> no ownership transfer
```

## Progressive architecture ladder

本项目不预先锁死最终形态。按真实 host 证据逐层升级。

### Level A — Keep a lightweight control listener alive

最小改动候选：

- 工作区“停止执行”不再直接销毁 MCP/OAuth control listener。
- listener/tunnel 保留最小控制面；
- workspace executor 标记为 `Offline`；
- business tool 在 authorization 后返回稳定的 offline 语义；
- restart workspace 只恢复 execution plane。

如果真实 ChatGPT 验收确认这一层可以消除重连 UI，并且满足用户的“工作区关闭但桌面应用仍在”场景，则优先采用。

### Level B — Desktop background agent

如果关闭 Tauri UI 也必须维持 connector，则把 control listener / OAuth / presence 从窗口生命周期拆到常驻后台 agent；UI 仅负责管理。

### Level C — Always-on remote broker

只有在以下需求被正式确认时才进入：

- 电脑关机、休眠或断网期间 connector 仍必须在线；
- 多设备 workspace routing；
- 需要 server-side tenant/user entitlement。

远端 broker 不允许直接获得本地文件系统权限；本地执行仍由受控 agent 完成。

## Security and privacy invariants

1. OAuth authentication 与 local chat approval 不得合并。
2. `openai/session` 继续作为 chat binding，不提升为员工身份。
3. 非 owner 不创建新的 pending、fingerprint、桌面通知或 owner metadata。
4. Offline response 不得泄露 workspace path、project name、host name、running task、owner identity。
5. 如果调用者没有 workspace entitlement，则未来多租户层应优先返回 non-disclosing semantics；不得把项目存在性作为错误细节泄露。
6. Refresh 不续期 chat lease，不获得 owner，不恢复 local approval。
7. Offline -> Online 不自动恢复已失效/revoked chat grant。
8. 任何新 control plane 都不得绕过 existing execution fence / draining。
9. 所有新错误码必须明确区分 OAuth failure 与 business availability failure，避免错误触发登录挑战。

## Five-round execution plan

### Round 1 — Host behavior reproduction and classification

Objective: 先确认“重新连接”由哪些 transport/OAuth/MCP 条件触发。

Deliverables:

- failure-first reproduction；
- 至少 10 个 host behavior cases；
- HTTP/OAuth/MCP trace；
- ChatGPT UI observation；
- local/tunnel logs；
- 对每个 case 标注是否出现 reconnect、是否要求 OAuth、是否下一轮仍可调用。

Required cases:

| Case | MCP | OAuth token endpoint | Credential | Expected investigation |
|---|---|---|---|---|
| C1 | online | online | valid | baseline |
| C2 | unreachable | unreachable | valid | current stop behavior |
| C3 | 503 | online | valid | transport failure classification |
| C4 | online + typed offline result | online | valid | desired business-offline candidate |
| C5 | online | offline | access expired | refresh endpoint failure |
| C6 | online | online | access expired + refresh valid | refresh baseline |
| C7 | online | online | refresh rejected | auth reconnect control |
| C8 | connection reset | online | valid | network interruption |
| C9 | online | online | chat unauthorized | local-approval baseline |
| C10 | online | online | exclusive locked | non-owner baseline |

Hard gate:

> Original gate superseded on 2026-09-20: real-host C1-C10 is deferred because the setup cost is high. Round 2 design may proceed using the verified architectural coupling and synthetic harness. This does **not** convert host behavior into a proven fact, and Round 5 real-host acceptance remains mandatory before release/final PASS.

### Round 2 — Availability contract and control/execution separation design

Objective: 根据 Round 1 证据冻结协议语义和内部状态机。

Deliverables:

- `WorkspaceAvailability` contract；
- typed tool error/result contract；
- transport/auth/business error taxonomy；
- migration impact；
- observability fields；
- threat model；
- exact call-chain impact review before editing symbols。

Decision gate:

- Provisional implementation target: **Level A**, because it is the smallest reversible change that separates connector reachability from workspace execution availability.
- Level A remains a hypothesis until Round 5 real-host validation proves the target reconnect UX is eliminated.
- If the product later requires the connector to survive desktop-process exit, move to Level B.
- Only if the connector must survive machine shutdown/sleep/network loss should Level C be evaluated.

### Round 3 — Minimal control-plane implementation

Objective: 实现通过 Round 2 选定的最小架构，不提前上更重方案。

Expected Level A implementation boundary:

- split listener lifecycle from execution availability；
- keep OAuth discovery/token route stable while execution is intentionally offline；
- introduce availability gate before business dispatch；
- preserve stable tools/list schema；
- stop/start workspace becomes execution state transition；
- tunnel lifetime follows control-plane policy, not blindly follows executor state；
- local desktop exposes explicit “Connector online / Workspace offline” state。

Required tests:

- listener survives executor stop；
- OAuth refresh remains valid while workspace offline；
- chat owner unchanged by offline/online；
- business tools return offline semantic with no OAuth challenge；
- pending/locked behavior unchanged；
- startup/restart/shutdown races；
- tunnel failure remains distinguishable from intentional offline.

### Round 4 — Multi-user privacy and tenancy hardening

Objective: 让公司多人环境中的错误行为最小化，并明确哪些问题必须依靠 ChatGPT workspace access controls。

Deliverables:

- non-disclosing error contract；
- no metadata leak regression；
- owner/non-owner/offline cross-product tests；
- optional connector installation/user entitlement abstraction if product requirements demand it；
- document limitation for shared OpenAI account vs distinct workspace members。

Hard gate:

> 不能以“所有同事都能看到同一个 connector 但不会点它”作为安全假设。

### Round 5 — End-to-end hardening and acceptance

Objective: 五轮完成后才能判断问题是否解决。

Required scenarios:

1. workspace online -> offline -> online；
2. active chat during offline；
3. unrelated chat during offline；
4. non-owner 100 repeated calls；
5. access token refresh while offline；
6. tunnel restart / network flap；
7. UI close/reopen；
8. app process restart；
9. long-running task enters draining before offline/release；
10. recovery-required fence；
11. Windows installed build；
12. Ubuntu installed build；
13. real ChatGPT connector observation；
14. no secret/project metadata in logs/screenshots/evidence。

Final acceptance:

- intentional workspace offline no longer produces the target reconnect UX in the supported lifecycle scenario;
- OAuth failure still correctly requests reconnect;
- unauthorized/foreign chat gets no project-specific information;
- existing exclusive/draining/refresh tests stay green;
- documentation states remaining host-controlled or account-sharing limitations.

## Issue-style workflow

GitHub Issues is currently disabled for this repository, so until repository settings change, issues are represented as English-named tracked spec files under this directory.

Lifecycle:

```text
OPEN
  -> REPRODUCED
  -> ROOT_CAUSE_CONFIRMED
  -> DESIGN_FROZEN
  -> IMPLEMENTED
  -> REVIEWED
  -> HOST_VALIDATED
  -> DONE
```

If a verification fails:

```text
TEST_FAILED
  -> record exact evidence
  -> revise one hypothesis/change
  -> rerun bounded test
```

Do not use “retry until green” as a substitute for diagnosis.

## Initial issue set

- ISSUE-001 — Host reconnect classification and failure-first reproduction.
- ISSUE-002 — Workspace availability contract and error taxonomy.
- ISSUE-003 — Decouple connector control plane from workspace execution lifecycle.
- ISSUE-004 — Non-disclosing multi-user access boundary.
- ISSUE-005 — Offline-safe end-to-end and installed acceptance.

ISSUE-001 remains evidence-incomplete for real-host behavior, but its host gate is explicitly deferred. ISSUE-002 may proceed for protocol/state design; production implementation remains provisional until required impact analysis and later real-host acceptance.

## Code areas expected to be affected after Round 1

Potential, not yet authorized implementation set:

- `src-tauri/src/mcp/listener.rs`
- `src-tauri/src/mcp/server.rs`
- `src-tauri/src/commands/runtime.rs`
- `src-tauri/src/runtime/supervisor.rs`
- `src-tauri/src/tunnel/supervisor.rs`
- `src-tauri/src/auth/聊天授权v1.rs` only if availability handling requires explicit interaction
- workspace runtime models / DTOs
- Svelte workspace status UI
- HTTP/integration/native acceptance fixtures

Before editing any symbol, run the repository-required impact analysis. HIGH/CRITICAL blast radius must be surfaced before implementation.

## Observability requirements

Every relevant request/transition should be diagnosable without secrets:

- workspace_id or non-sensitive stable internal id;
- connector control state;
- workspace availability;
- chat authorization outcome class;
- OAuth outcome class without token values;
- HTTP/MCP method;
- error code;
- tunnel state;
- transition reason;
- timestamp and revision.

Never log:

- access/refresh tokens;
- OAuth password/client secret;
- local authorization password;
- raw `openai/session`;
- workspace path unless explicitly needed in local-only diagnostic evidence;
- user source content.

## Rollback

Round 3+ implementation must support a bounded rollback:

- restore current listener/executor coupling;
- do not delete OAuth refresh families or history to rollback;
- do not migrate project data destructively;
- preserve config schema compatibility where possible;
- a failed candidate must not replace the current release.

## Evidence policy

A round is complete only when its evidence is recorded in `iterations.md`.

Evidence entries include:

- exact branch/commit;
- exact command or host action;
- expected behavior;
- observed behavior;
- PASS / FAIL / BLOCKED;
- remaining uncertainty;
- next gate.

Rust/unit test success alone is not sufficient for a ChatGPT-host interoperability claim.


## Gate amendment — 2026-09-20

Real ChatGPT host testing is intentionally deferred for now because the dedicated test connector/public-route setup is operationally expensive.

This changes sequencing, not truth status:

- synthetic harness evidence is accepted as sufficient to start Round 2 design;
- reconnect trigger remains `UNCONFIRMED_ON_REAL_HOST`;
- Level A is selected only as the minimal reversible design hypothesis;
- no release may claim the reconnect bug fixed until Round 5 real-host acceptance is executed;
- OAuth weakening, token-TTL workarounds, or host-behavior claims remain prohibited without evidence.

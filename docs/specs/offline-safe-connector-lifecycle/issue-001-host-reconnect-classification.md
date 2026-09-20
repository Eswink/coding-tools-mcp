# ISSUE-001 — Host reconnect classification and failure-first reproduction

Status: OPEN  
Parent plan: [plan.md](plan.md)  
Round: 1 / 5  
Implementation changes: NOT AUTHORIZED BY THIS ISSUE

## Problem

当前用户可观察到：本地工作区停止后，ChatGPT 侧的 connector 可能显示“连接已过期 / 重新连接”。现阶段只能确认当前实现会同时撤掉工作区 MCP listener 和 tunnel；还不能把具体 UI 归因到某一个 HTTP status、OAuth refresh failure 或 MCP protocol failure。

本 Issue 的任务是把该现象从“产品感觉”转化成可重复、可分类、可回归的 host behavior contract。

## User impact

- 项目 owner 停止本地工作区后，未来继续使用可能需要额外重连。
- 非项目同事在其他 ChatGPT 会话中可能被无意义的重连 UI 干扰。
- 现有 local authorization/exclusive lease 无法处理请求根本到不了服务端的情况。
- 如果直接在未分类状态下修改 OAuth 或 token TTL，可能缓解一个表象但扩大授权风险。

## Current behavior

已核对源码：

1. `mcp/listener.rs` 将 MCP 和 OAuth endpoints 放在同一个 per-workspace listener。
2. `commands/runtime.rs::stop_mcp_service` 停 listener 后停止 MCP tunnel。
3. 因此 intentional workspace stop 会造成远端 endpoint 消失。
4. Chat authorization 仅在 endpoint 可达并处理请求后生效。

## Expected outcome of this issue

不是“修复 reconnect”，而是得到一个可复查答案：

> 哪些 transport/OAuth/MCP 条件会触发 ChatGPT reconnect UI；哪些条件可以表达 workspace intentionally offline 而不被 host 视为 auth/connector failure？

## Invariants

- 不修改 production OAuth 安全策略。
- 不延长 token TTL。
- 不关闭认证。
- 不伪造 PASS。
- 不把本地 synthetic MCP client 结果冒充真实 ChatGPT host 结果。
- 不让本测试向日志输出真实 secret/token。
- 不创建新的 non-owner pending request。

## Test matrix

| ID | Endpoint condition | OAuth condition | Chat condition | Evidence target |
|---|---|---|---|---|
| C1 | MCP reachable | token endpoint reachable, credential valid | approved | healthy baseline |
| C2 | MCP unreachable | token endpoint unreachable | existing credential | current intentional stop analogue |
| C3 | MCP returns HTTP 503 | OAuth remains reachable | existing credential | transport-level unavailable |
| C4 | MCP remains protocol-valid; tool call returns typed workspace-offline semantic | OAuth reachable | approved | desired candidate semantics |
| C5 | MCP reachable | token endpoint unreachable after access expiry | approved before expiry | refresh endpoint failure |
| C6 | MCP reachable | refresh succeeds | approved | refresh baseline |
| C7 | MCP reachable | refresh rejected | approved | auth reconnect control |
| C8 | connection reset / abrupt close | OAuth reachable | approved | network interruption |
| C9 | MCP/OAuth reachable | valid OAuth | chat unauthorized | local approval baseline |
| C10 | MCP/OAuth reachable | valid OAuth | different chat blocked by exclusive owner | non-owner baseline |

Where feasible, add:

- C11: `tools/list` reachable but one business tool unavailable.
- C12: listener reachable, tunnel transiently restarted.
- C13: workspace goes offline after a long-running task enters draining.

## Required evidence per case

Record all of the following:

- case ID;
- exact server build/commit;
- exact public endpoint type without secret URL parameters;
- access token freshness class (valid / expired / refreshable / rejected), never token value;
- HTTP status;
- MCP JSON-RPC result/error class;
- OAuth request sequence;
- local MCP request log excerpt sanitized;
- tunnel state;
- ChatGPT UI observation;
- whether reconnect button appears;
- whether a new OAuth login is requested;
- whether next-turn tool invocation is possible;
- whether a second chat is affected;
- timestamp.

## Harness requirements

Prefer a deterministic fault-injection layer rather than editing production branches for each case.

Candidate approaches:

1. small local HTTP fault proxy between public tunnel and MCP listener;
2. test-only listener mode with allowlisted injected behavior;
3. reverse proxy rules in an isolated test profile.

Do not add arbitrary command execution or arbitrary response injection to production builds.

## Failure-first requirement

Before any fix:

1. reproduce C1 as healthy baseline;
2. reproduce the user's current stop flow as C2;
3. capture the reconnect UI if reproduced;
4. capture HTTP/tunnel/OAuth evidence that distinguishes it from C1.

If C2 cannot reproduce reliably, mark BLOCKED and investigate timing/token state; do not move to Round 2.

## Review questions

After C1-C10:

1. Does a normal MCP business error keep the connector connected?
2. Does HTTP 503 alone trigger reconnect?
3. Is the reconnect card tied specifically to OAuth refresh failure?
4. Does endpoint unreachability immediately trigger UI, or only after token expiry/next use?
5. Can control endpoints stay reachable while execution is offline without misleading the host?
6. Does a second chat cause any OAuth challenge when the first chat owns the workspace?
7. Does ChatGPT distinguish auth failure from non-auth business failure?
8. Are retries host-generated, model-generated, or both?

## Acceptance criteria

ISSUE-001 can move to `ROOT_CAUSE_CONFIRMED` only when:

- C1 and C2 are reproduced with exact evidence;
- C3/C4/C5/C6/C7 have real host observations or an explicit documented blocker;
- the reconnect trigger is narrowed to one or more concrete failure classes;
- at least one candidate offline representation is identified or proven unavailable;
- no security invariant was weakened to obtain the result.

It reaches `DONE` only after the evidence is reviewed and Round 2 inputs are frozen.

## Output

Update:

- `iterations.md` with each executed case;
- `tasks.md` checkboxes;
- this file's Status;
- create ISSUE-002 only after this issue's hard gate.

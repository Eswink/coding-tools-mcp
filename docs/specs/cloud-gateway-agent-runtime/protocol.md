# Versioned Gateway protocol laboratory

Source pin/date: MCP 2026-07-28 and legacy 2025-11-25 / 2025-06-18, reviewed 2026-09-21. See [references.md](references.md). This is a limited synchronous tool-profile experiment, **not complete MCP conformance**.

## Modern subset

Every request includes `params._meta["io.modelcontextprotocol/protocolVersion"]` and object `clientCapabilities` under the same prefix. HTTP `MCP-Protocol-Version`, `Mcp-Method` and (for tool calls) `Mcp-Name` mirror body values. Decode the standard Base64 sentinel for Mcp-Name before comparison. Missing/malformed/duplicate/mismatching headers fail with HTTP 400 / -32020. Unsupported versions use HTTP 400 / -32022 with `data.supported` and `data.requested`.

`server/discover` returns `resultType: complete`, `supportedVersions`, `capabilities.tools`, and `_meta["io.modelcontextprotocol/serverInfo"]`. `tools/list` and `tools/call` also carry `resultType: complete`; legacy envelopes do not. Unknown modern method returns HTTP 404 / -32601. GET/DELETE return 405; no protocol-session header is created or echoed. Legacy session headers are ignored for modern requests, never used as authority.

## Legacy subset

`initialize` negotiates either supported legacy revision and reports `protocolVersion`, `serverInfo`, tools with listChanged false. `notifications/initialized` is accepted with 202. No SSE notification delivery is advertised. Subsequent calls use the negotiated version header; this lab intentionally does not support pre-2025-06-18 headerless clients or the old separate SSE transport. Modern metadata mixed into a legacy request is rejected instead of downgrading checks.

## Business contract

`auth_status` is control-plane only. `request_chat_authorization` may return a synthetic existing grant, or `CHAT_AUTHORIZATION_UNAVAILABLE` when a new request cannot be accepted. It never issues remote approvals. The only lab business tool is `workspace_probe`: it returns fixed synthetic success data while online, not a real file/command result.

Authenticated request ordering:

```text
valid context -> recovery -> exclusive owner -> active grant -> scope -> availability -> fixture dispatch
```

| Condition | HTTP / MCP | OAuth challenge |
|---|---|---|
| Valid owner, offline before dispatch | 200 / result.isError=true, WORKSPACE_OFFLINE | absent |
| Unknown result after admitted work | 200 / result.isError=true, EXECUTION_OUTCOME_UNKNOWN | absent |
| Foreign/unauthorized/scope/recovery | 200 / non-disclosing permission tool error | absent |
| Missing/invalid bearer fixture | 401 | present (lab bearer, not OAuth endpoint) |
| Invalid JSON / request shape | 400 / protocol error | absent |
| Foreign/duplicate Host or Origin | 403 | absent |

No request is automatically retried. The lab tests error classification only; it does not claim durable idempotency, real agent transport, at-most-once distributed execution or cancellation. Those remain ISSUE-019..021 gates.

## HTTP limits

Loopback IPv4 only; explicit lab opt-in. POST /mcp with application/json and Accept covering application/json and text/event-stream. Bound body to 64 KiB, total read time to 5 seconds, 64 concurrent sockets, headers to 16 KiB. Fail oversized/bad-encoding bodies generically. Do not log headers, body, raw session, exception text or upstream URLs. Cache-Control no-store for lab responses. No public launch mode, proxy forwarding, filesystem or child-process access.

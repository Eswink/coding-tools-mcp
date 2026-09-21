# Cloud Gateway protocol laboratory

**NON-PRODUCTION. SYNTHETIC IDENTITY AND WORKER. LOOPBACK ONLY.**

This first increment provides executable wire contracts for the future cloud
Gateway, not a deployable service. It reads no workspace files, runs no commands,
uses no real OAuth credentials, and never forwards traffic to a workstation.
The existing Tauri/Rust application is unchanged.

## Run the contract suite

Requires Node.js 22 (standard library only; no npm install):

```sh
node --test tests/cloud-gateway/*.test.mjs
```

Tests use actual local HTTP sockets plus a separately spawned lab process. They
cover modern and legacy envelopes, consistent header/body routing, authority and
Origin checks, offline/authorization ordering, bounded requests and fixture state.
They **do not** test real OAuth refresh, signed device identity, durable execution,
production security, native sandboxing, or ChatGPT's reconnect UI.

## Manual local protocol inspection

Set `MCP_LAB_TOKEN` in your local shell to a newly generated **synthetic** token
(32–256 URL-safe characters). Never copy a production OAuth/device secret here.

Ubuntu:

```sh
export MCP_LAB_TOKEN="$(node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))")"
node prototypes/cloud-gateway/cli.mjs --lab --port 28769
```

Windows PowerShell:

```powershell
$env:MCP_LAB_TOKEN = node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
node prototypes/cloud-gateway/cli.mjs --lab --port 28769
```

The program prints a loopback endpoint, never the token. The default synthetic
workspace is offline with a preapproved fixture conversation named `lab-owner`.
`--online-fixture` returns only a fixed synthetic probe success. It does not turn
on any local execution. The API has no approval, presence-control or agent routes.

Use `Authorization: Bearer <synthetic token>` and `Accept: application/json,
text/event-stream`. Modern POSTs additionally require `MCP-Protocol-Version`,
`Mcp-Method`, and `Mcp-Name` for tool calls, consistent with request metadata.
See [the versioned contract](../../docs/specs/cloud-gateway-agent-runtime/protocol.md)
and `tests/cloud-gateway/helpers.mjs` for complete requests.

## Limits and unsupported capabilities

The lab binds only `127.0.0.1`; there is intentionally no public bind mode. It
accepts only matching local Host/Origin, caps headers at 16 KiB and bodies at
64 KiB, has a 5-second body-read deadline and 64-socket cap. It emits no payload
logs and uses no-store responses. This is not a production DoS audit.

Only `server/discover` (modern), `initialize`/`ping`/initialized notification
(legacy), `tools/list` and `tools/call` are implemented. No SSE streaming,
subscriptions, MRTR, resource/prompts API, durable protocol sessions, device WSS,
OAuth endpoints or production worker are advertised. `supportedVersions`
identifies this implemented synchronous tool profile, not a full conformance
certification. The fixture authorization has conservative ownership retention;
it does not simulate actual process draining or cross-restart grant persistence.

Do not publish this endpoint through FRP/Cloudflare, point a company ChatGPT
connector at it, or use it as a deployment image. Production replacement depends
on [the issue register](../../docs/specs/cloud-gateway-agent-runtime/issues.md).

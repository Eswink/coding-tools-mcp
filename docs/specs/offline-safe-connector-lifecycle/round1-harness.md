# Round 1 Host Fault Harness

Status: READY FOR CI CONTRACT VALIDATION; real ChatGPT host observations are still required.

## Purpose

This harness supports ISSUE-001 without changing production MCP/OAuth behavior. It sits between a test-only public connector route and the real local MCP listener.

The harness is deliberately allowlisted. It cannot execute commands, modify workspace files, change application configuration or emit arbitrary response bodies.

## Safety boundary

Use a dedicated test workspace and a dedicated ChatGPT test connector/hostname. Do not route a company-shared production connector through this harness.

The harness:

- never logs Authorization headers;
- never logs OAuth form bodies;
- never logs MCP request bodies;
- records only mode, method, sanitized path, byte counts, injected outcome and upstream status;
- caps request/response bodies at 2 MiB;
- accepts only HTTP/HTTPS upstreams without embedded credentials;
- passes OAuth endpoints through except in the two explicit OAuth fault modes.

## Modes

| Mode | ISSUE-001 case | Behavior |
|---|---|---|
| `pass` | C1 / C6 | transparent baseline |
| `mcp-503` | C3 | only `/mcp` returns HTTP 503; OAuth remains reachable |
| `workspace-offline` | C4 | protocol remains reachable; non-auth business `tools/call` returns typed `WORKSPACE_OFFLINE` |
| `reset-mcp` | C8 | only `/mcp` is abruptly closed; OAuth remains reachable |
| `oauth-token-503` | C5 | only `POST /oauth/token` returns HTTP 503 |
| `oauth-refresh-reject` | C7 | only refresh-token grants return OAuth `invalid_grant`; authorization-code exchange still passes through |

C2 uses the current product stop flow directly. C9/C10 use the real authorization/exclusive behavior directly.

## Local topology

Example only:

```text
real MCP listener       127.0.0.1:28766
fault proxy             127.0.0.1:28767
test-only tunnel/route  -> 127.0.0.1:28767
ChatGPT test connector  -> https://test-host.example/mcp
```

The workspace's advertised public origin must match the test connector origin so OAuth issuer/resource metadata remain coherent. Use an isolated test profile/hostname; do not rewrite the shared production connector.

## Run

From repository root:

```bash
python scripts/connector_fault_proxy.py \
  --listen-port 28767 \
  --upstream http://127.0.0.1:28766 \
  --mode pass \
  --evidence evidence/round1-c1.jsonl
```

Change only `--mode` and the evidence filename between controlled cases. Restart the proxy between cases so each observation has a single unambiguous mode.

## Pre-host validation

```bash
python -m py_compile scripts/connector_fault_proxy.py scripts/connector_fault_proxy_tests.py
python scripts/connector_fault_proxy_tests.py
```

These tests validate proxy behavior only. They are not evidence of ChatGPT UI behavior.

## Host observation record

For every real ChatGPT run record:

- exact candidate commit;
- case ID and proxy mode;
- time window;
- access-token freshness class only, never token bytes;
- MCP/OAuth HTTP outcome;
- whether reconnect UI appeared;
- whether OAuth login was requested;
- whether next-turn invocation remained possible;
- whether an unrelated chat was affected;
- sanitized proxy evidence file digest.

Do not place secrets, callback query codes, raw session metadata or local workspace paths in committed evidence.

## Hard gate

Round 1 remains open until C1/C2 are reproduced and C3/C4/C5/C6/C7 are observed in the real ChatGPT host or explicitly documented as blocked.

Passing this harness's unit tests does not authorize Round 2 or a production implementation.

# Deferred Real-Host Acceptance Procedure

Status: PREPARED, NOT EXECUTED  
Date: 2026-09-20

This procedure is intentionally separated from ENGINEERING_CANDIDATE_PASS. It exists so the real ChatGPT validation can be run later without redesigning the experiment.

## Preconditions

Use an isolated test setup only:

```text
real MCP listener       127.0.0.1:28766
fault proxy             127.0.0.1:28767
dedicated public route  -> 127.0.0.1:28767
ChatGPT test connector  -> dedicated test origin
```

Do not point a company-shared connector at the fault proxy.

The advertised public origin must match the dedicated test connector origin so OAuth issuer/resource metadata stay coherent.

## Harness startup

From repository root:

```bash
python -m py_compile scripts/connector_fault_proxy.py scripts/connector_fault_proxy_tests.py
python scripts/connector_fault_proxy_tests.py

python scripts/connector_fault_proxy.py \
  --listen-port 28767 \
  --upstream http://127.0.0.1:28766 \
  --mode pass \
  --evidence evidence/round5-host-c1.jsonl
```

Restart the proxy between cases.

## Required sequence

1. C1 — pass: healthy MCP/OAuth/approved chat baseline.
2. C2 — hard stop: current connector hard-stop behavior.
3. C3 — mcp-503: transport unavailable while OAuth remains reachable.
4. C4 — workspace-offline / real Level A pause: control plane online, business execution unavailable.
5. C5 — oauth-token-503 after access expiry.
6. C6 — successful refresh baseline.
7. C7 — oauth-refresh-reject.
8. C8 — reset-mcp.
9. C9 — valid OAuth, chat unapproved.
10. C10 — valid OAuth, foreign chat while another chat owns workspace.
11. Online -> Offline -> Online through the new desktop pause/resume UI.
12. Close/reopen the desktop UI while the connector remains in the supported lifecycle.
13. Restart the application process.
14. Controlled tunnel/network interruption and recovery.

## Per-case record

Record only:

- case id;
- candidate commit;
- proxy mode;
- start/end timestamp;
- credential freshness class, never token bytes;
- HTTP/MCP/OAuth outcome class;
- reconnect button/card visible: yes/no;
- OAuth login requested: yes/no;
- next-turn tool invocation possible: yes/no;
- unrelated chat affected: yes/no;
- sanitized evidence file SHA-256.

Never commit access/refresh tokens, authorization codes, OAuth secrets, raw openai/session, workspace paths, or user source content.

## Required conclusions

For the supported Level A lifecycle, the target observation is:

```text
Connector control plane: reachable
Workspace execution: Offline
Approved owner business call: WORKSPACE_OFFLINE
OAuth challenge/reconnect UI: absent
Foreign chat: existing generic authorization/exclusive denial
```

A real OAuth failure such as rejected refresh should still produce the host's authentication/reconnect behavior. If C4 and C7 look identical in the host UI, Level A has not proven the target UX distinction.

## Shared-account observation

Use only a deliberately shared test account/workspace arrangement approved for this test. Record connector visibility and invocation behavior separately from server-side confidentiality. Do not infer employee identity from openai/session or from a shared OpenAI login.

## Completion rule

Only after this procedure is executed may ISSUE-005 move from ENGINEERING_CANDIDATE_PASS to HOST_VALIDATED / DONE.

Until then, use the exact truth label:

```text
UNCONFIRMED_ON_REAL_HOST
```

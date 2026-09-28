# Threat model and release blockers

Status: design baseline; no claim of a production security audit.

| Threat | Required mitigation | Evidence gate |
|---|---|---|
| Foreign chat infers workspace/owner/presence | Auth/recovery/exclusive/scope before availability; generic denials and non-sensitive catalog | Same denied body across online/offline, no fingerprints/paths/task IDs |
| Stolen/replayed device identity | One-time short enrollment, device-generated key, cloud binding confirmation, key rotation/revocation | Replay, wrong tenant/device, expiry and revocation tests before WSS production |
| Gateway ticket substitutes for local approval | Agent local grant and policy ceiling; ticket bound to canonical args hash, scope, device, request and epochs | Missing/revoked local grant always denied even with valid cloud signature |
| Gateway fully compromised | Explicit trusted relay boundary; no local privilege escalation; least-privilege grants, local sandbox, auditable revoke | Document residual risk: can abuse already authorized scope without end-to-end user intent proof |
| Duplicate mutation on retry | Durable request identity/digest, terminal-result retrieval; unknown means no replay | Drop response before/after durable admission and completion, reconnect same ID |
| Offline owner replaced while child task still alive | Durable execution fence, draining, local recovery acknowledgement | Power/network loss + replacement owner forbidden |
| Stale device socket disconnects replacement | Monotonic/fresh connection generation; compare before clear/route | Old close/late reply cannot affect new generation |
| SSRF / alternate routing | No caller-chosen upstream URL; one opaque connector mapped to enrolled device | Reject URL/host/path overrides and redirects on device channel |
| Token/session/code in diagnostics | Allowlisted structured event fields, body logging off, encrypted secrets/backups, bounded retention | Canary scans of logs, database and exported evidence |
| Host/Origin/header smuggling | Canonical TLS origin, explicit trusted-proxy topology, duplicate-header rejection, header/body equality | Foreign/stale/malformed/duplicate headers; no trust in arbitrary X-Forwarded-Host |
| Public approval flooding | New approval only while enabled online local operator is available; quotas and deduplication | Offline creates zero pending notifications |
| Prompt injection via repository files/hooks | Guidance is data; locally trusted config only, approvals cannot be model-generated | Hook/script arguments through same policy and sandbox |
| Sandbox label overstates enforcement | Report policy-only vs actual kernel mechanism; fail closed unsupported policy | Native Windows/Ubuntu filesystem/network escape-negative tests |
| VPS crash/restore revives revoked authority | Durable OAuth state and monotonic revoke reconciliation; unknown local state blocks execution | Restore clean target; still-valid auth separate from execution authority |

## First increment safety boundary

The lab uses a test-only bearer credential and synthetic principal. It is **not OAuth** and cannot be exposed publicly or connected to user files. Local-admin fixture setters exist only as imported JavaScript functions; no HTTP endpoint changes state or approves a chat. No secret/payload logging; no browser CORS opt-in. HTTP resource limits are defense in depth, not a production DoS certification.

## Production hard blockers

Real OAuth/PKCE/resource validation; enrollment and device authentication; local signed approval verification; durable fencing/deduplication; security review; target TLS/proxy topology; actual host response classification. None is waived by a green lab.

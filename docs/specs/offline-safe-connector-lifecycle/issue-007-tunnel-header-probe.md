# ISSUE-007 Tunnel Header Topology Probe

Status: READY FOR LOCAL / TUNNEL OBSERVATION  
Purpose: gather the missing Host / HTTP authority evidence without using ChatGPT.

## Why this exists

ISSUE-007 intentionally blocks production Host enforcement until supported tunnel modes are observed.

The probe uses the same Axum/hyper stack family as the product listener, but it is a standalone example binary. It does not read workspace state, OAuth credentials, sessions, request bodies, query strings, or user content.

It prints one sanitized JSON line per request containing only:

- HTTP version and method;
- URI authority hostname, when the HTTP stack exposes one;
- Host-header hostname;
- booleans indicating whether Origin, X-Forwarded-Host, Forwarded, X-Forwarded-Proto, and cf-ray are present.

It deliberately does **not** print forwarded-header values.

## Compile

```bash
cargo check --locked --manifest-path src-tauri/Cargo.toml --example tunnel_header_probe
```

## Run

```bash
cargo run --locked --manifest-path src-tauri/Cargo.toml --example tunnel_header_probe -- --port 28768
```

The probe binds only:

```text
127.0.0.1:28768
```

Do not bind it to a public interface.

## Direct-local baseline

```bash
curl -sS http://127.0.0.1:28768/mcp
curl -sS -H 'Host: localhost:28768' http://127.0.0.1:28768/mcp
```

Record the JSONL output as the direct-local baseline.

## FRP observation

Create a **temporary test route** targeting local port 28768 using the same FRP transport mode that the real workspace uses.

Check separately where applicable:

```text
FRP HTTP fixed domain
FRP HTTP subdomain
FRP HTTPS + https2http
```

Send one GET to the temporary public URL and record the sanitized probe line.

Do not reuse a company-shared production route.

## Cloudflare observation

### Quick Tunnel

For an isolated test only:

```bash
cloudflared tunnel --url http://127.0.0.1:28768
```

Send one GET through the generated `*.trycloudflare.com` URL.

### Named Tunnel

Use a dedicated test hostname/ingress rule that targets the probe port, then send one GET.

This is the important check for remotely configured `httpHostHeader`.

## Evidence table

Record only:

| Mode | HTTP version | URI authority host | Host header host | XFH present | Forwarded present | Result |
|---|---|---|---|---|---|---|
| direct localhost | | | | | | |
| FRP HTTP fixed domain | | | | | | |
| FRP HTTP subdomain | | | | | | |
| FRP HTTPS + https2http | | | | | | |
| Cloudflare Quick | | | | | | |
| Cloudflare Named | | | | | | |

Public test hostnames may be recorded. Do not record credentials, authorization headers, cookies, query strings, workspace identifiers, or user content.

## Decision gate

Production Host / :authority enforcement remains blocked until the table shows the legitimate target seen by the listener for every supported tunnel mode that the product intends to preserve.

If a mode rewrites Host to loopback, do **not** recover identity from X-Forwarded-Host. The security policy must allow the actually observed trusted target while continuing to derive OAuth/public identity from the configured PublicOrigin.

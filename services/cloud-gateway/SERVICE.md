# Standalone identity service — Issue #42

This executable serves OAuth metadata, browser owner login/consent, token exchange,
and two generic health endpoints. It is **not yet a functional MCP execution Gateway**.
No Agent, workspace filesystem, remote shell, or remote administrator endpoint exists.
Do not replace the existing ChatGPT connector or deploy the old render-only Compose
blueprint based on this increment.

## Build and commands

```sh
cargo build --locked --manifest-path services/cloud-gateway/Cargo.toml --bin coding-tools-gateway
coding-tools-gateway --help
coding-tools-gateway check-config --config /absolute/private/config.json
```

Configuration uses the fields below. All identifiers are example placeholders, NOT
provisioned accounts. Use locally generated identifiers and an audited registered
callback. Unknown/duplicate fields, noncanonical HTTPS identity, public binds and
privileged ports fail. Port zero is supported only as an explicit ephemeral test choice.

```json
{
  "origin": "https://gateway.example.invalid",
  "prefix": "/coding-tools",
  "connector": "00000000-0000-0000-0000-000000000001",
  "owner_subject": "00000000-0000-0000-0000-000000000002",
  "client_id": "explicitly-registered-client",
  "redirect_uri": "https://client.example.invalid/registered-callback",
  "client_authentication": "public",
  "bind": "127.0.0.1:28880"
}
```

A secret packet contains `database_url` and `identity_key` (32 cryptographically
random bytes encoded as unpadded base64url; no default). Only owner provisioning or
rotation packets contain `password` (16..1024 bytes). Only confidential-client
registration packets contain `client_secret` (32..512 bytes). Secrets are never
arguments and environment credential defaults are ignored. No command prints them.

Each stateful command requires `--config` and exactly one of `--secrets-stdin` or
`--secrets-file /absolute/protected/file.json`. Stdin must be a pipe, not a terminal;
use an approved secret manager/private file as its producer, not a shell literal in
history. Unix config and secret files must be owner-only regular files (0600/0400),
with one hard link, no symlink, and a non-group/world-writable containing directory.
Use a private 0700 directory. Input is capped at 16 KiB. Other same-UID code is trusted:
this loader is not an OS sandbox and does not protect against privileged host compromise.
Windows secret-file input deliberately rejects until native ACL validation exists;
use explicit non-terminal stdin there. Windows public config integrity is the local
operator's responsibility. No claim of native Windows installed acceptance is made.

## Lifecycle sequence

1. `migrate`: explicitly apply embedded additive migrations and bind immutable identity.
2. `provision-owner`: create once. Duplicate owner creation fails; never overwrites.
3. `register-client`: create once. Duplicate ID fails; mode/callback changes require review.
4. `serve`: validates current migration ledger, identity key, owner and registered client
   before binding. It does not auto-migrate or auto-provision anything.
5. `rotate-owner --expected-epoch N`: explicit CAS rotation, invalidates affected browser
   flows and OAuth token families; never permits a caller-selected remote subject.

Configuration/credential errors produce fixed JSON classes without paths, DSNs or
credentials. The service prints only readiness/listen mode and a graceful-stop marker.
No request/body/SQL tracing subscriber is installed. Ingress proxy/WAF/OS logs are a
separate trust boundary; ensure they do not record credential-bearing URLs or bodies.

## Limits and health

The first service profile accepts loopback HTTP/1 only behind a trusted TLS proxy:
64 simultaneous connections, 64 requests per one-second window, 32 headers, 16 KiB
header buffer, 5-second header deadline, 10-second maximum connection lifetime, and
no persistent HTTP/1 keepalive. Existing identity handlers bound bodies to 8 KiB and
work to 5 seconds. SQL acquisition/statement/lock waits are bounded. Authentication
failure remains an authentication error, not a fabricated successful tool result.
Generic `/coding-tools/health/live` survives DB failure; `/coding-tools/health/ready`
reports DB/provisioning readiness without owner/credential details. All routes enforce
configured Host/Origin. SIGINT/SIGTERM drain connections with a bounded grace period.
Limits are containment; audited per-source ingress limits are still required. This
HTTP identity profile is not the future streaming Agent/MCP transport profile.

## Deployment boundary

Host-loopback service validation does not validate a Docker bridge listener. The
existing Compose renderer is still a blueprint; container-private binding, image
hardening, actual Engine isolation, TLS/WAF routing and rollback remain #40 gates.
CentOS Stream 8 support status has not been waived. The user's live domain, Nginx,
WAF, certificates, firewall and installed desktop remain untouched.

Path prefixes are routing partitions, NOT same-origin browser security partitions.
A compromised application on the same HTTPS origin can act as that origin. Use a
dedicated audited origin or review every application sharing it before deployment.

## Test commands

```sh
cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --test service_contracts
python services/cloud-gateway/tests/run_service_http.py --pg-bin /usr/lib/postgresql/16/bin --binary /absolute/built/coding-tools-gateway
python services/cloud-gateway/tests/run_service_acceptance.py --pg-bin /usr/lib/postgresql/16/bin --binary /absolute/built/coding-tools-gateway --chromium /absolute/chromium
```

The process suites run as an unprivileged test user, create a fresh private PostgreSQL
cluster, accept no input DSN, and clean it up. Browser acceptance additionally uses an
ephemeral loopback TLS proxy and certificate. Certificate trust is relaxed only for
that disposable test certificate; Chromium OS sandboxing is not under test. Browser
policies must not be bypassed; blocked navigation exits nonzero and is never PASS.

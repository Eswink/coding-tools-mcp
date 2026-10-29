# Runnable nonproduction container topology

This is the executable development/acceptance path for Issue40. It does not replace the existing Nginx/Baota vhost, publish a registry image or configure the user's VPS. Native CI evidence is required before marking the engineering gate passed.

## Services and trust boundary
- A small non-root namespace anchor uses the same gateway image, runs only init plus sleep, and owns the shared network namespace. It publishes exactly one port on host 127.0.0.1.
- The gateway stays bound to 127.0.0.1:28880 inside that namespace. Its established loopback-only configuration policy is unchanged.
- Non-root Nginx shares the namespace and listens on internal 8080. It validates the original Host against the immutable configured origin before forwarding to the loopback gateway. Arbitrary Forwarded and X-Forwarded-Host headers cannot select identity.
- PostgreSQL is non-root and attached only to an internal private database network. It has no host-published port. Separate migration and runtime roles are used. The runtime role is non-superuser, cannot create roles/databases/schema objects, and cannot update the migration ledger. It receives only the required application-table DML and sequence permissions.
- A separate opt-in operator profile has no ports and uses Docker logging driver none. This is essential for explicit key/invitation/proof/configuration documents returned to a caller's pipe; ordinary container logging must not persist them.

Gateway restart does not replace the shared namespace or ingress container. Replacing the anchor itself is an explicit paired-recreation operation. Do not put the application in host network mode or widen its bind address to make a template work.

## Render and protected configuration contract
`deploy/cloud-gateway/runtime_topology.py` renders only into a new directory. It takes an immutable local gateway image ID, official Nginx/PostgreSQL digest references, a validated canonical domain, connector UUID and unprivileged host loopback port. It invokes no Docker or host configuration operation. Its sanitized read-only port observation reports an existing listener but never claims that absence proves availability; the final bind must still refuse collisions.

The rendered Compose refers to these operator-prepared directories:
- gateway-private, owned by UID/GID 65532 with mode 0700. Its config.json is the actual GatewayConfig JSON: origin, prefix, connector, owner_subject, client_id, redirect_uri, client_authentication and loopback bind. Its runtime.json contains only database_url and identity_key. Files must be private and owned by 65532.
- ingress-private, owned by 65532 with mode 0700, containing the rendered Nginx configuration as nginx.conf. Mounts are read-only.
- postgres-private, owned by 999 with mode 0700, containing a private password file for the selected tested PostgreSQL image.

These are complete directory binds so the parent-directory ownership check matches the implemented CLI. No nonexistent DATABASE_URL_FILE/IDENTITY_KEY_FILE loader or LISTEN_ADDR environment override is used. Missing bind sources are not silently created. Do not change global host permissions; prepare only explicitly owned configuration directories through an approved operator procedure.

## Explicit from-empty operator flow
Start only the private database first. Provision separate non-superuser migration and runtime roles. Run migration with the migration role, then grant the runtime role schema usage, ledger read access and application-table DML without schema creation or ledger updates. Then use the shipped binaries through the operator profile:
1. coding-tools-gateway migrate, provision-owner and register-client with the pinned config and protected secrets channel
2. coding-tools-agent generate-key, explicitly piping the private document to a protected caller-owned destination
3. coding-tools-gateway invite-device with the pinned origin/connector
4. coding-tools-agent prove-enrollment using the pinned minimal identity configuration, invitation and private key
5. coding-tools-gateway redeem-device using the public proof; the private key never goes to the gateway
6. coding-tools-control-gateway select-device using the returned device UUID
7. Start namespace, gateway and ingress, then verify readiness through the host loopback endpoint

Use each binary's current --help for exact channel options. Explicit stdout documents must be captured in a private pipe/file, never a terminal transcript, general log or Actions artifact. The renderer does not generate credentials, migrate a database, grant workspace authority or start services. The dedicated CI fixture performs this flow only with fresh ephemeral credentials and a uniquely named disposable project.

## Actual acceptance workflow
`.github/workflows/issue40-container-topology.yml` runs from ci/issue40-container-topology and is also reusable with workflow_call. It builds all four locked release binaries from the exact commit, records Cargo JSON artifacts, resolves official image digests and verifies Compose 2.27.0 against its official checksum.

The native fixture checks actual non-root users, private DB network, loopback-only publication, exact binary hashes, operator logging disabled, original Host/forwarded-header behavior, OAuth login/consent/PKCE, MCP legacy protocol headers and their negative version gate, real Agent WebSocket upgrade, collision refusal preserving an existing listener, graceful gateway shutdown before pending-auth expiry, restart with persistent OAuth authority, and revoked-device rejection after database restart. Cleanup targets only the newly generated project-labelled containers/volumes and private fixture directory. No private documents or raw HTTP payloads are exported.

The WebSocket test is an internal HTTP-upgrade and pending-channel shutdown test. It does not claim public TLS/WSS or physical-host provenance; existing authenticated WSS regressions remain required. Engineering CI may use the current gateway component version before an RC is selected. Final release still requires desktop/gateway product-version alignment and exact-source reruns.

## Production boundaries
A supported host, actual Docker Engine security floor, existing Nginx/Baota syntax, TLS/WAF behavior, route conflicts, backup/restore and real ChatGPT acceptance remain separately reviewed requirements. CentOS Stream 8 is unsupported; containers do not repair that kernel lifecycle. No OS migration, WAF exception, new443 listener, DNS change, registry push or production restart is performed by this work.

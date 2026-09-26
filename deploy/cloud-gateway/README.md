# Existing Nginx / Baota deployment boundary

Status: **REVIEW_BLUEPRINT_ONLY / NOT_DEPLOYABLE**. These files do not install or start a gateway.

## Supplied topology

User reports CentOS Stream 8, x86_64, Compose 2.27.0, `research-system.eswlnk.com`, with Nginx/Baota WAF on 443. This is not a live inventory or access credential. The design preserves that listener and existing site, using `/coding-tools/` and the exact path-based OAuth discovery locations. Planned upstream: `127.0.0.1:28880`; neither availability of this port nor absence of route conflicts has been observed on the VPS.

`render.py` writes only a new caller-selected review directory. It does not run Docker, inspect or reload Nginx, query DNS, open SSH, alter a firewall/WAF, generate production secrets or connect to the supplied domain.

```bash
python deploy/cloud-gateway/render.py \
  --connector-id 00000000-0000-0000-0000-000000000001 \
  --output ./gateway-review
```

That UUID is a documentation fixture, not an enrollment credential. Select/persist a real opaque route during future provisioning. The generated origin/resource and database identity must agree; changing the domain, prefix or connector is a migration, not normalization.

## Guarded blueprint, not an installer

The generated Compose JSON has all services behind `integration-pending`; image and external secret-file variables are mandatory. No gateway image exists in this increment. The `_FILE` settings describe a **future binary configuration contract**, not an implemented loader. A rendered/normalized file is not runnable-service acceptance. Digest pinning, tested image UID/file permissions, resource sizing, readiness, graceful shutdown and runtime hardening must be checked when an executable/image is delivered.

Only the gateway port is published, explicitly on loopback; PostgreSQL stays on a separate internal network. The future gateway uses an application DB role, **not** the bootstrap superuser. Provision least-privilege migration/runtime roles before filling its DSN file. The blueprint does not provision those roles. Never mount the Docker socket, host workspace directories or host network into the gateway.

Compose file secrets are not an encrypted secret manager. Keep source files outside the checkout, private to the correct runtime owner, and out of Git/logs/backups unless the backup is explicitly encrypted and access controlled. File-mounted secret uid/gid handling must be validated for the selected image; blindly using root-owned 0600 files with a non-root process will not work. Database backups contain sensitive identity metadata even though bearer credentials are stored only as digests.

## Nginx / WAF integration

Review/merge only the generated locations into the appropriate existing TLS vhost. There are no certificate, global `server`, `listen`, root-site, WAF-disable or reload directives. Prefixes are not stripped. Inbound Host is checked before it is set to the explicit upstream authority; forwarded host values cannot choose OAuth identity. Buffer/cache/error interception are disabled for protocol routes. WebSocket upgrade forwarding is confined to the future exact Agent route; that channel is not implemented yet.

`access_log off` suppresses ordinary location access logs only. Baota WAF, upstream/CDN, APM, Nginx error logs and request-body inspection may still capture query/form bodies; audit these separately. Do not globally disable the WAF or bypass authentication to make the protocol work. Only narrow, reviewed route-specific changes with an abuse-control replacement may be considered after observing real behavior. Nginx syntax passing in a container does not establish Baota/WAF/TLS compatibility.

## Deployment blockers, no user intervention required for development

1. **CentOS Stream 8 EOL**: official builds/updates ended on 2024-05-31. A maintained container image does not update the host kernel. Production launch needs a supported-host migration or explicitly reviewed security resolution. Do not automatically upgrade the current server or modify other services. This does not block development/isolated tests.
2. **Docker Engine unknown**: Compose 2.27.0 is a different component. Docker warns that engines older than 28.0.0 can expose localhost-published ports to the same L2 segment. Verify Engine/firewall/external reachability instead of assuming the loopback string proves isolation. No firewall changes are included here.
3. **Application integration pending**: owner sign-in/consent, Agent WSS/dispatch, full rate limiting and rollback-safe identity restoration are not complete. The Rust adapter cannot serve a complete ChatGPT authorization flow.
4. **Live deployment unobserved**: port/path conflicts, public TLS, WAF behavior, backup restore and real ChatGPT remain unverified. No credentials, deployment channel or host access were supplied; no deployment is claimed.

`assess_inventory()` reports these findings from supplied facts without contacting the host; it cannot certify readiness.

## Reversible future rollout

Provision an isolated test route/database first. Back up the current site config and validate with the **actual Baota binary** before a reviewed reload. Keep old connector/desktop configuration and credentials unchanged until real-Host acceptance passes. Never restore an old identity DB blindly: consumed tokens/revocations need an anti-rollback decision. No routine `docker compose down -v` or destructive database cleanup is part of rollback. Removing un-applied review artifacts is the only rollback needed now.

## Authoritative references

- CentOS end of updates: https://blog.centos.org/2023/04/end-dates-are-coming-for-centos-stream-8-and-centos-linux-7/
- Docker loopback/L2 warning: https://docs.docker.com/engine/network/port-publishing/
- Compose secret-file behavior: https://docs.docker.com/compose/how-tos/use-secrets/
- Nginx WebSocket forwarding: https://nginx.org/en/docs/http/websocket.html
- OAuth security / refresh rotation: https://www.rfc-editor.org/rfc/rfc9700.html

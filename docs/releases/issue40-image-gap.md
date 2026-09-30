# Issue40 deployment contract reconciliation

Issue: https://github.com/Eswink/coding-tools-mcp/issues/40

## Acceptance against executable source
- Read-only sanitized preflight/offline rendering: present in render.py/migration.py. These helpers do not apply configuration or contact the VPS. User-supplied inventory is not live evidence.
- Non-root/secrets/resource/private-network/restart preparation: template fields exist, but the old generated Compose is deliberately NOT_DEPLOYABLE. Executable compatibility must be demonstrated before this acceptance can be called complete.
- Existing-Nginx include/Host/MCP header protection: review snippets and private-loopback test harness exist; existing TLS vhost and sites are not replaced.
- Restore/rollback/non-resurrection: documented operator review boundary exists. No production restore test has occurred.
- Image/build: previously absent; this increment supplies a bounded executable image recipe and native CI gate. Local synthetic tests are not image execution evidence.
- Compose2.27.0/Nginx syntax: existing origin-migration workflow downloads exact Compose2.27.0 and verifies its release checksum, then runs actual config normalization and private Nginx tests. Those tests prove syntax/header routing only, not a working gateway deployment.

## New bounded image preparation
The cloud artifact workflow appends an image job after the release-binary process acceptance. It consumes the same verified four-binary archive, resolves official Ubuntu22.04 to an immutable digest, builds a UID65532 image and records base/image/source/product identities. No registry login or push is present.

Native tests run the image with network disabled, read-only root filesystem, no capabilities, no-new-privileges and bounded memory/process count. They verify actual UID, exact copied binary SHA256, and actual help/version for all four executables. A freshly created public synthetic fixture tests config ownership and the precise secret-file protection boundary. The so-called secret input is intentionally invalid noncredential JSON: successful protected reading reaches invalid_secret_input; making that file world-readable must instead yield file_protection_failed. No password, key, DSN or token is created. Only the fresh fixture's ownership/mode changes; no system ACL changes occur.

The image is exported as an Actions archive with checksum and receipts. It does not expose a port, start a configured service, connect to a database, install a service unit or alter a host. Image package inventory is retained. A digest-pinned base makes the selected base identifiable; apt-installed package versions are recorded and the resulting image ID identifies the build. This is not a claim of bit-for-bit rebuild reproducibility or a completed container vulnerability scan.

## Remaining executable engineering gaps, not external deferrals
1. Old Compose supplies PUBLIC_ORIGIN/LISTEN_ADDR and separate DATABASE_URL_FILE/IDENTITY_KEY_FILE variables. Current binaries instead require explicit --config JSON plus --secrets-file containing the implemented JSON schema. No compatibility loader exists. Do not label the old template runnable.
2. Current GatewayConfig intentionally accepts only loopback bind addresses. The old template expects 0.0.0.0:8080 inside a bridged container. Docker port forwarding does not make a service bound to the container's loopback reachable through its bridge address. Do not widen production binds merely to pass an image test.
3. A reviewed container ingress adapter is still needed. One possible design is a narrowly scoped non-root proxy sharing the gateway's network namespace, forwarding an internal bridge listener to the gateway's loopback listener, with only the host loopback port published. This requires implementation and real tests for Host/MCP headers, bounded buffers, shutdown, namespace ownership and private DB connectivity. It is a proposal, not implemented by this image recipe.
4. Protected config/secrets must have actual owner UID65532, non-shared parent permissions and private modes. Compose file-backed secrets do not automatically solve arbitrary host ownership. Do not assume uid/gid/mode declarations prove effective permissions; verify actual mounts and avoid global permission changes.
5. Least-privilege DB provisioning, readiness, graceful service shutdown, restore/rollback and revocation preservation must be exercised through the final runnable container topology. The no-network CLI fixture does not replace these tests.

## External production blockers remain separate
CentOSStream8 received no further builds after2024-05-31 per the official notice: https://blog.centos.org/2023/04/end-dates-are-coming-for-centos-stream-8-and-centos-linux-7/ . An updated container does not update an unsupported host kernel. No OS migration or risk waiver was applied.

Actual host port/path collisions, existing Baota binary syntax, TLS/WAF behavior, external isolation and real ChatGPT remain NOT_EXECUTED. No secure deployment channel or production credentials were used. These are genuine external acceptance boundaries; they must not be used to hide the unfinished source-level ingress/config integration above.

References: Docker USER and build semantics https://docs.docker.com/reference/dockerfile/ ; Compose secret handling https://docs.docker.com/compose/how-tos/use-secrets/ ; service network namespace configuration https://docs.docker.com/reference/compose-file/services/ .

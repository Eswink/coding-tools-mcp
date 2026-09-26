# Cloud identity and owner consent — rounds 2–3

**LIBRARY_INCREMENT / NOT_DEPLOYABLE / HOST_UNCONFIRMED**

This isolated Rust crate does real cryptographic verification and PostgreSQL transactions. It does not use the M1 laboratory's fixture authentication. It is also **not a complete OAuth authorization server or MCP gateway**: there is no production executable, provisioning CLI, Agent socket, MCP dispatch or local execution. An explicitly provisioned owner can now use the browser authorize/login/consent controllers in the library router; ingress controls, real-browser interoperability and deployment are still separate gates. Do not expose this router to ChatGPT or the public internet yet.

## Ownership boundaries

`IdentityStore` binds a database to one explicitly configured HTTPS issuer and opaque connector resource. The database pool must target a new, dedicated schema/database. `migrate` is an explicit administrative operation; normal startup does not run migrations. Identity/key mismatch fails rather than destroying old sessions or silently minting a new identity.

`register_client`, `issue_after_owner_consent`, `create_device_invitation`, `revoke_owner_sessions` and `revoke_device` are **trusted operator APIs**, not remotely callable authorization shortcuts. The browser controller authenticates the provisioned owner, binds `state` server-side and enforces CSRF, cookie rotation, exact client redirects and bounded login work. Public ingress rate limits are still required. Never accept a user-supplied `subject` or privilege from an unauthenticated HTTP request.

The HTTP adapter exposes fixed discovery paths, the token endpoint and GET authorize / POST login / POST consent. It does not expose provisioning, device invitations, direct code issuance or password rotation. Token requests require a preregistered client, exact redirect/resource, S256 PKCE, and a secret for confidential clients. Client secrets must be high-entropy random values, not user passwords. `client_secret_basic`, dynamic registration and password grants are not supported/advertised. PKCE and refresh binding cannot be bypassed with alternate form fields or duplicate parameters.

## Persistence and refresh

Raw authorization/access/refresh/invitation/client credentials are never stored: domain-separated HMAC digests are retained with an externally managed 32-byte random key. This is **not encryption of all database metadata**. Protect subject/client IDs, timestamps, device public keys and future approval projections with database/backup access controls and encrypted storage as required.

Access validation consults current family/client state, so family revocation invalidates already-issued access tokens. A PostgreSQL family lock serializes refresh. Reuse revokes the family, including tokens returned by a concurrent winning request. No permissive reuse grace period is added to hide replay or transport failures. A lost refresh response can therefore require real OAuth reauthentication; that is distinct from local Agent offline and must remain a real authentication failure.

Database time controls expiry; family lifetime is absolute. Restart persistence is tested, but restoring an older backup can resurrect consumed/revoked state. Anti-rollback/key-epoch handling, backup restoration policy, garbage collection and monitored capacity/rate limits remain required release gates. Do not copy this database, mix connectors into it, rotate/delete its key or change issuer/resource as a routine restart.

## Device and local authorization

Five-minute invitations are single-use and route-bound. Redemption verifies Ed25519 proof of possession before consumption and atomically creates the device. Enrollment alone grants **no tool access**. Device private keys stay on the device; production key enrollment/storage and transport are not wired yet.

`verify_grant` accepts an exact signed envelope from a freshly loaded, non-revoked registered device. Claims bind issuer, connector, device, conversation, scopes, epoch and absolute expiry. A `VerifiedGrant` does not replace the Agent's local active grant, execution gate, revocation/recovery fence or per-call revalidation. It is not a distributed projection, ownership arbiter or worker ticket. Shared ChatGPT logins are not reliable employee identity.

## Validation

Rust 1.98.1; locked independent dependencies. No Tauri/GTK is needed.

```bash
cargo fmt --check --manifest-path services/cloud-gateway/Cargo.toml
cargo clippy --locked --manifest-path services/cloud-gateway/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --test pure_contracts
```

Database tests intentionally fail without `TEST_DATABASE_URL`; they never silently skip or fall back to production. Only a loopback database named `coding_tools_identity_test` is accepted. Tests create unique schemas and preserve them for investigation until the disposable cluster is removed. Do not use a persistent/shared production cluster even if a database has this name.

```bash
TEST_DATABASE_URL=postgresql://gateway_test@127.0.0.1:25439/coding_tools_identity_test \
  cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml
cargo build --locked --manifest-path services/cloud-gateway/Cargo.toml --example restart_probe --example browser_restart_probe
python services/cloud-gateway/tests/run_restart_test.py \
  --pg-bin /usr/lib/postgresql/16/bin \
  --probe services/cloud-gateway/target/debug/examples/restart_probe
```

The restart test must run as an unprivileged user. It creates its own fresh cluster, starts/seeds/stops/restarts it, verifies credentials in a new process, and removes the cluster. It never accepts a production DSN or existing data directory. Probe credentials travel through parent/child pipes in memory; do not run `seed` manually or save its stdout. Fixed fixture keys are explicitly test-only.

Tests are protocol/identity evidence, not proof of ChatGPT's reconnect UI behavior, Windows installed acceptance, a complete OS sandbox, or a deployed VPS.

## Browser consent (ISSUE-013B / GitHub #41)

Provision exactly one owner through the trusted `BrowserAuth::provision_owner` library API. There is no default password, signup endpoint or remotely callable provisioning route. The five-minute browser flow requires an exact registered client, redirect, resource and S256 challenge. Argon2id login rotates cookie and CSRF without extending the absolute deadline; explicit consent atomically consumes the flow and creates at most one code. Owner password rotation uses an expected epoch and invalidates browser flows and that owner's OAuth families. OAuth consent never creates local chat approval.

Passwords and bearer/CSRF secrets are not stored raw. Authorization request/state is AEAD-encrypted in the temporary flow table. HTML uses Secure/HttpOnly/SameSite=Lax `__Host-ctm-browser` cookies, escaping, no-store, no-referrer and a restrictive CSP. The existing same-origin site remains a trust boundary: a path or __Host prefix does not isolate malicious same-origin applications. Cookie prefixes and 303/CSP behavior still require real browser acceptance before deployment.

There are only two concurrent password-verification tasks per shared BrowserAuth, 128 active browser flows per connector database, and a durable five-failure / 60-second login cooldown. These limits bound work but are not a complete public anti-abuse layer. Reuse one router/BrowserAuth per service, not one per request. Tests cover replay, CSRF, callback tampering, client disable, credential rotation, concurrent consent, database restart and expiry while awaiting a client row lock.

The test-only `browser_restart_probe` can replace `restart_probe` in the Python restart runner above to verify an authenticated browser transaction survives a real process/database restart. Never expose the probe or its fixed test fixtures in a production binary.

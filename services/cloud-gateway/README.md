# Cloud identity core — round 2

**LIBRARY_INCREMENT / NOT_DEPLOYABLE / HOST_UNCONFIRMED**

This isolated Rust crate does real cryptographic verification and PostgreSQL transactions. It does not use the M1 laboratory's fixture authentication. It is also **not a complete OAuth authorization server or MCP gateway**: there is no production executable, owner sign-in/consent controller, public authorization endpoint, Agent socket, MCP dispatch or local execution. The metadata advertises the eventual authorization URL, which cannot be used until that controller is implemented. Do not expose this router to ChatGPT or the public internet yet.

## Ownership boundaries

`IdentityStore` binds a database to one explicitly configured HTTPS issuer and opaque connector resource. The database pool must target a new, dedicated schema/database. `migrate` is an explicit administrative operation; normal startup does not run migrations. Identity/key mismatch fails rather than destroying old sessions or silently minting a new identity.

`register_client`, `issue_after_owner_consent`, `create_device_invitation`, `revoke_owner_sessions` and `revoke_device` are **trusted operator APIs**, not remotely callable authorization shortcuts. The future controller must authenticate the owner, validate `state`, enforce CSRF/session/consent controls, exact client redirects and rate limits. Never accept a user-supplied `subject` or privilege from an unauthenticated HTTP request.

The HTTP adapter exposes only fixed discovery paths and the token endpoint. Token requests require a preregistered client, exact redirect/resource, S256 PKCE, and a secret for confidential clients. Client secrets must be high-entropy random values, not user passwords. `client_secret_basic`, dynamic registration and password grants are not supported/advertised. PKCE and refresh binding cannot be bypassed with alternate form fields or duplicate parameters.

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
cargo build --locked --manifest-path services/cloud-gateway/Cargo.toml --example restart_probe
python services/cloud-gateway/tests/run_restart_test.py \
  --pg-bin /usr/lib/postgresql/16/bin \
  --probe services/cloud-gateway/target/debug/examples/restart_probe
```

The restart test must run as an unprivileged user. It creates its own fresh cluster, starts/seeds/stops/restarts it, verifies credentials in a new process, and removes the cluster. It never accepts a production DSN or existing data directory. Probe credentials travel through parent/child pipes in memory; do not run `seed` manually or save its stdout. Fixed fixture keys are explicitly test-only.

Tests are protocol/identity evidence, not proof of ChatGPT's reconnect UI behavior, Windows installed acceptance, a complete OS sandbox, or a deployed VPS.

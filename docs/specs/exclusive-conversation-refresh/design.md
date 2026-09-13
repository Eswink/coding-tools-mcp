# Design and manual impact assessment

## Scope and trust

High-risk authorization change by manual call-chain assessment. Native GitNexus/Probe unavailable; attempted pinned CLI install and offline execution failed. This is NOT graph validation. Read AGENTS.md, Probe 4.0.1 skill, project-context and graph summary before editing. Preserve old main and independent PR #11.

MCP listener verifies the OAuth principal, then constructs the existing HMAC binding over profile, workspace, issuer, subject, client ID and host session. The shared dispatch intercept checks chat ownership/scopes before side effects. New admission guards cover a complete dispatch; background jobs register their session/task stores before the guard is released. Shared workspace files are not cloned.

## State and lock order

A per-profile Owner records binding, request ID and typed phase RESERVED/ACTIVE/DRAINING. The authorizer mutex linearizes reservations and decisions. Non-owner requests return before creating records or events. Expiry/revocation only closes future admissions; draining retains the workspace until all known work is terminal. Admission epoch rejects a stale executor scan. Executor locks are never acquired while holding the authorizer state lock. A bounded broadcast event is only an invalidation, never permission.

Before dispatch capable of starting a process, an authenticated encrypted execution fence is committed. The fence records known HMAC runtime namespaces. After process restart, dirty means recovery-required, not automatic release. Restored unfinished task records remain interrupted/unknown and discoverable through the local task controls. The local operator must separately resolve unknown tasks and acknowledge the current recovery generation after inspecting processes. A successful remote request cannot acknowledge or clear the recovery lock.

## Credential storage and OAuth

AuthDocument reuses the application Vault and a lifetime sidecar lock; raw data is bounded, encrypted/authenticated, atomically replaced, and never overwritten when unreadable. Missing preexisting keys fail closed. RefreshStore is shared by namespace within the process and stores at most64 families. Raw tokens have a random256-bit component, family/generation, and a keyed authentication tag; only keyed digests/family metadata are persisted. The tag allows verifying a spent generation before revocation without an unbounded list of old tokens. Guessed family IDs cannot revoke anyone.

Refresh binds client, issuer, resource and a credential-derived key; password/client-secret/token-signing changes invalidate the family context. Rotation saves before returning credentials. Family absolute deadline never slides. Access JWT `sid` references the family; each network authentication verifies family validity. Older access-only JWTs remain backward compatible until expiration. Refresh neither observes nor modifies chat ownership. Client authentication, exact redirect/resource binding, PKCE S256 and scope validation remain enforced; optional offline_access is authorization-server consent, not a business-tool scope or OIDC.

## UI and configuration

The global Svelte approval host is mounted outside workspace routes. It listens for invalidations, fetches an authoritative local inbox, deduplicates IDs and uses snapshot revision fencing. An explicit fingerprint checkbox and nonempty requested-scope subset gate approval. The backend revalidates pending state and rights. Native desktop notifications contain no secrets/path/owner ID. A tray menu and badge provide fallback. The workspace panel remains a recovery and revocation view, not a conflicting temporary exclusive switch.

SessionPolicy is defaulted by serde for old profiles, validated before update/listener start, and copied by AuthConfigForm so unrelated credential edits cannot reset custom durations. The UI converts labelled units to seconds and guards async confirmations/completions across workspace switches. Changes apply to newly signed tokens/newly approved leases; existing refresh absolute deadlines do not silently grow.

## Validation boundaries

A compiled DOM fixture mocks only IPC/events/native dialog, not component decision logic. It is not evidence of installed system notification behavior. Full Rust/HTTP tests need actual Cargo and run in Actions. Real ChatGPT metadata delivery and OAuth renewal, native installed Windows/Linux notices, and production public ingress remain separate non-substitutable gates.

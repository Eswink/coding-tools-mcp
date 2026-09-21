# ISSUE-013 — cloud-oauth

Parent: Epic #32. Follow-on implementation for Draft PR #36.
Status: **PARTIAL / BROWSER_LOCAL_VERIFIED / PUBLICATION_PENDING**. Actual parent issue #37; browser consent child #41.

## Implemented increment

PostgreSQL PKCE/exact client/resource binding; rotating opaque tokens; replay-family revocation; persistent key/origin binding; fixed metadata/token HTTP adapter; round3 explicit owner provisioning, Argon2id browser login, rotated cookies/CSRF and atomic allow/deny consent.

Source: `services/cloud-gateway/`. Validation evidence: `round2-validation.md` and `round3-validation.md`.

## Open acceptance gates

Production entrypoint/provisioning CLI, real-browser cookie/CSP acceptance, public ingress rate limits/capacity, revocation HTTP endpoint, encrypted backup/restore anti-rollback, production integration.

## Constraints

No existing desktop/Tauri code, credentials, production route or database is altered. Tests run only in disposable loopback databases. These primitives are not authorization to run a local command. Local Agent may be fully absent during cloud refresh. Real ChatGPT truth label remains `UNCONFIRMED_ON_REAL_HOST`.

## Next state

Publish the exact tested patch after a write-capable channel exists; review and run Windows/Ubuntu CI. Close this issue only after its remaining integration and security gates pass, not merely after primitive tests pass.

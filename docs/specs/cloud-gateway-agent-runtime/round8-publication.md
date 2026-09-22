# Round 8 publication — request admission and no-replay reconciliation

Date: 2026-09-22. Tracking: #49 / ISSUE-019A, Epic #32, Draft PR #36.
Classification: **REQUEST_ADMISSION_ENGINEERING_VERIFIED / LOCAL_EXECUTION_NOT_CONNECTED / HOST_DEFERRED**.

## Exact source identity

The reviewed local commit `353a2bdd09ade864d7ca0c8ec1a6d3640edc0bff` and published native commit `1e1db5faa0fdcf34133b615f9842b93a40fe7b9a` share exact Git tree `2ec47d544a1d5bd3d001fcf912516e01c6b56176`. The published commit fast-forwards previous feature head `765664434a8016f05ce3a15fff87065506fbc7fc`; main is unchanged.

Independent one-shot run `35694160510` reconstructed the exact tree from a digest-pinned patch and passed the full cloud-gateway Rust/PostgreSQL and delivery-scheduler regression gates before importing only hash-verified blobs. The first recovery run's test gates passed but its direct branch push was rejected because the GitHub App workflow token could not modify a workflow file; that failure is retained rather than relabeled. The second run did not mutate refs. The authorized native connector created the exact tree/commit and fast-forwarded the feature branch with `force=false`.

## Current-source CI

`35694473116` — Cloud gateway request admission:

- Ubuntu PostgreSQL: 19 admission concurrency/reconciliation tests PASS.
- Ubuntu 24.04 portable: canonical admission unit tests, formatting and all-target Clippy PASS.
- Windows 2025 portable: the same portable compilation/contracts PASS.

Artifacts:

- `10679328970` request-admission-postgres — `sha256:42d78182182767ac6eba636c8b210b627ee5cae6eade5cacff9f2a6d9081540a`
- `10679513903` request-admission-portable-ubuntu-24.04 — `sha256:888650c76366cf56b977b3e1448e5068cb7255daba83b1facf3b0f425a006d70`
- `10680320950` request-admission-portable-windows-2025 — `sha256:512f3e14d80dc2ae2cbe08840e7f362465e6c108f94a86dcb88017294c3d54d3`
- one-shot source verification `10680320278` — `sha256:89970b2a153b8f76f330f5f6576d2fa57f9f167339c2a13deb1a76fd6dd9418a`

## Delivered boundary

The durable ledger persists request identity, argument digest and authorization/channel fences only. It does not persist raw tool arguments, command output, source files or bearer/session material. Exact duplicate requests reconcile to durable state; changed request reuse conflicts. Offline denial is terminal for that request ID. Pause/revoke/reconnect/expiry and old gateway boots are rechecked before transition to `running`. Lost or already-running outcomes become `outcome_unknown` and are never silently replayed.

This remains a cloud-side eligibility/admission boundary, not a local execution permit. No MCP business tool, shell, filesystem or desktop command path is connected by this increment. The next delivery task is the locally approved authority provider/execution gate bridge and must receive fresh high-risk impact review before touching existing desktop authorization symbols.

## Retained failures and rollback

Initial local tests exposed a concurrent exact-duplicate primary-key race; a transaction-scoped advisory lock now serializes same-request admission. A PostgreSQL test initially decoded `octet_length` as `i64` instead of `int4`; the test was corrected without product behavior change. Clippy rejected two over-wide helpers; typed context structs replaced the wide signatures instead of suppressing warnings.

Migration `0005_request_ledger.sql` is additive. Rollback stops future dispatch first and retains migration history, unknown-outcome rows and revocation authority. It must not delete unknown outcomes or resurrect a revoked grant.

Physical Windows/Ubuntu installation, live VPS/BaoTa/WAF and real ChatGPT behavior remain deferred and are not PASS. No reconnect-card claim is made.

# ISSUE-014 — local-grant

Parent: Epic #32. Follow-on implementation for Draft PR #36.
Status: **PARTIAL / LOCAL_INCREMENT_NOT_PUSHED**. Actual GitHub issue #38 verified; publication and CI remain separately tracked.

## Implemented increment

Ed25519 signed local-grant verifier with issuer/connector/device/conversation/scope/epoch/time binding; conversation HMAC domain separation.

Source: `services/cloud-gateway/`. Validation evidence: `round2-validation.md`.

## Open acceptance gates

Local approval UI, authoritative projection and persistence, exclusive owner arbitration, recovery/fence/gate integration, per-request local revalidation. No cloud ticket can mint local permission.

## Constraints

No existing desktop/Tauri code, credentials, production route or database is altered. Tests run only in disposable loopback databases. These primitives are not authorization to run a local command. Local Agent may be fully absent during cloud refresh. Real ChatGPT truth label remains `UNCONFIRMED_ON_REAL_HOST`.

## Next state

Publish the exact tested patch after a write-capable channel exists; review and run Windows/Ubuntu CI. Close this issue only after its remaining integration and security gates pass, not merely after primitive tests pass.

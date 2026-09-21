# ISSUE-016 — device-enrollment

Parent: Epic #32. Follow-on implementation for Draft PR #36.
Status: **PARTIAL / LOCAL_INCREMENT_NOT_PUSHED**. No new GitHub issue number assigned: this session exposes read-only connector operations.

## Implemented increment

Five-minute route-bound single-use invitation; Ed25519 proof before consumption; PostgreSQL atomic redemption, registered-device lookup and revocation.

Source: `services/cloud-gateway/`. Validation evidence: `round2-validation.md`.

## Open acceptance gates

Authenticated operator enrollment UX, on-device private-key storage/rotation, authenticated WSS channel, reconnect/generation/replay protection and real Agent integration.

## Constraints

No existing desktop/Tauri code, credentials, production route or database is altered. Tests run only in disposable loopback databases. These primitives are not authorization to run a local command. Local Agent may be fully absent during cloud refresh. Real ChatGPT truth label remains `UNCONFIRMED_ON_REAL_HOST`.

## Next state

Publish the exact tested patch after a write-capable channel exists; review and run Windows/Ubuntu CI. Close this issue only after its remaining integration and security gates pass, not merely after primitive tests pass.

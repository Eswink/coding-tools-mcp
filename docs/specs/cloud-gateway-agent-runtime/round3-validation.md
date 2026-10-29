# Round 3 validation — owner browser consent (#41)

Classification: **BROWSER_IDENTITY_LOCAL_VERIFIED / PUBLICATION_PENDING / NOT_DEPLOYABLE / HOST_UNCONFIRMED**.
Date: 2026-09-21. Parent #37; Epic #32; Draft PR #36.

## Source provenance

Recovered exact local round2 commit `4b6f197118d818735d77d23d9f8593976abdb702` (tree `d38905bc9684ca2c066de331a42eabaee2c0bcea`) from the prior delivery bundle, with prerequisite `ba9c379f08da37f2a05bb96c377a95f432da969e`. Remote PR was independently read and still had that prerequisite head. The recovery archive SHA-256 is `1d7a0d649b41c48e8d36eec052c8e22d93918ab0daa2fd860a631bb6b23cd43c`. No claim of prior remote publication is made.

This document lives with the source increment; its owning commit/tree and any remote import/CI identifiers are recorded separately in the delivery manifest and Issue #41. A source-recovery workflow may reconstruct/import the exact tested Git objects on an isolated branch. It must verify expected base, content digest, protected paths and resulting tree, test the reconstructed source, and never move main or silently replace concurrent feature-branch edits. Remote publication is a separate explicit ref update after object/CI verification.

## What changed

Six browser modules separate credentials, encrypted transaction envelope, state-machine/database transitions, strict HTTP parsing and HTML/cookie policy. Additive schema 0002 adds an explicit single owner and temporary browser transactions. The existing trusted code-issuance API delegates to an internal caller-owned transaction helper; HTTP router adds only authorize/login/consent. Direct admin issuance, device invitations and local execution remain unexposed.

Login verifies Argon2id and rotates cookie/CSRF, but does not issue a code. Allow/deny checks current owner epoch, expiry and exact registered client then atomically consumes the flow with issuance or denial. Password rotation is explicit CAS, clearing browser flows and revoking owner OAuth families. No Agent needs to be online for any of this.

## Executed tests (development container)

| Suite | Result | Boundary |
|---|---|---|
| Browser HTTP | 13 PASS | Router/body/header/cookie/CSRF/redirect; not a real browser engine |
| Browser store | 17 PASS | Real PostgreSQL transactions/concurrency/expiry/password rotation |
| Existing identity/device/HTTP/pure tests | 38 PASS | Exact locked Rust crate, no skipped database tests |
| Full Rust total | **68 PASS, 0 failed, 0 ignored** | Rust 1.98.1, PostgreSQL 16.15, isolated loopback test database |
| Cargo format and all-target Clippy | PASS / zero warnings | Includes browser and restart probe source |
| Browser independent process + database restart | PASS | Seed in one process; PostgreSQL stop/start; consent/exchange/refresh in another |
| Existing OAuth independent restart | PASS | Existing access/refresh persists; no Agent |
| Deployment renderer | 13 PASS | No Docker up or VPS writes |
| Existing MCP protocol lab | 32 PASS | Synthetic worker only |
| Existing UI source contracts | 8 PASS | Not desktop/browser interaction |
| Existing Python fault proxy | 8 PASS | No company connector pointed to it |

## Failure evidence retained

The initial route test failed because authorize was not implemented. An early test compile used a nonexistent method and was corrected to the actual access API. A targeted client-row-lock regression then demonstrated expiry being checked too early; database time is now rechecked after waits and during issuance. The first full-suite attempt also failed an obsolete POST-authorize 404 assertion; the new GET route correctly makes POST return 405, so the regression now checks 405, no redirect, zero issued codes, and preserves 404 for direct admin/enrollment shortcuts. None of these earlier runs is relabeled PASS. See review.md and iterations.md.

## Evidence digests

These are original local evidence files bundled with the increment; remote CI artifacts require their own source-linked evidence. Absolute paths and timing details are development-container observations, never production identifiers.

| File | SHA-256 |
|---|---|
| `rust-after-route-update.log` | `fa96fa4098dac2c1ba084d2269bc1ac2d718d75e4e2a3b70c40edd2fd98f2b30` |
| `clippy-final.log` | `284bfb645de4db7c41b1e4978ff45cbcd36123bb20c988447c486e7fdb8b8bee` |
| `fmt-final.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `browser-restart.json` | `1930f779a5d22cbb4d112cfd1181e34d51062e44d68e00634b1d5b7509ccb7b3` |
| `oauth-restart.json` | `1930f779a5d22cbb4d112cfd1181e34d51062e44d68e00634b1d5b7509ccb7b3` |
| `deployment.log` | `411f30d4837b25b6707aee26b96ce0ff50889d442da658c85a3ea5973dcfec2a` |
| `lab.tap` | `5fcf8bc0bb6de13434919b52ac3fb15877913f1986f524563b40b4cc9c2cab77` |
| `ui.tap` | `2554003949a192de63cfba05399702980002b28c5a50be894dbf64083f5a2a16` |
| `proxy.log` | `97fe685343a8ce46d1df65566c1fbe4b375507aa4ae1ffc16c6216fa18e399e8` |
| `browser-route-before.log` | `3f969c17b95b9bfb2b31423ee47ca82dad21f6c3f46d350df373b7c3961ebe7b` |
| `browser-store-race-before.log` | `4640251f649b11020ad6c71efa859bec4d7b47c57fd7c2eda3e15214c82da22d` |
| `rust-final.log` | `acf7944d7672450c7fea25383da8d03c22474db74d37ee711d7ab8634502169d` |

## Remaining gates / continuation

Publish the recovered round2 plus round3 exact source tree and run native Windows/Ubuntu compilation, portable contracts and Ubuntu PostgreSQL restart CI. Windows database execution is not implied by portable compilation. Independent real-browser cookie/CSP/303 validation, trusted provisioning CLI, public ingress throttling, backup anti-rollback, local signed-grant projection, authenticated WSS, durable request reconciliation and actual MCP dispatch remain open. Keep Issue #41 open through publication/review; do not mark overall ISSUE-013/014/016 complete.

No existing desktop/runtime/installer dependency or production data was changed. The supplied VPS stays untouched. CentOS EOL, Engine-version and same-origin application-trust checks remain deployment gates. This is still a library increment, not a complete production executable or a ChatGPT-tested Gateway. **UNCONFIRMED_ON_REAL_HOST**.

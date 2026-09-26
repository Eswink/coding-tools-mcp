# Round 5 — Device-owned authority projection

Date: 2026-09-21. Issue #43 / ISSUE-014A, parent #38, Epic #32, PR #36.
Status at implementation commit: **LOCAL_PROJECTION_ENGINEERING_VERIFIED / PUBLICATION_PENDING / NOT_FULL_GATEWAY**.
No physical workstation, live VPS, browser engine, ChatGPT, DNS, WAF or installer tests run in this increment. These are deferred by user and do not block isolated engineering.

## Recovered baseline and scope

Recovered published base `5ad89711e67eeb907d496a32a1b54a3f82500c55` from the digest-verified source bundle. Restored round4 local commit `a06a48f24c2b45ba2bebb96a8f35f1542127f29a`, tree `06251b81dae6fd479c09764aae951733da3ab2b9`; verified every round4 manifest hash and the bundle prerequisite. The previous blocked plan was resumed, not recreated. Its original failures remain in the historical evidence.

Added only services/cloud-gateway projection module, migration, tests, isolated CI and spec updates. No changed existing device/OAuth/desktop authorization function. The public identity-only router does NOT expose projection mutation or execution. A future authenticated channel must invoke these internal APIs; `ProjectionDecision::Eligible` is explicitly not an execution permit.

## Implemented boundaries

- Trusted one-device connector binding; enrollment or OAuth alone creates no grant.
- Domain-separated Ed25519 snapshots bind exact issuer/resource/connector/device/registry epoch, boot/challenge, monotonic revision, local authority epoch, original grant, scopes and expiry. Signed input is bounded; unknown/duplicate JSON fields rejected.
- Device registry lock + connector row lock, bounded waits and time recheck. New challenge invalidates cached eligibility; exact duplicate is idempotent with no freshness renewal. Device-epoch changes invalidate cached projection too.
- Active owner cannot transfer or extend grant silently. Draining -> Free requires signed acknowledgement of the exact old grant; Free raises the durable revoked-through epoch. Next grant requires a newer epoch. Lease expiry and Offline are not drain acknowledgement.
- Activation installs a new boot fence and reconciled=false. Old handles and captured proofs cannot revive restored grant data. A fresh local proof is required; no claim of protection against simultaneous rollback/compromise of cloud and authoritative device stores. Stop/restart is mandatory for database restore; live rewind is unsupported.
- Foreign-chat decisions reveal no owner, phase, presence or workspace details and allocate no per-chat pending records. Cloud stores only minimal opaque authorization state, not raw session/challenge, files or execution payloads.

## Actual local validation

Development container, Rust 1.98.1 and disposable PostgreSQL 16 (not a physical user's workstation):

| Suite | Result |
| --- | --- |
| Projection signatures/bounds/shape | 16 PASS |
| Projection PostgreSQL transactions/races/fencing/restore | 32 PASS |
| Full Rust suite including old identity/browser/CLI | 139 PASS, 0 failed/ignored |
| Actual binary/process/TCP/HTTP/PostgreSQL service cases | 30 PASS, no Agent/browser |
| Existing protocol lab | 32 PASS |
| Existing offline UI source contracts | 8 PASS |
| Existing fault proxy | 8 PASS |
| Existing deploy renderer | 13 PASS |
| fmt, all-target Clippy | PASS, no final warnings |

Portable signature tests have a new read-only Windows/Ubuntu workflow. PostgreSQL cases are included in the existing identity workflow's full Ubuntu database suite. Local PASS does not imply those remote runs have occurred; publication evidence will be linked separately.

## Failure-first and review evidence

1. A new regression `changed_registry_epoch_invalidates_cached_projection` failed: cached state still returned Eligible after registry epoch advanced. Fixed by persisting `snapshot_device_epoch` and checking it against the locked registry on assessment. Initial result 27/28 database cases PASS, one FAIL; after fix all 28 passed, then expanded to 32 cases. Failure retained, no assertions weakened.
2. Initial test compilation had a RecoveryRequired enum-name collision; corrected explicit imports, no product behavior change. Initial unused import was removed before Clippy.
3. Development-only PostgreSQL relocation initially failed because an older bundled glibc shadowed the system loader, then because fixed share paths were absent. Used system glibc with isolated ICU compatibility libs and container-only PostgreSQL share/lib symlinks. No production OS or server change; original setup errors retained separately from product tests.
4. Graph impact for verify_grant/revoke_device/assess/apply is LOW but Rust callsite coverage omits known tests. New-symbol queries initially UNKNOWN; exact path disambiguation used for apply. Manual review checks transaction/lock order, immutable grants, challenge replay, database restore limits and absence of public execution routes. Automated graph/review guidance is not independent security certification.

## Rollback and continuation

Remove new callers/module export only after stopping the authority controller; retain additive schema and epoch tombstones. Do not use an old authorization database as a rollback mechanism. Parent #38 still needs paired Agent/UI reconciliation and local admission integration. Next: authenticated outbound device channel with bounded frames/generation/disconnect, then durable request ledger and local execution tickets. Codex-inspired PTY/policy/sandbox tools remain after the safe routing foundation. Main and current desktop packages remain unchanged.

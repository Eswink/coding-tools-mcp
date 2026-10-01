# Full-scope Release Candidate notes — draft, not published

Status: **NOT RELEASED**. Version and final source commit are not frozen. This document must not be copied to a public Release with unresolved placeholders or failing gates.

## Highlights

The candidate integrates cloud OAuth identity and an authenticated outbound desktop Agent with locally owned conversation authorization, local admission and actual workspace tools. OAuth/device authentication does not grant workspace execution permission.

The candidate also includes managed Git worktrees, native owner-approved Hooks, durable execution/root recovery fences, Ubuntu mandatory isolation and guarded Linux workspace snapshot restoration. Windows isolation and full snapshot metadata acceptance remain unresolved and block full-scope release.

## Implemented / fixed, pending final acceptance

- #34: shipped-Rust modern and both legacy protocol matrices, real authenticated WSS fixture reads and empty HTTP 202 notification correction pass in exact `1281915` hosted real-transport jobs; final release acceptance remains pending
- #37, #41, #42, #45: runnable identity service, owner browser consent, PKCE, token rotation/replay protection and browser-compatible strict Origin policy
- #38, #43, #44, #46, #81: locally issued grants, signed projections, live Agent channel, generation fencing, bound results, durable reconciliation and no automatic uncertain mutation replay
- #39: shipped invitation/redemption/revocation commands and device-local key/proof flow are implemented; exact `1281915` hosted enrollment contracts and eight real PostgreSQL/process bootstrap cases pass. Windows/full-release gates remain separate
- #70: in-process managed worktree lifecycle, private ownership records, path containment, dirty-state refusal and isolated native profiles
- #73: Ubuntu admission/policy-first sandbox enforcement, filesystem/network limits, bounded output and process cancellation
- #84: devalue updated to5.9.4 with malformed-reference regression and aligned npm/pnpm locks
- #85: patched Rustls and the exact two-line upstream GLib 0.18.5 backport are integrated. Exact `1281915` Ubuntu source checks retain five upstream SIGSEGV controls and nine optimized patched passes; separately downloaded four-binary engineering archives have exact-build reachability/audit proof. Raw RSA/advisory and maintenance-warning records remain visible; final-source audits are still required
- #86: snapshot opened-root authority binding remains blocked: the required repair is unimplemented/unverified and outside this documentation increment
- #40: exact `2602478` nonproduction container topology passed 14 cases plus cleanup; downloaded source/tree/binary/audit bindings were verified. The mandatory FINAL DAG must rerun topology on the frozen final source; real VPS deployment remains deferred
- #87: the read-only RC-tag evidence route passes exact `1281915` provenance tests on Ubuntu and Windows; actual tag-event and successful full FINAL-DAG validation remain pending
- #88: a full-scope RC publication consumer is still missing. Its first increment is design-only/nonpublishing; a separately reviewed publisher and real final evidence are required

A source implementation or an old passing run is not a completed issue. Final issue classifications and exact evidence belong in the release ledger.

## Security

Local approval remains the execution authority. The cloud cannot create or enlarge a local grant, change its workspace, bypass pause/revoke or request unsandboxed execution. Required isolation fails closed when unavailable.

Accepted or uncertain mutations are never automatically replayed after disconnect or restart. Device generations, request digests and result bindings fence stale replies. Root-wide quiescence and durable recovery markers prevent conflicting work or automatic recovery through unknown state.

No production credentials, device private keys, OAuth secrets or user data belong in release artifacts. Windows runtime capability changes require explicit review; ordinary AppContainer is not accepted as equivalent to the stronger LPAC boundary.

## Platforms and automated validation

Required targets: Windows x64; Ubuntu amd6422.04 and24.04. Other platforms are not claimed.

Engineering baseline: `1281915b38c2364c4476ca94aabae3043423ed5f`, tree `a0e84eb7e7f237b64908058e5a5ee1f306752ca4`. [Integration 36773728707](https://github.com/Eswink/coding-tools-mcp/actions/runs/36773728707) has six non-Windows jobs PASS and Windows FAIL: 599 passed / 6 failed / 0 ignored, plus four production warning errors. Both Ubuntu native library suites pass 665 tests; the health repair and three actual credential/restart cases on Windows and each Ubuntu OS pass. [Provenance 36774018809](https://github.com/Eswink/coding-tools-mcp/actions/runs/36774018809) passes 78 tests per OS with zero skips. All nine evidence ZIPs were downloaded, hash/integrity checked and bound to the exact source/tree or committed browser manifest; see the [current ledger checkpoint](next-rc-ledger.md#current-engineering-evidence--2026-10-01).

These results do not establish final-source/version acceptance, the FINAL packaging DAG or an actual RC-tag event. Before publication, replace this engineering baseline with the approved final candidate SHA and successful complete regression, audit and installed-package evidence. A later docs-only commit does not inherit these exact-source CI results.

## Known limitations and external acceptance

- No production VPS, BaoTa/Nginx/WAF/DNS/TLS configuration has been changed or verified
- No real ChatGPT-account interoperability or physical Windows/Ubuntu workstation acceptance is claimed
- Hosted CI cannot establish all Secret Service, notification, FUSE, Wayland, antivirus or organization-policy behavior on the user's machines
- Installer signing status must be read from the actual final artifacts; signing has not been established
- Windows isolation and metadata/recovery implementation gates are **coding blockers**, not external acceptance deferrals
- Existing CentOS Stream8 deployment assumptions are unsupported; an Ubuntu build does not prove compatibility

## Upgrade and rollback

Do not upgrade production from this draft. For a published RC, stop new work and prove all accepted tasks/process trees have drained before replacing binaries. Preserve local configuration, native credential entries, revocation state and encrypted journals; make operator-controlled backups without exposing credentials.

Rollback requires a previously verified installer/binary set and a schema-compatible state strategy. Reinstalling an older binary is not permission to restore stale grants, reset journals or roll back database revocation history. If a mutation outcome is unknown, keep execution fenced and reconcile it explicitly rather than retrying it. Keep the prior immutable tag/assets and do not overwrite release history.

## Artifacts and checksums

The three `fde46cc6299be88ffcf6b3fa3236d222dbdda7b1` engineering NSIS/DEB/AppImage files were downloaded and hash-verified against five installed receipts, including four Ubuntu 22.04/24.04 format/OS combinations and Windows standard-user acceptance. They retain `0.6.0-rc.4`, the Windows regression failure and the unsigned-Windows limitation. They are not final `1281915` or owner-selected-version assets.

Final builds remain pending: Windows NSIS, Ubuntu DEB/AppImage, standalone four-binary cloud bundle and evidence/checksum files. Publish only artifacts built from the final selected source and product version. Record every filename, byte size and SHA256, verify downloaded bytes, and link the final SHA256SUMS file here. The [#88 consumer](https://github.com/Eswink/coding-tools-mcp/issues/88) must verify authenticated FINAL artifact bytes before any separately authorized publication.

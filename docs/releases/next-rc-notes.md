# Full-scope Release Candidate notes — draft, not published

Status: **NOT RELEASED**. Version and final source commit are not frozen. This document must not be copied to a public Release with unresolved placeholders or failing gates.

## Highlights

The candidate integrates cloud OAuth identity and an authenticated outbound desktop Agent with locally owned conversation authorization, local admission and actual workspace tools. OAuth/device authentication does not grant workspace execution permission.

The candidate also includes managed Git worktrees, native owner-approved Hooks, durable execution/root recovery fences, Ubuntu mandatory isolation and guarded Linux workspace snapshot restoration. Windows isolation and full snapshot metadata acceptance remain unresolved and block full-scope release.

## Implemented / fixed, pending final acceptance

- #34: modern and legacy protocol source reconciliation; shipped-Rust negative tests and legacy notification response correction pass locally; final CI pending
- #37, #41, #42, #45: runnable identity service, owner browser consent, PKCE, token rotation/replay protection and browser-compatible strict Origin policy
- #38, #43, #44, #46, #81: locally issued grants, signed projections, live Agent channel, generation fencing, bound results, durable reconciliation and no automatic uncertain mutation replay
- #39: invitation and device-proof foundations exist; shipped device-local bootstrap commands and real process tests now pass locally; final native/cumulative CI pending
- #70: in-process managed worktree lifecycle, private ownership records, path containment, dirty-state refusal and isolated native profiles
- #73: Ubuntu admission/policy-first sandbox enforcement, filesystem/network limits, bounded output and process cancellation
- #84: devalue updated to5.9.4 with malformed-reference regression and aligned npm/pnpm locks
- #85: desktop TLS lock updated to patched Rustls; gateway optional RSA lock finding remains under explicit build-reachability review
- #86: snapshot opened-root authority binding remains a release-blocking repair
- #40: deployment/build preparation is being reconciled with actual protected-file CLI contracts; historical templates are not a verified deployment

A source implementation or an old passing run is not a completed issue. Final issue classifications and exact evidence belong in the release ledger.

## Security

Local approval remains the execution authority. The cloud cannot create or enlarge a local grant, change its workspace, bypass pause/revoke or request unsandboxed execution. Required isolation fails closed when unavailable.

Accepted or uncertain mutations are never automatically replayed after disconnect or restart. Device generations, request digests and result bindings fence stale replies. Root-wide quiescence and durable recovery markers prevent conflicting work or automatic recovery through unknown state.

No production credentials, device private keys, OAuth secrets or user data belong in release artifacts. Windows runtime capability changes require explicit review; ordinary AppContainer is not accepted as equivalent to the stronger LPAC boundary.

## Platforms and automated validation

Required targets: Windows x64; Ubuntu amd6422.04 and24.04. Other platforms are not claimed.

Before publication, replace this section with the final candidate SHA and successful run links for frontend, Rust, PostgreSQL, authenticated TCP/WSS, real browser, native credential restart, admission/sandbox, worktree/Hook/snapshot and installed-package tests. Current cumulative CI is not all green.

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

Pending final builds: Windows NSIS, Ubuntu DEB/AppImage, standalone cloud executable bundle and evidence/checksum files. Publish only artifacts built from the final selected source and product version. Record every filename, byte size and SHA256, verify downloaded bytes, and link the final SHA256SUMS file here.

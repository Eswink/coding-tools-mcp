# Round 3 publication and remote acceptance

Date: 2026-09-21. Classification: **BROWSER_IDENTITY_ENGINEERING_VERIFIED / NOT_DEPLOYABLE / HOST_UNCONFIRMED**.
Tracking: [Issue #41](https://github.com/Eswink/coding-tools-mcp/issues/41), parent #37, Epic #32, Draft PR #36.

This addendum resolves the publication-pending status in round2-validation.md and round3-validation.md. It does not rewrite their historical local evidence or close deployment/Host gates.

## Source identity

| Increment | Original local commit | Published commit | Exact shared source tree |
|---|---|---|---|
| Round 2 identity primitives | `4b6f197118d818735d77d23d9f8593976abdb702` | `d4747224edfefda52deb29458138e7282b5e62c9` | `d38905bc9684ca2c066de331a42eabaee2c0bcea` |
| Round 3 owner browser consent | `5b55ba5eaaaea11d8c2322bbaa5980980cc8ad48` | `0f39460857a9c78a6c1ac8cd5e522b2174875fcf` | `92ea0acab1281db6feb85f02c14290235eabff3e` |

The native connector created new commit metadata; source trees are identical. Both published commits extend the previous remote head `ba9c379f08da37f2a05bb96c377a95f432da969e`. Feature branch `feat/cloud-gateway-agent-runtime` was fast-forwarded with force=false only after verifying its unchanged base. Main was not moved.

Remote PR tests checked synthetic merge `0f8e2b2e7e6f16903b09ca65a0eaee70d20c350d`, whose tree is also `92ea0acab1281db6feb85f02c14290235eabff3e`. The downloaded source bundle verifies this, its parents, and the exact published commits. All 81 PR-changed files match the Ubuntu checkout byte-for-byte; all Windows candidate hashes match the exact LF-to-CRLF checkout transformation. No source discrepancy was ignored.

## Verified remote gates

| Run | Actual scope | Result |
|---|---|---|
| [35589508195](https://github.com/Eswink/coding-tools-mcp/actions/runs/35589508195) | Independently reconstruct exact local commits, 68 Rust tests, both process/PostgreSQL restart probes and prior contracts; verify imported blob hashes | PASS |
| [35589952054](https://github.com/Eswink/coding-tools-mcp/actions/runs/35589952054) | Ubuntu PostgreSQL: 68 tests; OAuth and browser-flow restart probes; actual Compose 2.27.0 and Nginx config/routing checks | PASS |
| Same identity run | Windows 2025 and Ubuntu 24.04: all-target Clippy, formatting, 10 pure Rust contracts and 13 deployment-render contracts on each | PASS |
| [35589952055](https://github.com/Eswink/coding-tools-mcp/actions/runs/35589952055) | Windows/Ubuntu: 32 protocol-lab, 8 UI-source, 8 fault-proxy contracts each; graph/spec job | PASS; spec 0 errors / 0 warnings |
| [35589952090](https://github.com/Eswink/coding-tools-mcp/actions/runs/35589952090) | Existing frontend check/build/regressions and existing Windows/Ubuntu Rust checks/regressions | PASS |

The full 68 database/browser Rust tests ran on Ubuntu, **not** on Windows. Portable Windows compilation/tests are not Windows desktop installation, native browser or full database acceptance. Nginx tests used an isolated CI process, not the user's BaoTa/WAF. Compose was parsed without starting a Docker daemon. No live VPS, device channel, source-file execution or ChatGPT Host behavior is validated by these results.

## Artifact integrity

The following archives were downloaded, ZIP-integrity checked and SHA-256 matched to GitHub metadata. Logs were read to verify counts and restart/config results.

| Artifact ID | Archive SHA-256 |
|---|---|
| 10634111654 — identity Ubuntu | `9565959a7668e479ad76eb59001415001c3cb8e79976dfe658bdbc7563257391` |
| 10634036704 — identity Windows | `9a5e1d327a90504c9ee11b09b746c9acf14a1d5cf0d3d7e0a7a3889f185d4d4e` |
| 10633759160 — identity PostgreSQL | `0d4ecbc1cbfaec223002bc1f15dc48d6904deb75f51dd7636c893d1506ed5a32` |
| 10633759035 — graph/spec/source | `eb026a9d3d0df75dac2a637612bc23a4e00b5c7fd01141f48b3eea4bc708275d` |
| 10633848628 — lab Windows | `ecbb73cad8731f262a3a3890963493276cd7f0658df7c19839c7ccc4ef659af8` |
| 10633594287 — lab Ubuntu | `5c0e6f5c453856c19880776d616946f8bd8fa859ee251fb9ac1a4dc18ec59cb0` |
| 10634166048 — blob import receipt | `53ea6214f4af343ce7eb1952021a2061a1e4f07763879e80e1ac08322ca5e673` |

Artifacts use finite CI retention; keep source-linked hashes and regenerate evidence when necessary.

## Failures preserved

The browser expiry-after-client-lock regression failed before the transaction fix and passes afterward; see round3-validation.md/review.md. The POST-authorize assertion changed from 404 to 405 because GET-authorize now exists, with no-Location/zero-code assertions added. This did not enable a direct remote issuance endpoint.

Publication run 35589003623 passed source verification but its import job failed on POST git/trees with HTTP 403. No branch ref changed. Instead of expanding the workflow token permissions, the isolated helper was narrowed to blob upload only; run 35589508195 repeated verification and imported 65 hash-verified source blobs. The explicitly authorized native GitHub connector then created both exact trees/commits and fast-forwarded the feature branch. The recovery branch is a one-shot transport aid and must never be merged into main; no helper or binary parts are present in the feature source tree.

## Issue progression and next boundary

Issue #41 implementation and cross-platform engineering gates are verified. Keep it open for the independent browser/interoperability release review. Newly opened [Issue #42 / ISSUE-013C](https://github.com/Eswink/coding-tools-mcp/issues/42) owns the next bounded increment: runnable service, trusted owner provisioning CLI, limits/readiness and actual browser-engine acceptance. This is a child refinement of ISSUE-013, not an extra autonomous-agent feature.

Then continue #38 local-grant projection and #39/ISSUE-017..021 authenticated outbound Agent channel, fencing and durable request reconciliation. Cloud OAuth consent must never create local workspace authority; uncertain execution is not automatically replayed. Codex-inspired PTY/policy/sandbox enhancements remain later in the roadmap, after the early secure offline Host PoC.

No public deployment command, production image, existing desktop changes, Nginx/DNS/WAF modifications, credentials transfer, installer/release or merge-to-main occurred. The whole project remains active. Real Host truth label: **UNCONFIRMED_ON_REAL_HOST**.

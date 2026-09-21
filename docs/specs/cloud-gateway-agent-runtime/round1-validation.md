# Round 1 candidate acceptance and continuation

Classification: **M1_PROTOCOL_LAB_VERIFIED / NOT_PRODUCTION / HOST_UNCONFIRMED**.
Date: 2026-09-21. Tracking: [PR #36](https://github.com/Eswink/coding-tools-mcp/pull/36), [Epic #32](https://github.com/Eswink/coding-tools-mcp/issues/32).

## Exact tested candidate

- Source commit: `82c20d3d26f32e41a4238b590b42dfe53d697c8d`.
- Git tree: `902d66ff5b6bfaf447dcfeaab0f389851e998ee6`.
- Protected desktop/main baseline: `758c60a6e74e624e144f9c19c5f19d04d17f7a13`.
- [CI run 35564597505](https://github.com/Eswink/coding-tools-mcp/actions/runs/35564597505), attempt 1, all three jobs succeeded.

| Environment / job | Actual checks | Result |
|---|---|---|
| Windows 2025 | 32 HTTP/CLI + 8 existing UI + 8 Python fault-proxy tests | PASS; zero skipped |
| Ubuntu 24.04 | 32 HTTP/CLI + 8 existing UI + 8 Python fault-proxy tests | PASS; zero skipped |
| Pinned graph / specification | Candidate diff impact and parent-child check_spec | PASS; 0 spec errors / 0 warnings |
| Local Node 22.16.0 | Same 32 HTTP/CLI contracts, final publication rerun | PASS |

The 8 UI checks are source-level contracts, **not Svelte browser interaction or desktop installation tests**. Native Rust/package/GPU/workspace execution and real ChatGPT behavior are not validated by this lab.

## Artifact verification

| Artifact | ID | Archive SHA-256 |
|---|---|---|
| cloud-gateway-contracts-windows-2025 | 10623710600 | `62d3538403faea0b9c8d2d5438e77cd183ca991e1a9438052aecb4dfba38472b` |
| cloud-gateway-contracts-ubuntu-24.04 | 10623501228 | `04f6cb22b2854f56d4979b8c1d604455030ea3f5c90e1d562c95ba70de804cce` |
| cloud-gateway-impact | 10624190368 | `ee07ebeba7d37edc1fed68b6d76cac5c040b6c52a8157acc6ae226ee4cd10989` |

Downloaded all three archives and checked their reported digests. The source bundle points to the exact candidate tree. Ubuntu candidate hashes match all 31 locally tested files byte-for-byte. Windows checkout hashes differ only by the expected LF -> CRLF conversion, verified for every file; no source-content discrepancy was ignored. Artifacts expire according to workflow retention, so retain these source-linked IDs/hashes and regenerate evidence when needed.

## What is now established

The synthetic worker can transition online/offline without changing public discovery or catalog responses. Valid owner offline calls produce a normal MCP tool error without an OAuth challenge; invalid credentials still reject authentication. Foreign chats cannot distinguish presence through denial bodies; offline requests create no fresh pending allocation. Limits, header validation and actual local HTTP/CLI processes pass both runner platforms.

The laboratory is explicitly synthetic, loopback-only and incapable of local file/command execution. It is **not** a deployment candidate, OAuth implementation, real agent connection, durable idempotency system or complete MCP compliance certification.

## Next bounded implementation increment

1. Open ISSUE-013 / ISSUE-014 / ISSUE-016 as actual GitHub issues, with security acceptance and dependencies before implementation.
2. Build the production Rust/Axum gateway identity boundary separately from this lab: stable resource/issuer, proper OAuth/PKCE/client validation and refresh continuity while no Agent exists. Credentials remain server-side; tests use canaries.
3. Implement one-time device enrollment and authenticated outbound Agent channel. Bind route, device, grant, request digest, expiry and generation; a cloud ticket must not override the local grant.
4. Add durable request reconciliation and disconnect fault tests before wiring existing mutating tools. Unknown outcomes are never silently replayed; new offline work is not queued.
5. Deploy only an isolated test route after the user supplies VPS OS/architecture, domain/TLS/proxy topology and a secure deployment channel. No production secrets in issues, source or chat.
6. Run the first real ChatGPT online -> Agent exit/power-off -> offline refresh -> recovery experiment before building all advanced Codex-inspired features.

The overall 36-issue plan remains active. Existing high-impact interceptor and runtime extraction require a fresh impact review. No cloud deployment, DNS cutover, production secret transfer, release, installer update or merge to main has occurred in round 1. Real host truth label remains `UNCONFIRMED_ON_REAL_HOST`.

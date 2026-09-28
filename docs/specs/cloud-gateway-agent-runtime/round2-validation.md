# Round 2 — local identity and deployment-contract validation

Date: 2026-09-21. Base: `ba9c379f08da37f2a05bb96c377a95f432da969e`.
Branch: local `work/cloud-identity-round2`; remote PR #36 is not updated by this session.
Classification: **IDENTITY_CORE_LOCAL_VERIFIED / NOT_DEPLOYABLE / NOT_PUSHED / HOST_UNCONFIRMED**.

## Actual evidence

| Check | Executed result | Boundary |
|---|---|---|
| Rust pure contracts | 10 PASS | Policy/signature/config primitives |
| PostgreSQL identity contracts | 15 PASS | Real SQL transactions, PKCE, refresh rotation/concurrency/replay/expiry |
| PostgreSQL device contracts | 3 PASS | Real proof/one-time redemption/revocation |
| HTTP adapter + PostgreSQL | 10 PASS | Includes an actual TCP listener, headers/limits and malformed-Origin regression |
| New process + PostgreSQL restart | PASS | Fresh private cluster restarted, saved access and refresh used by a new process; no Agent exists |
| Deployment Python contracts | 13 PASS | Rendering, path/host injection, loopback/private DB, no-overwrite and readiness blockers |
| Actual Compose 2.27.0 | config PASS | No Docker daemon, image pull, container start or VPS connection |
| Actual Nginx 1.24.0 | syntax + isolated loopback HTTP PASS | Root route retained; prefix/metadata paths retained; foreign Host rejected; forwarded Host stripped |
| M1 Node protocol lab | 32 PASS | Existing synthetic protocol tests unchanged |
| Existing UI source contracts | 8 PASS | Not browser or native installer tests |
| Existing fault proxy | 8 PASS | Python synthetic failure contracts |
| Rust fmt + clippy all-targets | PASS | Zero warnings in final run |

Rust: 1.98.1. PostgreSQL: 16.15 (Ubuntu package). All executed results are from this Linux development container, not the user's CentOS server or a Windows host. The new Windows/Ubuntu CI workflow is authored but **not pushed or executed**. An older CI run for the parent revision is not evidence for this increment.

## Failure-first correction

Adversarial HTTP tests found that the URL parser repairs a backslash/missing-authority Origin into a trusted URL. `malformed-origin-before.log` records the failing test (exit 101). The fix requires an already serialized origin, allowing normal case/default-443 equivalence without accepting repaired strings. The focused test and entire suite then passed. A post-test-file-split unused import also failed strict Clippy; it was removed and Clippy rerun successfully. No intermediate failure is reclassified as a success.

## Scope and review

All new implementation is in `services/cloud-gateway`. New deployment code only renders a new review directory. Existing desktop/Tauri/runtime/OAuth/worker code is untouched. The existing M1 CI scope check now permits the new isolated directories, but its test semantics are unchanged. Generated planning/graph tool changes to AGENTS/CLAUDE/skills are excluded from the patch.

Graph analysis reported HIGH impact for the existing desktop `intercept`; it was not changed. The new `allow_origin` fix had a LOW graph result; source review additionally confirmed its identity HTTP boundary caller. Graph full-text search is unavailable in the offline tooling environment, so this is not claimed to be a complete call-graph/security audit. A forced full rebuild repaired missing-ID/incremental graph artifacts; the aggregate still reported CRITICAL (16 flows) and remains recorded, with protected Git-object identity verified. A pinned graph diff and deterministic code-review helper are used alongside manual review and real tests, not as substitutes for them. Bounded architecture validate/drift passed after correcting metadata shape and the distinction between test teardown and legacy-path cleanup.

## Not established

No complete authorization server or public Gateway binary/image; owner login/state/CSRF/consent and public authorize endpoint missing. No real Agent transport, signed-grant projection, distributed execution journal, local shell/files/sandbox enhancement or cloud tool dispatch. No desktop installation, CentOS runtime, Baota WAF, production TLS, server access, DNS change, backup restoration or real ChatGPT test was performed. `UNCONFIRMED_ON_REAL_HOST` remains exact.

## Deployment-specific decisions

Use the supplied existing Nginx/Baota 443 entry; review-only locations use `/coding-tools/`, exact OAuth metadata routes, and a planned loopback upstream at 28880. Do not replace the current site. Supplied CentOS Stream 8 is out of updates; report a supported-host/security gate rather than automatically upgrading. Docker Engine version is unknown; Compose 2.27.0 does not prove Engine version or safe localhost publishing. No automatic WAF/firewall exceptions, production credential generation or service reloads.

## Publication and continuation

GitHub APIs available in this session are read-only; container GitHub DNS is unavailable. The increment is committed locally and delivered as an exact-base patch/bundle with source/evidence hashes. No remote issue, PR status, release or branch update is claimed.

Next bounded increment: trusted owner authentication and CSRF-safe OAuth consent controller; completed grant projection and enrollment UX; then authenticated outbound Agent channel with generation fencing and durable non-replayed request outcomes. Run new native CI after publication, and a secure isolated VPS/real-ChatGPT PoC before advanced Codex-inspired tool features. Publishing/deployment restrictions do not justify weakening authentication or queueing offline mutations.

# Issue #74 — retained test-listener ownership

Parent: Epic #32 / Draft PR #36. Baseline: `6fe8f8a3f1dc55dc1e2f9704fa65586a8a1d2ecd`.
Status: implementation candidate; native Windows/Ubuntu and official release-candidate gates remain required. No main merge, deployment or release authorization.

## Failure and evidence boundary

Official release-candidate run `36154924658`, Windows 2025 job `108137017396`, failed in `auth::chat_http_tests::offline_new_authorization_is_a_non_oauth_tool_error_and_resumes_cleanly` before any authorization assertion. The startup error was `MCP 本地端口 64506 绑定失败` / Windows error 10048. The corresponding Ubuntu job passed. Retained Windows artifact `10872987633` SHA256: `933d05f33c3cd70ef4a9a6bbceea14c7f97d5378faf6962b8b2de9733dbcd4f4`.

All four tests in `聊天HTTP回归v1.rs` obtained an ephemeral port using a bound `std::net::TcpListener`, dropped it and supplied only its port number to the runtime. No owner protects the port between those operations. A deterministic Linux/Python socket experiment forced a competing listener into this gap in 100/100 iterations; retaining the original listener excluded the competitor in 100/100 iterations. This proves the ownership gap, **not** the identity of the original Windows competitor or native Rust acceptance. There is no evidence attributing that owner to PTY or issue #62.

## Minimal design and protected behavior

The production entry point retains its signature and still invokes `bind_listener(port)` synchronously at the original initialization point. Its initialization body is extracted into a private function accepting a one-shot binding closure; the body otherwise changes only from `bind_listener(port)?` to `bind()?`. Session policy validation, storage setup, OAuth/public-origin resolution, error ordering, serving and shutdown are preserved. The original platform-specific `bind_listener` is unchanged. There are no retries, alternate ports, sleeps, authority changes or authentication/origin exceptions.

A `cfg(test)`-only helper accepts an owned, already-bound IPv4 loopback `TcpListener`, obtains its actual port, marks it nonblocking and moves the same socket into Tokio. The four HTTP fixtures now transfer that ownership instead of releasing and reacquiring it. Existing authorization assertions are retained. Shutdown joins have a five-second bound.

Two additional native regressions verify that an occupied **requested** port still returns a synchronous startup error, and that retained ownership excludes duplicate binds both before and after handoff while serving discovery at the same endpoint. The conflict test obtains the competitor's port directly and keeps it alive, so the regression itself introduces no reserve/drop/rebind race.

## Plan and impact evidence

Pinned `mcp-probe-kit` 4.0.1 `resume_plan` found no recoverable plan in the downloaded repository; a separate `start_bugfix` plan was persisted:
`bugfix-issue-74-epic-32-draft-pr-36-baselin-b9838c6d80`.
Checkpoints record gap, context, acceptance, cause, design and implementation. Parent delivery remains active.

Fresh GitNexus 1.6.9 analysis on the exact baseline reported HIGH impact for `spawn_listener_with_origin_and_execution_gate`: eight direct callers, forty upstream symbols and three processes. This was reported before editing. Each of the four affected HTTP tests reported LOW/zero upstream impact. The graph's unavailable full-text extension and Rust-resolution limits are not security certification; exact-symbol graph results were supplemented with call-site review and initialization-body comparison. Generated AGENTS/CLAUDE/skill changes are not part of this candidate.

The first incremental staged graph reported CRITICAL/183 flows and falsely made the new Rust test a method of unrelated Python/TypeScript classes. A forced full, index-only rebuild removed these invalid incoming edges; the retained full staged result is HIGH/14 flows. Neither result is discarded: the incremental failure is preserved as a tooling limitation. The staged Git diff contains eight files; graph symbol mapping reports seven and does not replace the explicit full-file review.

The existing delivery scope guard gains only three exact reviewed paths: the test-support module, the MCP module re-export and the existing chat HTTP regression file. It does not permit a broad desktop prefix. Positive digest and negative `.bak` cases exercise the actual inline CI guard, not a duplicate allowlist.

## Verification gates

- Local socket-mechanism experiment: 100/100 forced old handoff conflicts and 100/100 retained-owner exclusions; Linux/Python only.
- Local actual-scope-guard contracts: 49 passed, zero failed; complete cloud-gateway JavaScript suite: 81 passed, zero failed. Original assertions and initialization ordering are compared against the baseline.
- Native test workflow `cloud-gateway-listener-handoff.yml`: pinned Windows 2025 / Ubuntu 24.04, Rust 1.98.1, all-target check, ten separately invoked exact offline-authorization regressions, full parallel Rust suite and production `-D warnings`. Each exact invocation must report one passing test; zero-match success is rejected. Artifacts record source objects, outcomes and log hashes, including failures.
- Staged GitNexus `detect_changes`, actual-diff review and source identity are required before publication. Native workflow completion and official `发布候选验证v4` on the published feature must be checked before closing #74.

The local environment has no usable Cargo toolchain or external DNS; no local Rust/Windows PASS is claimed. Physical desktop/VPS/real-ChatGPT tests remain deferred, not passed. Native run IDs and final source/artifact receipts belong in the issue/PR publication record, not invented in advance.

## Rollback

Revert the single scoped handoff candidate commit on the feature branch after re-reading its head; do not force-push, reset main, change migrations or delete durable authority data. This restores the old fixtures and their known flaky handoff. The independent validation workflow can be removed with the same revert. Keep the original failing CI artifact and failed-attempt evidence. A documentation-only receipt can be reverted separately without changing runtime behavior.

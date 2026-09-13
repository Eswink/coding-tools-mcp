# Exclusive Conversation Refresh — Continuation Plan

Date: 2026-09-13
Status: IN PROGRESS; local continuation, not a new upstream release.
User instruction (verbatim): 继续任务执行
Approved parent: [plan.md](plan.md)
Initial recovered base: 83558bc1e4d6dd009324c6598e52be458ba9948a
Final patch base: ecf5ca9449a82122f26f2bef3f50ce6d0afd5488
Verified final base tree: 729b851322fb77d9b587588a6c85872038f67104

## Recovered state

The implementation and the plan were already saved before interruption. Do not restart the feature, duplicate the branch, or edit the separate public OAuth routing PR #11. Candidate run 34744014562 has successful Windows/Ubuntu source regression and failure-first jobs, but its browser job failed. Those successes belong only to the upstream base above, not to subsequent local changes.

## Bounded next iterations

13. Reproduce the browser readiness predicate failure in a zero-network Playwright contract test; fix the two function-valued wait predicates, preserve the actual component scenario, and improve failure evidence. A blank-page contract test is not the HTTP browser or installed desktop acceptance gate.
14. Recheck the authorization decision linearization point. Refresh the pending deadline while holding the decision mutex, not only before a potentially slow reconciliation. Add deterministic boundary/stale-decision tests; no wall-clock sleeps or skipped security assertions.
15. Inspect approval presentation and multi-workspace async completion handling. Fix only source-supported defects and add focused regressions. Keep fingerprint/scope/local-only approval rules unchanged.
16. Reconcile source/test evidence, run available local checks, export a base-pinned patch and checkpoint. Keep missing Rust/native/real-ChatGPT gates explicit; never transfer prior CI PASS to the changed revision.
17–20. Reserved for new measured failures after the changed candidate can run in CI. Do not manufacture rounds or rerun until green.

## Tool constraints and impact

Current GitHub discovery exposes read/search/download actions only; no code-write, ref update, PR creation, or workflow-dispatch action is available. The installed plugin search returns the same GitHub connector. The container has no Cargo/Rust toolchain or working external DNS; git ls-remote fails to resolve github.com. No credential is requested or recovered from unrelated files. Source and CI artifacts remain accessible through the read connector.

Probe resume/install and offline GitNexus impact were attempted and failed (missing launcher; EAI_AGAIN; ENOTCACHED). Manual call-chain assessment is a declared fallback, not graph validation. Authorization decision edits are security-sensitive: trusted local Tauri chat_authorization_control -> ChatAuthorizer::decide -> active record/owner phase -> permit/admit -> shared workspace side effects. Retain the public IPC contract, exact record ID/profile/binding checks, pending TTL, nonempty scope subset, and event invalidation after commit. Executor locks must not be acquired under the decision mutex.

The local browser can run isolated blank-page JavaScript but rejects the production fixture's localhost URL with ERR_BLOCKED_BY_ADMINISTRATOR. Do not remove browser policy or disable its sandbox. Preserve that separate gate as blocked and execute only independent permitted checks.

## Exit conditions

Local changes must be packaged with exact upstream SHA, changed paths, SHA-256 hashes, executed checks and unexecuted tests. No push/PR/release/deployment claim without a successful tool result. Resume from this checkpoint when repository writes and candidate CI are available.

## Upstream alignment update

During the continuation, the remote branch advanced by one commit to ecf5ca9449a82122f26f2bef3f50ce6d0afd5488. That commit independently fixes the two function-valued browser wait predicates. Its complete source workflow 34749675645 is successful, including 10 browser scenarios. Preserve that change and its comments; it is not a push performed by this continuation's available tools. The incremental patch is rebased by exact source-tree verification onto that upstream commit. The additional Rust and approval-queue changes are not covered by that successful CI run.

# Round 8 — request admission and durable no-replay ledger

Date: 2026-09-22. Baseline: `765664434a8016f05ce3a15fff87065506fbc7fc`.
Tracking: #49 / ISSUE-019A; dependencies #47 and #43. Status before remote publication: **LOCAL_ENGINEERING_VERIFIED / REMOTE_CI_PENDING / HOST_DEFERRED**.

## Local implementation evidence

- Added migration `0005_request_ledger.sql`; it persists only request metadata, hashes and fence identifiers. No raw tool arguments, command output, file contents, OAuth bearer material or Host session is stored.
- Added canonical JSON SHA-256, typed request class/state/denial, admission/reconciliation APIs, bounded in-flight/deadline policies and terminal-only purge.
- Admission locks/checks enrolled device, device epoch, projection, grant/conversation/scope, revocation floor, gateway boot, authenticated channel session/generation/lease and execution state in one bounded transaction before writing `admitted`.
- `begin_execution` rechecks the fence before `running`; it still is not an Agent execution permit.
- Exact duplicate request IDs reconcile to durable state. Changed inputs conflict. Offline denial stays terminal. Running/lost/old-boot work becomes `outcome_unknown`, never auto-replayed.

## Tests actually run in the development container

A disposable PostgreSQL 16.15 cluster on loopback was initialized from the previously verified public CI tool bundle. The exact current source used Rust 1.98.1 and an offline cargo registry from previously verified CI artifacts.

- New admission PostgreSQL suite: **19 passed** after retained failure-first fixes.
- Full cloud-gateway Rust suite: **245 passed, 0 failed, 0 ignored** across library, admission, identity/browser, channel, projection, Agent and service suites. The 22 new tests in this increment are 3 canonical-digest unit tests plus 19 PostgreSQL admission tests.
- `cargo fmt --check` and all-target `cargo clippy -- -D warnings`: PASS after refactoring two over-wide helper signatures.
- Delivery scheduler regressions after the manifest transition: **25 Python + 18 Node metadata contracts PASS**; release remained fail-closed and emitted zero next packets while request-admission was `in_progress`.
- mcp-probe-kit `resume_plan` 4.0.1 was executed first as required; no active/blocked managed plan existed, so the persisted issue/spec/manifest remained the delivery authority.
- A fresh GitNexus 1.6.9 index (`10,100 nodes / 23,001 edges / 300 flows`) and `detect_changes` ran before commit. The current ten-file change mapped to 9 symbols, 0 affected processes and **LOW** risk. FTS was unavailable offline, so full-text search was not used; this does not change the graph/diff result.
- Existing source was not connected to a production MCP dispatcher or local execution tool.

## Retained failures and fixes

The first admission PostgreSQL run had 13 PASS / 2 FAIL. Exact concurrent duplicate requests could both pass the pre-insert absence check and one failed at the unique key. A transaction-scoped advisory lock keyed by request ID now serializes retries before the existence check; the concurrency regression passes. The second failure was test-only: PostgreSQL `octet_length` returns `int4`, while the test requested `i64`; the assertion now uses `i32` without changing product behavior.

Clippy then rejected two helper functions with eight arguments. They were refactored into typed evaluation/insertion context structs rather than suppressed with an allow. Final Clippy passes.

## Pending publication gates

Remote Windows/Ubuntu portable and Ubuntu PostgreSQL CI are pending until the exact source commit is published. After those pass, update #49 and the delivery manifest to `verified`, then queue the next local-authority/execution-ticket issue. Real workstation, VPS, BaoTa/WAF and ChatGPT behavior remain explicitly deferred and not PASS.

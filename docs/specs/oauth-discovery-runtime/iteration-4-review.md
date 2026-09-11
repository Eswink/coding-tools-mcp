# Iteration 4: isolate lifecycle fixtures and preserve concurrency protection

Source: PR #10 head 68f3569d5500731e1cb8b16f81509b950c0328b6, tree 8c589b8f2769378782bd787edfb5d85f2069b4de. The downloaded Actions source archive digest was verified before extraction. This checkout is a local inspection snapshot with the identical tree, not a fabricated remote Git history.

## Evidence and root cause

The uploaded rerun reports 287 passed / 3 failed. The first failure is in Fixture::new at AppState::new, before the concurrent operation. Another failure occurs while adding a fixture profile. The previous original Linux run also reports missing confidential-client metadata. Current code explains both: data::migrate::app_root uses one process-global OnceLock temporary directory; all test AppState values therefore read and write the same file. DataStore correctly rejects divergent snapshots (including whole-profile arrays). Runtime SecretStore also reads that file. Merely creating independent AppState mutexes does not isolate it. Separately, seed_workspace_secrets deliberately does not create the optional MCP client_secret, but this fixture expected one.

These facts do not establish the cause of the user's deployed public 404. Network discovery and real ChatGPT authentication are different layers.

## Countermeasure and scope

Six lifecycle cases now each run one exact Rust test in a fresh child process; the parent's tests still run in parallel, and the concurrent-secret case retains tokio::join and both live-listener/stale-secret assertions. The child executes the real AppState, encrypted configuration and listener code. No production env override, alternative credential provider or retry-on-conflict is added. A bounded child log, 90-second deadline, wait/kill cleanup and explicit one-test success check prevent silent zero-test success. The fixture explicitly stores its confidential-client secret; public PKCE behavior remains tested after clearing it.

The synchronous RuntimeSupervisor deletion helper is now compiled only for tests, since production uses awaited stop. Added no-I/O adapter and nonempty legacy-import entry tests remove test-target dead code warnings without accessing the user's credential service or legacy files. Existing native credential integration gates remain mandatory and are not replaced by these compile-contract checks.

## Impact and validation

GitNexus 1.6.9 indexed 6008 nodes / 14415 edges. Fixture::new has seven upstream callers, MEDIUM risk. Other modified existing test entry points have no upstream callers. Runtime drop_workspace was resolved by file path and has no production callers. Full-text search is unavailable because the FTS extension cannot be downloaded; exact symbol impact queries succeeded. Production merge conflicts, process lock, OAuth validation and package versions are unchanged.

The regression workflow retains all-target check, complete Rust suite and production-library -D warnings; it additionally runs the lifecycle group three times with eight test threads. No continue-on-error or ignored tests.

Self-review: prior iteration 3 rejected due to actual failures (78/100 for delivery readiness). Iteration 4 pre-CI candidate 94/100, not accepted until Windows and Linux pass. Remaining UI save flow, diagnostic checks, actual installation matrix and release gates are still open.

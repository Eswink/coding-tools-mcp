# Supervisor readiness fixture design

## 概述

对应需求：FR-1, FR-2, FR-3, FR-4

The original local_headers test can exhaust its0.5s budget before a slow child reaches the socket. Its expected timeout/reaping then succeeds while the required observed phase is absent. Original hosted scheduling was not recorded; controlled launcher-return and genuine child-bootstrap delays reproduce this mechanism.

## 技术方案

### Phase evidence and clock
An optional test-only progress list records the successful mode-specific partial response and each successful drip write. Omitted instrumentation preserves existing trickle callers.
The test uses the downloader's existing injected clock/activity seam. Before phase entry the logical clock remains zero, bounded by a0.9s real readiness watchdog; afterward it advances with actual elapsed phase time.
The caller passes an explicit0.5 deadline, so expiry before the first clock sample cannot create a later deadline. Readiness expiry is sticky, phase sampling precedes current-time sampling, and late evidence cannot revive the clock or pass readiness assertions.
The complete phase lasts at least0.5s with sustained successful writes. The original real1.5s invocation assertion and process-reaping/error/confidentiality checks remain.
No fake transport, parser, success record, timeout increase or runtime change is introduced. Separate original startup tests continue measuring startup-inclusive real time.

### Exact source closure
The supervisor fixture is the sole behavioral edit. CompositionTests wraps only its existing raw-supervisor read in integration_bytes, preserving the historicale45608f7 blob assertion.
The newest staged-byte profile receives only2 normalization and4 dispatch lines. Its cases receive one import and13 exact source-operand wrappers; all old assertions and method IDs restore byte-for-byte.
A finite new profile admits actual F69e74973 and only D[F], ordered I[F,D], and J[R,I] with the four pinned release documents.
Five replacement inverses restore complete F bytes. Sixteen older identities are exactly the nine composition and seven workflow rows already pinned by the predecessor profiles.
Every nonself scoped file is pinned; independent full-tree review binds the profile itself. All1785 out-of-scope F entries remain identical.
A new12-case module verifies topology, immutable F, paths/modes/pins/caps, inverses, historical rows, terminal errors, candidate freshness, inventory, readiness semantics and workflow receipts.
The existing publication workflow adds only the new finite group and profile selection, preserving contents:read, fixed actions, source-before/after checks and no live credentials.

### Review and validation
Mandatory impacts: latest normalize CRITICAL12 direct/39 affected/10 flows; failure MEDIUM6/6/0; trickle LOW2/4/0 plus its two DownloadBudgetCases callers. Dynamic threading/subprocess/unittest edges and unavailable FTS are explicit limits.
Retain original failed run37732014756 and the superseded immediate-prefix prototype. Neither overlapping contracts success nor a diagnostic pass replaces that failed gate.
Verify delayed launcher return, genuinely late child READY, sustained physical drip, missing readiness and pre-bound timestamp published after expiry, with real reaping and source/index stability.
Run focused affected suites and finite guards, exact candidate D/I/J coverage and fresh hosted gates before integration. Native/global bundle acceptance and publication remain blocked.

## 文件结构
Behavior changes only in rc_consumer_transport_supervisor_tests.py; exact ten-path source/admission/spec structure is listed in tasks.md.

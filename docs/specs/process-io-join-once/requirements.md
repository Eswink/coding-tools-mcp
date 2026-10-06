# Requirements: consume process I/O task results once (#103)

## 功能概述

Bounded reuse of PR104 e853c8b6e39e9f50d7e66aace96e690425f9a688 on current M 9c5c031d24aadc5d704160bb5a5a65bff126c10c, tree dafa6aa8dce10cf396971329244aeb8ac36d4ed3. Original process.rs Git blob:47bf41f30f67724a873953313f2f31bcdff439a9. A partial I/O join followed by timeout can poll an already-consumed Tokio JoinHandle again. Source/API-contract analysis identifies this bug; actual unchanged-production baseline reproduction and candidate native validation remain pending until their recorded CI runs.

Related work: #101/#55. This repair supplies no Windows tree-completion proof, sandbox capability or execution authority. The Windows feature stays independently incomplete.

## 需求列表

### FR-1: Consume each task result once
**优先级:** Must
**用户故事:** As a process caller I need timeout cleanup to finish without polling consumed task results twice.
### 验收标准（EARS）
1. WHEN join_io consumes any task result, including panic/cancellation errors, THEN it SHALL remove that handle immediately before awaiting another task.
2. WHEN the existing two-second I/O deadline expires THEN cleanup SHALL abort all unconsumed handles and await only those unconsumed handles.
3. WHEN all tasks settle before the deadline THEN each original Boolean I/O result SHALL retain its existing mapping, including false for JoinError.

### FR-2: Preserve the existing contract
**优先级:** Must
**用户故事:** As an existing runtime caller I need the narrow repair to preserve outcome and platform behavior.
### 验收标准（EARS）
1. WHEN I/O join times out THEN the returned IoCompletion SHALL keep the original stdout=false, stderr=false, stdin=false result.
2. WHEN extracting supervisor and unit tests THEN all original bodies and token inventories SHALL remain identical except the declared join_io ownership repair and minimal module visibility/imports.
3. WHEN using Unix, default Windows, PTY or any process-tree API THEN existing behavior and tests SHALL remain unchanged.
4. The change SHALL NOT add a joined-proof field, Windows completion API, dependency, manifest edit or platform authority.

### FR-3: Reproduce the exact baseline honestly
**优先级:** Must
**用户故事:** As a maintainer I need genuine red-to-green evidence from unchanged production source.
### 验收标准（EARS）
1. WHEN preparing the baseline witness THEN CI SHALL materialize immutable M and verify its exact tree in a separate worktree, verify process.rs blob47bf41f30f67724a873953313f2f31bcdff439a9 and preserve its exact production bytes before appending only a named cfg(test) module declaration.
2. WHEN copying regression tests THEN baseline and candidate SHALL use byte-identical process_io_join_tests.rs files.
3. WHEN accepting the witness THEN build SHALL succeed, exactly four tests SHALL execute, the three named partial-join tests SHALL fail specifically with repeated-poll panic, and the all-pending control SHALL pass. Compilation/setup failure or arbitrary nonzero exit SHALL NOT count as reproduction.
4. CI SHALL retain production-prefix, test and overlay hashes, source/tree/toolchain, command, exit code, inventory and raw output.

### FR-4: Exact candidate verification
**优先级:** Must
**用户故事:** As a maintainer I need full cross-platform evidence before calling this repair verified.
### 验收标准（EARS）
1. BEFORE engineering completion THEN actual Windows2025 and Ubuntu24.04 SHALL pass fmt, locked all-target Clippy with -D warnings, full locked tests and check.
2. Test inventory and result counts SHALL be positive and equal, with all four new tests present and zero failed, ignored or filtered tests in the full run.
3. Existing process, PTY and group tests SHALL remain enabled and unchanged.
4. BEFORE publication THEN independent exact-diff review, staged graph and commit gates SHALL pass, and root SHALL approve publication separately.

### FR-5: Preserve finite source admission
**优先级:** Must
**用户故事:** As a maintainer I need the repair to remain admissible without weakening historical source or test boundaries.
### 验收标准（EARS）
1. WHEN selecting the new source D THEN its sole parent SHALL be exact M; a feature merge I SHALL have ordered parents [M,D] and the full D tree; the release-context shape J SHALL have [R,I] and only the four existing exact R document replacements.
2. WHEN a shape selects THEN all seventeen bounded paths and all unchanged entries SHALL be validated; content failures SHALL be terminal without fallback. Alternate anchors, descendants, correction chains and partial repairs SHALL reject.
3. Historical profiles, pins, budgets, ownership tests, both pretag workflows, the ten held paths and all 283+452 original test IDs SHALL remain preserved. The twenty new guard IDs SHALL produce strict303 and contracts755, with zero skips.
4. WHEN extracting publication adapters THEN complete inverse reconstruction SHALL recover exact M bytes and retain all historical method IDs and assertions.
5. BEFORE accepting native evidence THEN an independent source-bound audit SHALL verify full inventory uniqueness and identity in addition to the donor parser, which compares listed/executed names but can accept matching duplicate ordinary names.

## 非功能需求

Exactly seventeen changed paths and 1693 tracked entries; changed source files stay at most500lines. No source publication before approval. No sandbox/admission, credentials/security, release, deployment, PR98 or PR102 mutation. Local syntax checks are not Rust compilation or native test evidence.

## 依赖关系

Existing Tokio dependencies and dual-OS local-agent-runtime workflow only. Integration base is feat/rc-final-artifact-consumer-128 at exact M. The held assembly ref/correction and all ten held paths remain excluded. Windows completion work is neither imported nor claimed complete.

# Requirements: opt-in Windows owned-Job completion (#101)

## Current status: FEATURE INCOMPLETE / WINDOWS UNSUPPORTED

Native run37204048253 on086530d demonstrated that Job accounting zero did not establish immediate descendant-handle signaling. The Windows opt-in must therefore fail before execution with InvalidSpec and the fixed message `Windows tree-exit confirmation is unsupported`. Passing this safety guard does not satisfy the stronger completion feature. All existing strict positive assertions remain unchanged and unmet; no expected-failure or skip converts them to PASS.

## 功能概述

### Scope and baseline

Correction base: PR98 `c3fcfb1f2617d56f8f395317a18d93884d551789`, tree `2066e8ae62522e3a9ee579e03d36ebfbdddeafd0`. PR100 `bdeefba` was reconciled and contains identical runtime blobs; its metadata work is not a dependency. Draft integration target is `ci/rc-source-assembly-v2-20261001` from a separate fix branch.

This is a source-level evidence gap, not a reproduced process leak or current cloud escape. Related work: #55/#81. Windows execution admission stays fail-closed; no filesystem/network sandbox, ConPTY completion parity, credential/security change, release, tag or main merge is included.

## 需求列表

FR-2..FR-4 remain the strict, unmet completion acceptance contract; accounting-only prototype checks do not fulfill them. The current safe behavior is the FR-1 unsupported guard.

### FR-1: Explicit compatibility boundary
**优先级:** Must
**用户故事:** As a runtime caller I can explicitly request stronger Windows completion without changing legacy callers.
### 验收标准（EARS）
1. WHEN constructing ExecSpec THEN require_tree_exit SHALL default to false.
2. WHEN with_tree_exit_confirmation is selected on Windows THEN validation SHALL return InvalidSpec with `Windows tree-exit confirmation is unsupported` before capacity acquisition or spawn, until the stronger completion feature is implemented and verified.
3. WHEN using the default, Unix or PTY path THEN existing termination, outcome classification and admission behavior SHALL remain unchanged, except that the shared I/O timeout path SHALL avoid polling an already-consumed JoinHandle again.

### FR-2: Exact ownership observation
**优先级:** Must
**用户故事:** As a caller I need confirmation about the exact Job originally owning this execution.
### 验收标准（EARS）
1. WHEN requesting opted-in termination THEN request_termination SHALL borrow and retain the exact Job even on API error.
2. WHEN observing completion THEN QueryInformationJobObject SHALL receive Some(exact_owned_handle), and only successful ActiveProcesses==0 SHALL count as empty.
3. IF ownership is missing, query fails, or the bounded deadline expires THEN the outcome SHALL be TerminationUncertain, never command_ok.
4. WHEN uncertainty has occurred THEN subsequent zero-member evidence SHALL NOT erase it.

### FR-3: Publication order and bounded stages
**优先级:** Must
**用户故事:** As an outcome consumer I need all required completion facts before publication.
### 验收标准（EARS）
1. BEFORE publishing a confirmed opted-in outcome THEN termination request success, direct-child wait success, normal settlement of all I/O tasks and exact Job emptiness SHALL all be established.
2. IF an I/O task normally settles with an operation error THEN its existing OutputError/StdinError classification SHALL remain; IF a task panics, is aborted or misses its deadline THEN completion SHALL remain uncertain.
3. WHEN cleanup begins THEN child wait, I/O join and Job observation SHALL use existing3s, existing2s and fixed3s stage budgets respectively, with20ms Job polling and no deadline reset or zero accepted after deadline.
4. WHEN Job observation is pending THEN the outcome watch channel SHALL remain unpublished and the supervisor SHALL retain its Job and capacity permit.
5. Timing budgets SHALL be described as cooperative stages, not a hard3s total wall-clock guarantee.

### FR-4: Honest regression evidence
**优先级:** Must
**用户故事:** As a maintainer I need deterministic tests and native evidence without invented race reproduction.
### 验收标准（EARS）
1. WHEN validating retained identity THEN tests SHALL distinguish unchanged legacy consumption from new retaining-method behavior, without claiming an API-switched assertion is unchanged red-to-green.
2. WHEN validating descendants THEN a bounded native Rust self-descendant SHALL use private readiness stdio; parent/readers completion SHALL be observed while the original Job still has an active member.
3. WHEN validating ordering/errors THEN private per-run test-only query injection SHALL exercise the real supervisor/watch path without public hooks or global overrides.
4. BEFORE engineering completion THEN Windows2025/Ubuntu24.04 SHALL run full locked local-agent/PTY tests, fmt, Clippy and check with exact-source metadata and nonzero counts.
5. BEFORE publication THEN independent review, staged graph and commit gates SHALL verify the exact candidate; no existing PR98 cancelled run SHALL be retried.

## 非功能需求

No new dependency or credential exposure. Bounded owned-handle observation, <=500line changed code files, backward compatible opt-out and unchanged sandbox admission. Preserve evidence of native failures and unrun gates.

## 依赖关系

PR98 c3fcfb1 runtime baseline; existing Tokio/windows crates and local-agent-runtime dual-OS CI. No PR100 metadata dependency. Native Windows execution is required to claim Windows validation; Linux-only tests do not establish it.

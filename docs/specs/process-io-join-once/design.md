# Design: take each joined process I/O handle once (#103)

## 概述

FR-1..FR-4 are a narrow correction to the c3 baseline. Sequential await consumes a JoinHandle result; the original timeout branch retains and awaits that handle a second time if a later task is pending. The cause is ownership bookkeeping, independent of native process/Job completion.

## 技术方案

Wrap stdout, stderr and stdin JoinHandles in Options. A private helper awaits a borrowed present handle, removes it immediately after receiving Result, then maps JoinError to false as before. The readers future preserves stdout/stderr/stdin order. On unchanged READER_WAIT expiry, first abort every remaining Option, then await only remaining handles. Return the original default IoCompletion with exactly three false Boolean fields. No join-proof field or outcome-classification change is introduced.

Move the original ProcessManager::start and read_bounded/IoCompletion/join_io/take_stream/confirm_group_exit definitions mechanically to process_supervisor.rs. Keep the public types in process.rs; only helper visibility and test imports support existing tests. Move the original inline unit tests, including their nested ErrorAfterData implementation, to process_tests.rs without changing tokens or assertions. Preserve all existing process/PTY/group tests and process-tree implementations byte-for-byte. Verify extraction against c3; review join_io separately. All changed source files remain at most500lines.

## 测试与基线证据

One process_io_join_tests.rs contains exactly four tests: stdout ready with stderr pending; both readers ready with stdin pending; panicked stdout and cancelled stderr consumed before pending stdin; all-pending timeout control. Each asserts the same original all-false timeout result. Tests run under a named io_join_tests module, directly below process in the baseline and below supervisor in the candidate. Filtering uses the shared module name; no duplicate or rewritten baseline bodies.

CI uses a separate runner-temp worktree at immutable c3 with line-ending conversion disabled. It checks the canonical production Git blob, reads and hashes the exact production prefix, appends only the cfg(test) module declaration, copies the same test bytes and verifies the exact overlay. Build the baseline library tests successfully before running the four tests with one test thread. The gate requires the three exact named FAILED results, repeated-poll panic in each named failure block, one control ok and the exact1passed/3failed/0ignored summary. Raw failure logs are reproduced baseline failures, not passed production tests.

Then the candidate checkout runs fmt, locked all-target Clippy -Dwarnings, full test inventory, full locked --no-fail-fast tests, and locked all-target check. Parse exact positive test inventory/result counts and reject failures, ignores, filters or missing new tests. Preserve source/tree/toolchain and raw logs for both Windows2025 and Ubuntu24.04. Never substitute tree-sitter syntax or baseline instrumentation for actual candidate validation.

## 风险与边界

Fresh exact graph sees join_io -> ProcessManager::start -> run/process_runtime tests, but Rust reexports can hide broader callers. Independent HIGH/manual review covers supervisor publication, capacity/cancellation and NativeToolHost consumers. Only join ownership changes semantically. No Windows completion APIs, Job methods, process launch, sandbox/authority, PTY, dependency or original timeout-budget change. The external Windows feature remains blocked separately.

## 文件结构

Exactly process.rs, process_supervisor.rs, process_tests.rs, process_io_join_tests.rs, local-agent-runtime.yml and docs/specs/process-io-join-once/{requirements,design,tasks}.md. Tool metadata/evidence remains outside the committed source paths. Publication needs separate root approval after exact review.

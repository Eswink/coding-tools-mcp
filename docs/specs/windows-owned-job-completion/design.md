# Design: retained Job proof for opted-in non-PTY execution

## 概述

Implements FR-1..FR-4 for issue #101. This is lifecycle containment, not execution authority. Baseline/integration dependency is PR98 c3fcfb1; PR100 reconciliation does not import its metadata layer.

## 技术方案

ExecSpec exposes its existing strengthening on Windows and keeps false as default. The original ProcessTree::terminate and Drop remain unchanged, as do all PTY production files. New request_termination(&self) borrows the original Job, rejects absent ownership, and retains the handle on success/error. New is_empty(&self) queries only that handle using basic Job accounting.

The supervisor chooses retaining termination only for opted-in Windows calls. It independently waits for the direct child and joins bounded I/O. IoCompletion records normal task joins separately from each task's successful I/O result: normally joined read/write errors retain existing classifications; panic, abort and join timeout produce uncertainty. Existing legacy/Unix decisions ignore the additional join evidence. Independent review found an inherited partial-join timeout hazard: after stdout completes, waiting stderr/stdin can time out, and the old cleanup would await stdout again. Per-handle Option ownership removes each consumed handle immediately; timeout aborts and joins only remaining handles. This narrow shared-path correction prevents a supervisor panic and preserves existing error classification. It is source/API-contract analysis pending native tests, not a reproduced production incident.

After assembling an outcome, the Windows opt-in branch awaits a private publication helper. That helper uses one3s monotonic deadline, queries the owned Job, rejects missing/error/late observations, polls every20ms and never clears an earlier TerminationUncertain. Child wait3s plus I/O2s plus Job3s are independent cooperative stages; synchronous native calls and underlying blocking I/O are not a hard wall-clock guarantee. Aborted outer I/O tasks do not prove their Windows blocking operations completed, so later Job zero cannot repair incomplete joins.

The publication helper owns the sender until the proof resolves. The enclosing supervisor retains the Job and permit through the helper and its single send_replace. Test-only per-run query injection is private to the crate's Windows unit tests; there is no public injection setting or process-global mutable test hook.

## 文件结构与机械提取

- process.rs: public runtime types and opt-in configuration, <=500lines
- process_supervisor.rs: moved ProcessManager::start plus existing I/O/group helpers; narrow declared completion changes only, <=500lines
- process_tests.rs: unchanged existing unit test bodies moved out of824line process.rs
- process_tree_windows.rs: two new borrowing methods; original terminate/Drop/startup unchanged
- process_completion.rs and process_completion_tests.rs: private bounded publication logic and deterministic tests
- src/bin/process_fixture.rs and tests/windows_job_completion.rs: bounded private-pipe self-descendant and native Job tests
- local-agent-runtime.yml: exact fix-branch push trigger, pre-test provenance, focused Windows logs plus retained full dual-OS suite
- these three specification files

Maximum12paths; no external dependency, Cargo manifest/lockfile or desktop/runtime admission edit. Mechanical extraction is verified against original function bodies; intentional I/O join/completion changes are reviewed separately.

## 风险与验证

Fresh GitNexus exact-symbol impacts report low counts but miss platform reexports and the fixture main; manual HIGH review covers ProcessManager outcome consumers and shared PTY/startup callers. The chosen separate API avoids shared helper behavior changes. Reference pattern: Tauri tools/进程树Windowsv2.rs and session_windows_job.rs, without copying authority or broader runtime layers.

Native fixture descendant signals readiness on a private parent-child pipe, then sleeps bounded with null stdin. Parent may wait for a bounded release marker so tests retain a process handle before parent exit. Direct harness observes parent exit and captured pipe EOF while original Job accounting remains nonzero, then requests termination, records genuine owned-handle signaling, releases the process reference and observes Job zero. Runtime tests use a bounded observer that stores signal proof with Release before dropping its sole handle; the caller samples once with Acquire immediately at outcome return. Stop/error/deadline cleanup cannot create proof, and a known-live stop negative-control verifies this. This avoids the test itself pinning ActiveProcesses through an extra process reference. Cleanup/join occurs before assertions; no PID query failure is interpreted as death.

Private supervisor tests hold nonzero observation until a per-run barrier opens and require snapshot None, then zero before outcome. Error->zero is rejected immediately; fixed deadline, prior cleanup uncertainty, missing direct-child evidence and failed I/O joins remain uncertain. Success preserves Exited/TimedOut/Cancelled/OutputLimit/ordinary I/O-error classifications. Default bypasses the observer. Existing delayed PID tests stay unchanged and retain their eventual-cleanup-only interpretation.

Microsoft references: https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject ; https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject ; https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information . Zero means observed active members, not kernel object destruction; retained process references may conservatively delay accounting.

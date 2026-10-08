# 需求文档：windows-broker-launch

## 功能概述
A finite standalone native Windows image-authority experiment, based on `8bdd5f327b4603c5570dc764e2d62fecbe6e02d2` / tree `b75fdae6b9a2cb9589b51d832d7ba638384cb6b8`. It produces evidence about the executable selected by Windows before admitting its user-mode execution. This is not a production broker or isolation backend.

## 历史经验与坑（来自记忆库）
No memory was injected. Existing VM-session evidence at `79ac13ca` remains a separate, untouched result. Path validation, CREATE_SUSPENDED, a matching hash alone, and default debugger child behavior are insufficient authority claims.

## 范围边界
In scope: nine new files, native MSVC/Windows SDK only, harmless self-built marker executables, fresh owned temporary fixtures, and one versioned dedicated-branch push-triggered standard Windows Actions experiment after independent exact-source review.
Out of scope: existing application/Rust/Cargo/Go/dependency edits; downloads or toolchain setup; HCS/VM/import; registry, ACL, machine or network configuration changes; SeDebugPrivilege; attaching unrelated processes; debugger kill-policy relaxation; actual workspace, packaging, release or production admission.

## 需求列表
### FR-1: Bind retained image authority
Priority: Must. As an experiment operator, I need the admitted image to be the retained manifest-checked file.
1. WHEN preparing a case THEN retain a noninheritable GENERIC_READ image handle with FILE_SHARE_READ only, verify its SHA-256 against the build manifest, and obtain FileIdInfo volume serial plus all 128 file-ID bits.
2. WHEN the actual CREATE_PROCESS_DEBUG_EVENT arrives THEN require its nonnull hFile, query the same full identity and hash from that handle, and compare both with the retained handle before any admission ContinueDebugEvent.
3. IF either observation is missing, different, invalid, or unqueryable THEN reject; a path string, partial file ID, synthetic handle, or matching bytes alone SHALL NOT substitute.

### FR-2: Hold the real process before admission
Priority: Must. As an operator, I need an observable pre-user-mode decision.
1. WHEN launching THEN use CreateProcessW with DEBUG_ONLY_THIS_PROCESS, explicit absolute lpApplicationName, fixed quoted argv, trusted absolute cwd, explicit environment, and STARTUPINFOEX HANDLE_LIST limited to owned stdin/stdout/stderr; do not add CREATE_SUSPENDED.
2. WHEN processing the first create event THEN assert expected PID/event order and absence of marker file and stdout/stderr bytes; record actual OS hFile presence separately from fault injection.
3. IF validation succeeds THEN record admission before continuing that event; require the expected marker and clean exit afterward. No command interpreter or arbitrary command input is accepted.

### FR-3: Preserve lifetime until actual completion
Priority: Must. As an operator, I need rejection and cancellation to leave no admitted or unobserved child.
1. IF rejection, timeout, cancellation, query failure, wait error, unexpected event, or exception failure occurs THEN terminate only the self-created process, retain authority and fixture ownership, and drain pending debug events on its creating thread.
2. WHEN draining a rejected pending event THEN ContinueDebugEvent is allowed only after successful TerminateProcess or already-confirmed process termination; this is termination drainage, never admission.
3. WHEN EXIT_PROCESS_DEBUG_EVENT has been continued AND the independently owned process handle is signaled AND both bounded pipe readers reached EOF and joined THEN cleanup may retire the fixture. Unknown exit, failed termination/continuation, missing EOF or failed join remains failure and preserves the fixture.

### FR-4: Handle Windows debug ownership and exceptions
Priority: Must. As an operator, I need a bounded, correct debug pump through process exit.
1. WHEN processing debug events THEN close each owned create-image/DLL hFile exactly once; never manually close OS-managed debug event process/thread handles. Close separately owned PROCESS_INFORMATION/duplicated handles explicitly.
2. WHEN the initial first-chance loader breakpoint arrives THEN handle exactly that expected breakpoint; pass other first-chance exceptions as DBG_EXCEPTION_NOT_HANDLED and fail unexpected second-chance exceptions while draining termination.
3. WHEN time is bounded THEN use 50 ms debug waits, 5 s admission and 10 s execution/drain deadlines, at most 256 events and 64 KiB per output pipe. No INFINITE waits, APCs, detach, or DebugSetProcessKillOnExit(false). Every wait/continue error stays sticky even if a later cleanup retry succeeds.

### FR-5: Exercise native success, substitution, mutation and faults
Priority: Must. As an operator, I need falsifiable observations from actual self-created processes.
1. WHEN running the matrix THEN cover correct image; different bytes/file ID; byte-identical distinct file ID; blocked owned ancestor rename and actual junction redirection; denied ordinary image write/delete/rename while pinned; bad manifest; injected null/file-ID-query/hash-query/wait/continue failure; pre-admission timeout/cancel; post-admission timeout/cancel.
2. WHEN mutation is attempted THEN operate only inside the dedicated owned fixture; record the real result. A blocked redirect is not evidence that a redirected image was compared, and unsupported fixture setup is not PASS.
3. WHEN injecting faults THEN keep the real OS event and actual child lifecycle; separately label the substituted decision or failure. Null/query seams do not establish that Windows natively delivered null or failed its query.

### FR-6: Keep DLL and descendant authority separate
Priority: Must. As an operator, I need the experiment's claims to match its trust boundary.
1. WHEN building and launching THEN use a dedicated trusted code parent, static MSVC CRT for the harness, a no-CRT Kernel32-only marker stub, SystemRoot/System32-only child PATH, and record binary imports plus source/build hashes.
2. WHEN interpreting results THEN explicitly trust the CI host account, OS loader, system DLLs, build tools and fresh code parents. Main-image identity does not authorize all DLLs, metadata or reparse transitions; FILE_SHARE_READ does not block all attribute/metadata changes.
3. WHEN reporting DEBUG_ONLY_THIS_PROCESS THEN state it is not descendant containment. Stubs create no descendants; production tree/VM ownership remains outside this experiment.

### FR-7: Preserve auditable finite evidence
Priority: Must. As an operator, I need source-bound results and honest failure states.
1. WHEN running Actions THEN require an exact source SHA/tree, read-only contents permissions, Windows 2025 standard runner, preinstalled MSVC/SDK, push only on `ci/windows-broker-launch-followup-20261008`, no PR trigger, bounded job, and no privileged setup; require the run commit to have sole parent equal to the baseline. Publish no release, package or production integration.
2. WHEN reporting THEN emit per-case expected/observed verdict, Win32 errors, actual file identities/hashes, admission/termination/exit/EOF/join/cleanup facts, fault labels, case count and all-pass only if every required case passed. Validate an exact artifact allowlist, per-file and aggregate byte caps, and source/sole-parent/tree binding before uploading source/build/import/result evidence, including bounded failure evidence.

## 非功能需求
NFR-1: Exactly nine added paths, at most 1380 added lines overall and fewer than 500 lines per file; no edited baseline files. Individual budgets are locked in tasks.md.
NFR-2: No unsupported or unknown observation becomes success; Linux static/spec checks do not claim Windows runtime evidence.

## 依赖关系
Only already installed Windows SDK/MSVC and standard GitHub checkout/upload-artifact actions; SHA-256 uses Windows BCrypt. Initial packet approval and final independent source review are separate gates before implementation and publication respectively.

## V2 明确验收契约
V1 source `d271aa471d502c30286664f52d1f4dba16f13c7b` failed: 13 executed, 11 passed, 18 required, five not run. Its source/artifacts are preserved; this revision cannot relabel that result.
The v2 summary SHALL declare contract_version=2. Its18-case census replaces only native_ancestor_redirect with native_ancestor_rename_blocked; all other17 IDs and actual junction redirection proof remain mandatory.
WHEN testing the ancestor case THEN require the first rename denied with error5/32, no second move and unchanged-A admission/marker/output/exit/EOF/join proof; unexpected rename success fails and skips launch.
ONLY an already-rejected fault_debug_wait with Reason::Wait, applied fault, successful termination request and no admission/continuation may defer raw Peek109; each independently recorded pipe error must be0/109, at least one109, available counts zero, reader seen flags false and marker absent. Every other Peek error or admission-path failure remains sticky.
Deferred Peek109 SHALL NOT turn no_marker_before true or permit admission. Separate no_pipe_output_after_retirement requires actual EXIT+continuation, independent process signal, joined EOF readers, both captured strings empty and no unrelated cleanup error; missing proof retains failure and ownership.
WHEN that terminal pipe proof holds THEN actually check the marker file after retirement, record marker_checked and require absence before passing the wait case or retiring its retained image handle. Default false is not an observation.
The seven changed paths are header/owner/cases/workflow/three specs; fixture.cpp and prepare.ps1 SHALL remain byte-identical to verified v1. The new branch is created only at the final independently reviewed candidate, with sole parent8bdd.

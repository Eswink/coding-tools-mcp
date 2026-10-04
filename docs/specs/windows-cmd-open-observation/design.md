# 设计文档：windows-cmd-open-observation

## 概述

对应需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, NFR-1, NFR-2, NFR-3, NFR-4. Scoped implementation was approved after independent review; publication and native execution remain separately gated. This is the normative implementation contract. Baseline is PR99 4d8fc29595cf4e832deb0e336bb9932f162673f2, not recovered PR100. Runtime feasibility is unproven: existing attach or memory-write access may fail, and that ends this route without an access workaround.

## Decision and stopping point

Instrument only the already-created, suspended `cmd-relative-batch-exit23` subject, after the existing surrogate authority predicate and job assignment. Preserve the previous ten cases, original launch flags/command/payload, job, AppContainer/profile/zero capabilities, surrogate verification, local-execution gate, and original process/thread handles. This remains `accesscheck_signature_v1_ci`, not adopted full LPAC token verification.

Observe at most the first exactly path-bound NtCreateFile or NtOpenFile entry and its same-thread return. Permanently remove both entry traps once a match is found; use one one-shot return trap. There is no NtReadFile observation, asynchronous I/O completion tracking, whole call trace, next-stage expansion, or claimed root cause. A failed return identifies that operation and status. A successful, object-identity-matched return means that operation opened the prepared object; it does not establish reading or execution. No matched call is inconclusive, never evidence that no open occurred.

One reviewed Windows attempt is the experiment. An access denial, unsupported ABI/stub/path, budget failure, debugger perturbation, or ambiguous event ends observation. Do not try a new cmd spelling or a stronger facility as an automatic continuation. If useful paired evidence appears, return to the original bug diagnosis rather than enlarge the observer.

## Fixed boundaries and bounds

- Native AMD64 only: broker pointer size 8; target IsWow64Process2 processMachine=0 and nativeMachine=0x8664; target PE machine=0x8664 and PE32+ magic=0x20b. Reject WOW64, ARM64 and emulation.
- Same synchronous native thread creates the original child, attaches, waits and continues all debug events. No Task, worker thread, APC, remote thread, injected DLL or debug-spawn replacement.
- One DebugActiveProcess call, using the exact original PID while its original process handle stays live. No OpenProcess/OpenThread, privilege enabling, elevation, DACL or mitigation changes, DebugSetProcessKillOnExit change, drivers, ETW, Procmon, settings, downloads, symbol server, or policy alteration.
- No live detach path. DebugActiveProcessStop is absent from the allowlist. After successful attach, old cleanup is callable only after EXIT_PROCESS_DEBUG_EVENT was successfully continued and the retained original process handle is signaled.
- Operational deadline: monotonic 30,000 ms beginning immediately before debug preflight/attach; never reset on events. Cleanup has one 5,000 ms allowance beginning at abort or receipt of EXIT, with hard total ceiling 35,000 ms from operational start. Poll waits use min(remaining,100 ms). These bound the loop, not an OS call stalled inside the kernel; the existing Actions outer timeout remains the ultimate host limit.
- At most 4,096 operational events, 512 cleanup events, 32 live debug threads, 128 loaded modules, 128 entry hits, 1 matched operation, 1 pending step owner, 1 pending return owner, 3 patch-ledger addresses, and 264 one-byte write attempts. Budget exhaustion is incomplete/fatal.
- Remote reads total at most 1 MiB, including PE headers, export tables, argument names, contexts' pointed-to stack data, readbacks, and the returned handle. One name at most 8,192 bytes; one export block at most 512 KiB; at most 8,192 exported names/functions. No buffer/content/remote debug-string/exception-parameter read. The fixed debug-event structure and register context are not dumped.
- At most 16 KiB additional serialized receipt material. No dynamic key names, arrays of operations, raw addresses/handles, names/paths, exception text, instruction bytes or target contents in the new receipt. Existing case evidence is unchanged.

## Native API allowlist and handle boundary

Exactly these native APIs may be called by the new observer (reuse existing declarations when their exact ABI matches):

| API | Fixed use and handle |
| --- | --- |
| GetProcessId(HANDLE)->DWORD | Original process handle only; equality to creation PID |
| GetProcessTimes(HANDLE,FILETIME* x4)->BOOL | Original process handle only; bind creation FILETIME before attach and at terminal confirmation |
| IsWow64Process2(HANDLE,USHORT*,USHORT*)->BOOL | Original process handle only; native AMD64 gate |
| GetSystemDirectoryW(WCHAR*,UINT)->UINT | One broker buffer, 2,048 WCHAR capacity; derive expected system ntdll path in memory only |
| DebugActiveProcess(DWORD)->BOOL | Exactly once, original PID |
| WaitForDebugEvent(DEBUG_EVENT*,DWORD)->BOOL | Same synchronous native thread; bounded timeout; at most one pending event |
| ContinueDebugEvent(DWORD,DWORD,DWORD)->BOOL | Exact pending event's PID/TID, once; DBG_CONTINUE=0x00010002 or DBG_EXCEPTION_NOT_HANDLED=0x80010001 only |
| ReadProcessMemory(HANDLE,void*,byte*,SIZE_T,SIZE_T*)->BOOL | Original process handle; exact reads and aggregate budget; no retry on denied/failed reads |
| WriteProcessMemory(HANDLE,void*,byte*,SIZE_T,SIZE_T*)->BOOL | Original process handle; size exactly 1; only ledger addresses; no VirtualProtectEx or write fallback |
| FlushInstructionCache(HANDLE,void*,SIZE_T)->BOOL | Original process handle; same exact one-byte patch address |
| GetThreadContext(HANDLE,CONTEXT*)->BOOL | Borrowed debug-event thread handle, only while its debug event globally stops the target |
| SetThreadContext(HANDLE,CONTEXT*)->BOOL | Same; only owned breakpoint RIP correction and owned TF change, with all other requested registers preserved |
| SuspendThread(HANDLE)->DWORD | Borrowed, known-live peer debug-thread handles only, once per peer during one step-over |
| ResumeThread(HANDLE)->DWORD | Original main handle once to remove the original CREATE_SUSPENDED count; otherwise only exact owned peer-suspend increments |
| GetFinalPathNameByHandleW(HANDLE,WCHAR*,DWORD,DWORD)->DWORD | Supplied CREATE/LOAD image-file handle only; fixed 2,048 WCHAR broker buffer, flags 0; compare in memory only |
| DuplicateHandle(HANDLE,HANDLE,HANDLE,HANDLE*,DWORD,BOOL,DWORD)->BOOL | Original process -> GetCurrentProcess(), exactly one successful-open file handle, desiredAccess=0, inherit=false, options=2 (SAME_ACCESS) |
| GetCurrentProcess()->HANDLE | Broker pseudo handle only as DuplicateHandle destination; never close |
| GetFileInformationByHandle(HANDLE,BY_HANDLE_FILE_INFORMATION*)->BOOL | Broker-owned duplicate only; compare volume/file index and regular-file attributes with already-captured source identity |
| CloseHandle(HANDLE)->BOOL | Only positively owned CREATE/LOAD image-file handles and broker-owned duplicate; single attempt; never original process/thread/job, borrowed debug process/thread, or raw target file handle |
| WaitForSingleObject(HANDLE,DWORD)->DWORD | Original process handle only; bounded terminal confirmation |
| GetExitCodeProcess(HANDLE,DWORD*)->BOOL | Original process handle only, after signal |
| TerminateProcess(HANDLE,UINT)->BOOL | Original process handle only, one abort attempt with existing cleanup code 91; never an arbitrary PID |

BOOL is a 4-byte Win32 BOOL, DWORD/ULONG uint32, USHORT uint16, SIZE_T/handles/pointers uint64 in this AMD64-only observer. P/Invoke uses exact entry points, Winapi convention, appropriate Unicode W forms and SetLastError only for APIs documented to supply it. A failed native call records its immediate numeric error through the fixed API tag; no Win32Exception/Exception.Message, stack, InnerException or raw native message is retained.

Forbidden: NtReadFile, direct Nt/Zw invocation, NtClose, DUPLICATE_CLOSE_SOURCE (1), DebugActiveProcessStop, DebugBreakProcess, DebugSetProcessKillOnExit, VirtualProtect/VirtualProtectEx, hardware/debug-register modification, toolhelp/process/thread enumeration, generic handle forwarding, and any other native import. NtCreateFile/NtOpenFile/DbgBreakPoint names are resolved as observation addresses, never invoked.

Handle classes are distinct in code, not just comments: original coordinator-owned handles; OS-owned borrowed debug process/thread handles; close-once broker image-file handles; close-once broker duplicate. Numeric equality between namespaces is not identity: a raw target file handle is never compared with a broker handle to decide ownership and is never passed to broker CloseHandle. Within the broker handle table, an output aliasing any live protected original/borrowed/owned handle is rejected, not adopted or closed. Failure outputs are never adopted. A close failure consumes the close authority without retry, retains the unresolved attempted state, marks ownership uncertain and forbids acceptance; it does not authorize closing any other value.

## Exact AMD64 layouts and observation ABI

Use explicit-layout byte parsing, checked arithmetic and actual aligned buffers; never Marshal.PtrToStructure on a remote address. Assert every size/offset before attach. A 1,232-byte CONTEXT buffer must be 16-byte aligned (allocate extra broker memory and keep its original allocation pointer separately). ContextFlags=0x00100003 (CONTROL|INTEGER); no debug-register or XSTATE flags. Relevant offsets: ContextFlags 48, EFlags 68, Rax 120, Rcx 128, Rdx 136, Rsp 152, R8 184, R9 192, R10 200, Rip 248. TF=0x100. Only RIP and TF may change. A preexisting TF at an owned entry is unsupported. Context setting and verification must preserve all other CONTROL/INTEGER fields from the immediately preceding stopped context. The executed three-byte instruction naturally changes R10 to the entry RCX value and RIP to entry+3; step completion must expect those two deltas, not compare against a wholly unchanged preinstruction context. Other integer/control values stay unchanged across this register-to-register MOV apart from the owned TF and architecturally defined debug-event effects. An unexplained delta fails closed; no stale preinstruction context is written back.

DEBUG_EVENT is 176 bytes, eventCode/PID/TID at 0/4/8 and union at 16. Union-relative layouts:
- EXCEPTION: exceptionCode 0, flags 4, record pointer 8, address 16, parameter count 24, parameters 32..151; firstChance 152. Do not read parameter contents.
- CREATE_PROCESS: hFile 0, hProcess 8, hThread 16, imageBase 24, debugOffset 32, debugSize 36, threadLocalBase 40, startAddress 48, imageNamePointer 56, Unicode WORD 64. Do not dereference imageNamePointer.
- CREATE_THREAD: hThread 0, threadLocalBase 8, startAddress 16.
- LOAD_DLL: hFile 0, base 8, debugOffset 16, debugSize 20, imageNamePointer 24, Unicode WORD 32. Do not dereference imageNamePointer.
- EXIT_PROCESS/EXIT_THREAD: exit DWORD 0. UNLOAD_DLL: base pointer 0. RIP: error/type DWORDs 0/4. OUTPUT_DEBUG_STRING: ignore its pointer and data.

At either Nt entry, exception address must equal the owned entry address and CONTEXT.RIP must equal entry+1. Read return address at [RSP]. Require RSP+8 checked/nonwrapping, return address inside a currently loaded PE executable section, not one of the entry addresses and not an existing 0xCC. For this fixed one-shot protocol the matched return is accepted only on the saved event thread ID with its same still-live event handle, RIP=returnAddress+1 and RSP=entryRSP+8. RAX low32 is NTSTATUS; upper bits have no meaning.

NtCreateFile parameters:
- RCX: output PHANDLE; RDX low32: DesiredAccess; R8: OBJECT_ATTRIBUTES*; R9: IO_STATUS_BLOCK* (do not dereference)
- [entryRSP+0x28]: AllocationSize* (do not dereference); +0x30 low32 FileAttributes; +0x38 low32 ShareAccess; +0x40 low32 CreateDisposition; +0x48 low32 CreateOptions; +0x50 EaBuffer* and +0x58 low32 EaLength (do not dereference or record EA)
NtOpenFile parameters:
- same four register parameters; +0x28 low32 ShareAccess; +0x30 low32 OpenOptions; FileAttributes/CreateDisposition are inapplicable

OBJECT_ATTRIBUTES is 48 bytes: Length DWORD@0 must be 48; RootDirectory pointer@8; ObjectName pointer@16; Attributes DWORD@24; SecurityDescriptor@32 and SecurityQualityOfService@40 are never followed. UNICODE_STRING is 16 bytes: Length ushort@0, MaximumLength ushort@2, Buffer pointer@8. Length must be even, >0, <=MaximumLength, <=8,192 and fit checked read bounds. Decode only those Length bytes as strict UTF-16; embedded NUL or invalid encoding is unsupported.

A match requires RootDirectory=0 and the exact absolute native spelling `\\??\\` + already-verified full workspace path + `\\direct.cmd` (the notation denotes one leading backslash, question mark, question mark, backslash). No path resolution, namespace stripping beyond that one exact prefix, relative-root lookup, dot-collapse, reparse following, device alias, or environment expansion. Compare ordinal when OBJ_CASE_INSENSITIVE (0x40) is absent; otherwise ordinal-ignore-case. Unsupported root/name forms increment one finite counter and are skipped with correct entry step-over; they never become a no-open finding. Any failed remote read aborts. All nonmatching path data is discarded in memory immediately and never logged.

Return interpretation:
- STATUS_PENDING=0x00000103: result observed_pending, incomplete/fatal; do not read IO_STATUS_BLOCK, wait for this I/O, duplicate an output, or claim a final operation result.
- Other NTSTATUS with high bit set: matched_open_failed; use the returned status, not IO_STATUS_BLOCK. Do not inspect an undefined output handle. This is one failed operation, not established batch root cause or proven policy identity.
- Other nonnegative status: read exactly 8 output-handle bytes from saved PHANDLE; reject null/pseudo/invalid values. Duplicate once with SAME_ACCESS, compare existing `pilot_cmd_batch_source` volume/index and regular-file attributes through the broker duplicate, then close only that duplicate once. Identity disagreement or failed metadata/close is incomplete/fatal. A matched successful operation is not read/execution evidence.

## Module and export readiness

At CREATE_PROCESS, bind event PID and TID to the original creation PID/TID, verify original process handle PID and creation FILETIME still match, and retain the borrowed event handles without closing them. For every CREATE/LOAD image event, adopt its positively owned ordinary image-file handle before dispatch or thread-identity validation, then close it exactly once after bounded metadata handling or early abort. The pending-event ledger is None/Owned/Attempted/Closed/Unknown; consume the close authority before the API call, retain uncertain attempts, and never continue an event with an unaccounted image handle. NULL hFile is not opened by a pathname; if it prevents ntdll identity, readiness stays unavailable.

Use LOAD_DLL's actual base plus its supplied file handle. Compare its bounded final path in memory to GetSystemDirectoryW + `\\ntdll.dll` (only a documented DOS final-path `\\\\?\\` prefix is removed for this exact comparison); require one such image. Read its remote PE headers/exports, not local GetProcAddress-derived addresses. Validate MZ, e_lfanew, PE signature, AMD64 machine, bounded section count (1..96), PE32+ optional header size/magic, SizeOfImage and all checked RVA/length ranges. The export block is one bounded remote read. Require export module name `ntdll.dll`, exact unique names NtCreateFile, NtOpenFile and DbgBreakPoint, in-range function ordinals, distinct entry RVAs, no forwarded exports, and each entry in an executable section. Require bytes 4c 8b d1 at both Nt entry addresses and byte cc at DbgBreakPoint; unsupported bytes terminate the experiment, with no decoder or alternative breakpoint facility. Never log these bytes/addresses.

Only the first byte of the two Nt entry instructions is replaced with 0xCC. Every patch transition checks its expected current byte, writes exactly one byte once, requires success and bytesWritten=1, flushes that exact address, then reads back one byte to verify. Any denied, partial or uncertain write goes to abort; do not retry or attempt a protection change. Record the intended ledger slot before the call so uncertainty is retained.

Do not wait for the attach breakpoint as a prerequisite to releasing the original CREATE_SUSPENDED count: it may require that thread to run. Readiness means CREATE_PROCESS bound, ntdll proven, both entry patches verified while a debug event is pending, and all preceding attach snapshot events handled. While that pending event globally stops the target, call the existing original ResumeThread exactly once and require previous count 1, then ContinueDebugEvent on that event. If the required ntdll LOAD snapshot never arrives before the deadline, abort without resuming the original thread. Subsequent first-chance EXCEPTION_BREAKPOINT is recognized as the attach breakpoint only once, at the exact resolved unmodified DbgBreakPoint address, with RIP=address+1 and an observed live thread. It does not alter RIP or TF. Any matched file entry before this attach breakpoint is incomplete/fatal; nonmatching entries still use the normal step-over protocol. An unexpected breakpoint is passed unhandled and the observer aborts; it is not silently swallowed.

The assertion that 'all preceding attach snapshot events handled' means every earlier event actually returned by WaitForDebugEvent was continued exactly once, with no second pending event. It does not pretend that the API exposes an end-of-snapshot marker. Entries are installed before original resume; later CREATE_THREAD events are handled before those threads enter user mode.

## Finite event/state transitions

The implementation has these states only: NotAttached, Bootstrap, Watching, StepOne, AwaitReturn, DrainExit, AbortDrain, Exited, RetainedFatal. Attach readiness and attach-breakpoint-seen are separate booleans, never inferred from elapsed time.

| From/event | Required operation/order | Next |
| --- | --- | --- |
| NotAttached, preflight success | Original PID/FILETIME and ABI gates; single attach | Bootstrap on true; no-attach fatal on false |
| Bootstrap CREATE_PROCESS/CREATE_THREAD/LOAD | Bind handles/module; close owned image file; continue exactly once, except hold the ntdll readiness event until patches and original resume are verified | Bootstrap, then Watching |
| Watching known attach breakpoint | Exact DbgBreakPoint and first chance, once; continue handled, no context edit | Watching |
| Watching owned Nt entry, unsupported/nonmatch | Acquire peer suspend ledger; restore this entry byte; set owner RIP back and TF; continue handled | StepOne |
| StepOne owner single-step | Exact owner, code0x80000004, RIP=entry+3, R10=entry RCX, other requested state preserved except owned TF/debug effects; reinsert entry byte; clear owned TF; verify context; release every owned peer increment once; continue handled | Watching |
| StepOne CREATE_THREAD | Add valid new event handle and acquire one owned suspension before continuing this new-thread event; do not release existing peers | StepOne |
| StepOne ordinary LOAD/UNLOAD/output event | Update bounded module/handle metadata; never read output strings; continue once without releasing peers | StepOne |
| StepOne owner exit, foreign breakpoint/single-step, altered RIP/context, missing peer/ledger or ownership failure | Do not pretend the step completed | AbortDrain |
| Watching first exact matched entry after attach breakpoint | Save call/owner/RSP/PHANDLE; permanently restore both entry bytes; arm one return byte; correct entry RIP only (no TF); verify; continue handled | AwaitReturn |
| AwaitReturn exact owner return | Save returned status; synchronous success identity check as above; restore return byte; correct RIP only while preserving the fresh TF; verify; continue handled; tracing is permanently off | DrainExit (or AbortDrain for incomplete) |
| AwaitReturn foreign-thread hit on return address, owner exit before return, same-address ambiguity | No pairing or second observation | AbortDrain |
| Watching/DrainExit ordinary exceptions | Pass first/second chance with NOT_HANDLED; preserve application handling; only owned trap/step and exact one attach breakpoint are handled | Same state; ultimate exit may end it |
| Any normal state EXIT_PROCESS | Capture debug exit, continue it once, then wait original handle and query actual exit/creation identity | Exited only after signal and equality |
| Any state native failure/budget/deadline/protocol error | Mark fixed error before cleanup; no additional tracing or read/patch/context work | AbortDrain |

Peer-suspend ledger: one global step owner, keyed by live TID plus its current event handle/generation (TID reuse never inherits an entry). While all threads are globally stopped by the entry event, SuspendThread every known live peer once. On success store previous count and `incrementOwned=1` before any continuation; on failure abort. The owner is never explicitly suspended by this protocol. Every peer's ResumeThread is performed once only after the original entry byte is rearmed and owner TF cleared. Its return must equal previousCount+1. Never loop until zero or remove any preexisting count. Mark an attempted release consumed even on failure; no retry. A CREATE_THREAD event during StepOne is observed before user-mode execution and must receive an owned increment before continuation. EXIT_THREAD removes a live generation only after its exit event is continued; any unreleased increment or owner exit makes observation fatal rather than touching a recycled handle. In a step, a changed or unexplained context is fatal. Do not restore a stale full context snapshot after execution.

An event arriving with another PID is a protocol failure; it never authorizes inspection or mutation of that process. The session does not claim ownership of or blindly continue that foreign event. Abort/retention applies to the one original target only. No process descendants are attached or traced.

## Cleanup transition table: no unsafe handback

`MayCallOriginalCleanup` is a separate sealed result, not `s.OwnershipCertain`:
1. Attach was never attempted or returned documented false, and no attached/uncertain state exists: original cleanup may run as before; failed attempt is still fatal.
2. Attach returned true: MayCallOriginalCleanup becomes true only after exact target EXIT_PROCESS event ContinueDebugEvent succeeded, original process handle WAIT_OBJECT_0, and terminal process identity/exit queried. No other boolean combination permits handback.
3. An unexpected managed exception during the attach call itself leaves attachment state unknown: no ordinary cleanup handback; retain failure state. Do not infer 'not attached' from an exception.

Abort after a successful attach:
- If EXIT_PROCESS is already pending, continue it once and use terminal confirmation. No termination needed.
- Otherwise call TerminateProcess(original,91) once. If true, stop all instrumentation: no further target memory reads/writes or context/suspend operations. If an exact-target event is pending and Continue has not already been attempted, continue once with its already-determined disposition; then drain only known-target debug events and close their positively owned image-file handles, for the fixed cleanup allowance. Continue EXIT once and wait for the original handle to signal. OS termination ends peer suspensions and patched address space; restoring dead process bytes is unnecessary and prohibited.
- If TerminateProcess fails, Continue failed earlier, an event's continuation outcome is uncertain, identity is uncertain, an unexpected PID arrives, or terminal proof misses the cleanup bound: RetainedFatal. Do not retry that operation, detach, release peers, restore bytes, invoke StopQualificationSubject, drain/close the job, close original handles, free/delete profile/root, classify or resolve journals.
- In RetainedFatal keep the QualificationSubject and debugger session in one rooted broker-owned retained slot until the broker process exits. No finalizer/SafeHandle may dispose the retained original/debug handles. Record finite failure and retained recovery before returning a fatal row. Existing matrix/run failure paths preserve journals/root; selected-parent pin may close as it already does, without deleting the namespace. The broker's unchanged default debuggee-kill-on-exit and existing kill-on-job-close are last-resort OS behavior, never reported as confirmed cleanup. No persistent access or long-running recovery service is created.
- Borrowed process/thread debug handles are never CloseHandle'd. The OS closes them when their exit events are continued. Original launch handles are separate and remain owned by the original helper, which may close them only after the gate above. Image/duplicate close uncertainty forces fatal evidence even if target exit is proven; old cleanup can then safely stop/drain/close original resources, but scoped root/profile deletion and journal acceptance stay blocked.

Natural completion must also leave zero active patches, zero owned peer increments and no pending call for a completed paired result. EXIT with a missing return or active ledger is a safely terminated but incomplete/fatal observation. Do not claim restores merely because the process exited.

## Selected-case integration and perturbation gate

RunPilotCase retains the original authority/predicate/job lines byte-for-byte. Branch only after assignment: unselected cases use the original resume/wait block byte-for-byte; the selected case invokes the observer, which contains the single original resume. The RunPilotCase finally must call original StopQualificationSubject only when the session's explicit MayCallOriginalCleanup is true (or no debug session was applicable). A false/unknown gate records fatal retained recovery and skips that helper entirely. Setting OwnershipCertain=false is not a substitute for this branch.

After safe original cleanup and the existing capture/ReadPilotCmdObservation, but BEFORE ClassifyPilotCase, profile/root deletion, BindPreconditions or Resolve, call the fixed selected-case gate. It requires: observer lifecycle exit confirmed, no observer error, one paired synchronous operation (failed open or identity-matched success), raw observation complete, original exit=1, stdout matches its zero-byte expectation, and stderr empty. Exit23, any other exit, any output, missing raw capture or missing pair sets `debugger_perturbed` or the specific incomplete code, row.Fatal=true, PositivePassed=false, journal.Failed=true, and prevents the existing classifier and all journal resolution. A diagnostic exit23 is never a cmd success. Even when the baseline is preserved, the new receipt is only operation evidence; original gate outcomes remain independent.

Every new observer error is a fixed code. Preserve ALL existing Runner catches byte-for-byte, including selected-case setup, cleanup, capture and persistence catches. Both new observer and pre-classifier gate entry points sanitize any caught exception inside their own boundary; return a fixed error result, or throw only a fixed literal InvalidOperationException with no InnerException. Never pass a caught message, stack or target-derived value outward. The pre-classifier gate is inserted immediately BEFORE the existing ClassifyPilotCase line; a rejected gate sets the fatal/error state and throws a fixed literal so the unchanged surrounding legacy catch bypasses the classifier, deletion and journal resolution. The separate 1,869-byte ClassifyPilotCase-to-receipt-failure pinned span (SHA256 3f1d2f592775061ac70e60d59511229a83a33d1af80fefda752befe271e8bb20) stays entirely byte-identical. No new exception reaches any existing failure.Message with target-derived text; this does not rewrite or newly certify unrelated preexisting legacy error handling.

## Frozen additional receipt keys

Only prefix `cmd_debug_` in the existing Numbers/Identities dictionaries. No new top-level receipt fields and no acceptance boolean. The independent checker rejects any other key with this prefix, mistyped values, unknown enums, duplicate JSON members or extra generated operation records.

Identities (exact six):
- protocol: `own-child-open-v1`
- result: `incomplete|no_match|matched_open_failed|matched_open_succeeded|observed_pending|debugger_perturbed`
- error: `none|abi_unsupported|target_identity|attach_failed|attach_unknown|bootstrap_incomplete|module_identity|pe_invalid|stub_unsupported|native_failed|read_failed|patch_failed|context_failed|suspend_failed|resume_failed|event_protocol|thread_limit|module_limit|event_limit|entry_limit|read_limit|write_limit|deadline|unsupported_match|return_ambiguous|pending_io|object_mismatch|close_uncertain|exit_unconfirmed|selected_case_failed|debugger_perturbed|internal_exception`
- error_api: `none|GetProcessId|GetProcessTimes|IsWow64Process2|GetSystemDirectoryW|DebugActiveProcess|WaitForDebugEvent|ContinueDebugEvent|ReadProcessMemory|WriteProcessMemory|FlushInstructionCache|GetThreadContext|SetThreadContext|SuspendThread|ResumeThread|GetFinalPathNameByHandleW|DuplicateHandle|GetFileInformationByHandle|CloseHandle|WaitForSingleObject|GetExitCodeProcess|TerminateProcess`
- cleanup: `not_attached|exit_confirmed|retained_fatal`
- open_api: `none|NtCreateFile|NtOpenFile`

Numbers (exact 35, all emitted; not applicable=-1 except counters/flags start0):
`pid`, `main_tid`, `creation_filetime`, `attach_attempted`, `attach_succeeded`, `attach_break_seen`, `entries_ready_before_resume`, `event_count`, `cleanup_event_count`, `thread_peak`, `module_peak`, `entry_hits`, `unsupported_names`, `read_bytes`, `write_attempts`, `matched_tid`, `pair_complete`, `desired_access`, `object_attributes`, `share_access`, `file_attributes`, `create_disposition`, `open_options`, `ntstatus_u32`, `object_identity_matched`, `active_patches_at_exit`, `owned_suspends_at_exit`, `exit_event_seen`, `exit_event_continued`, `process_signaled`, `terminal_exit_u32`, `abort_terminate_attempted`, `abort_terminate_error`, `native_error`, `elapsed_ms`.

`creation_filetime` is the nonnegative combined 64-bit creation FILETIME, not an address; PID/TID may be ordinary numeric correlation facts. `ntstatus_u32` and access/options masks are uint32 represented losslessly as long. For NtOpenFile, file_attributes/create_disposition=-1. On failed NTSTATUS object_identity_matched=-1. Flags are0/1; counters are bounded. `pair_complete=1` requires a same-thread matched synchronous return plus successful object identity for nonnegative status; it does not certify overall artifact or root cause. An abort never sets pair_complete anew. `active_patches_at_exit` and `owned_suspends_at_exit` reflect ledger facts at observed exit, never overwritten to zero just because termination occurred. Values are copied through a fixed allowlisted serializer; no ToString of an exception, path or pointer.

## Implementation envelope and finite verification

Reduce the previous 17-path ceiling to 13:
- Existing six: PilotRunner.cs; run-pilot.ps1 (exact Add-Type additions only); pilot-audit.py; cmd-observations-audit.py; existing diagnostic workflow (its existing broker compile Add-Type plus synthetic contract/audit calls); tests/windows-applocker-observation/audit.py (only its two44-file aggregate hashes, after exact inventory review). The optional broker README edit is dropped and README stays byte-identical.
- New four: tests/windows-cmd-debugger-observation/CmdDebugNative.cs (ABI, API wrappers, bounded PE parsing); CmdDebugSession.cs (fixed state/patch/ownership machine and receipt); CmdDebugContractTests.cs (fake native adapter, no actual debug process); audit.py (source allowlist, receipt checker, positive/negative/mutation tests).
- Required three specification files (requirements/design/tasks) under one diagnostic feature spec.
Both Add-Type sites must be updated atomically: run-pilot.ps1 retains its current broker source enumeration and explicitly appends the sibling CmdDebugNative.cs and CmdDebugSession.cs paths; the existing workflow broker compile step retains its current broker enumeration and explicitly appends those two plus CmdDebugContractTests.cs. No sibling wildcard is allowed. The workflow invokes the new pure/fake-native contract test in the existing no-launch compilation step, and the new Python audit through a bounded audit step. Updating only the pilot script or only adding a separate test step would leave the existing broker compile broken and is rejected.

Each code file <=500 readable lines. Do not compress safety logic to hit a count; if this envelope does not fit clearly, stop for review rather than invent a framework or extra route.

Preimplementation: review this design; independently verify SDK ABI assertions and state transitions; create diagnostic-feature Plan linked to the still-blocked root-cause bugfix Plan. Before edits refresh exact impacted symbols and preserve graph caveat: C# partial and PowerShell call edges/process membership are incomplete, so manual HIGH lifecycle risk remains regardless of graph's LOW labels.

Tests before any Windows observation:
1. Explicit sizes/offsets and aligned allocation; x86/WOW64/ARM64 rejection; Nt arg slots; low32 return handling; checked pointer/RVA/length/UTF16 bounds; return RSP+8 binding; pending is never success; no IO_STATUS_BLOCK read.
2. Bootstrap delayed until ntdll LOAD; readiness before original resume; original resume previouscount !=1; attach failure/unknown; first attach trap binding; no duplicate continue/resume; no extra process/case.
3. Nonmatch step with zero/multiple/pre-suspended peers; peer new-thread event; peer exit/TID reuse; foreign trap; original TF; unexpected single-step RIP; partial set/write/flush/readback failure. Every fault proves no unowned decrement or stale context restoration.
4. One matched failed open; one success with duplicate identity match; mismatch; duplicate/metadata/close failure; no target handle close; DUPLICATE_CLOSE_SOURCE mutation rejected; return hit by foreign thread; owner exits before return; return-address0xCC; forwarded/export corruption.
5. Every early/late state error enters one abort attempt; pending EXIT bypasses termination; Continue failure is not retried; fake target signaled without continued EXIT cannot hand back; failed attach exception cannot hand back; unresolved state calls neither original cleanup nor classifier/journal resolver. Borrowed handles auto-close only in fake OS event semantics; no double close.
6. Clean paired baseline exit1/empty streams vs exit23/otherexit/output/missing pair/raw read: perturbation/fatal happens before ClassifyPilotCase and journal binding. A mutation that lets any new observer/gate exception expose failure.Message or InnerException must fail audit; legacy catches remain immutable. Extra secret/path/address receipt field must fail checker.
7. All existing pilot/observation/sentinel/AppLocker/foundation audits and synthetic tests; full repository-required aggregate checks. Exact protected authority/setup/cleanup source spans unchanged, with only narrow reviewed insertion boundaries. One existing protected Runner span must be split into separately immutable old subspans and independently checked exact insertion points, never merely repinned wholesale.
8. Before commit GitNexus detect_changes; independent source/security review; parent decision on one Actions run at the exact reviewed commit. Existing unrelated accepted metadata/source work does not authorize skipping these gates.

## Official sources used for this contract

- Attach access, snapshot events, initial breakpoint and unchanged debugger-exit default: https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-debugactiveprocess
- Global debug stop, event-handle ownership and EXIT continuation before kernel shutdown: https://learn.microsoft.com/en-us/windows/win32/debug/debugging-events
- Same-thread debug wait and debug handle lifetime: https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent
- Peer suspension is required to single-step just one thread: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread
- Suspend count semantics and rights: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-suspendthread
- CONTEXT layout definition: https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-context
- DEBUG_EVENT union definition: https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-debug_event
- AMD64 parameter and return convention: https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170
- NtCreateFile: https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile
- NtOpenFile: https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntopenfile
- STATUS_PENDING and authoritative non-pending returned status: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_io_status_block
- Write requirements and failures (no success presumption on code pages): https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-writeprocessmemory
- SAME_ACCESS vs dangerous CLOSE_SOURCE and shared file object: https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-duplicatehandle
- Asynchronous target-only termination and subsequent wait requirement: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess
- DbgBreakPoint export availability (user NtDll variant): https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-dbgbreakpoint

The exact three-byte stub and DbgBreakPoint-byte checks are explicit supported-build gates, not a Microsoft promise that all Windows builds use those bytes. Unsupported builds end this experiment. This design has not proved the current runner permits attach/patching or that its bootstrap reaches readiness without original resume; those are finite runtime feasibility outcomes, not grounds for an automatic fallback.

## 技术方案

A nested typed native adapter and one fixed session state machine are compiled with the existing partial BrokerDirectLauncher. Pure fake-native tests exercise the same state machine; no generic debugger UI or external configuration is exposed. FR-1 through FR-6 map to the contract sections above.

## 数据模型

The frozen additional receipt keys and typed handle classes above are the complete new data model (FR-4, FR-5).

## API 设计

CmdDebugApi uses only the22 native APIs above; CmdDebugSession receives the existing QualificationSubject and returns a sealed cleanup decision. Its observation and pre-classifier entry points sanitize every new exception. No network or public product API is added (FR-1, FR-2, FR-4).

## 文件结构

The13-path inventory is in the implementation envelope and tasks.md (FR-6).

## 设计决策

Decision1 (FR-2): one first matched operation avoids call-trace growth and shared return refcounts. Decision2 (FR-4): no live detach removes uncertain restoration handback. Decision3 (FR-3): fixed MOV instruction admits precise step semantics without a disassembler.

## 风险评估

Manual HIGH lifecycle risk persists despite low graph node counts. Attach/code-page write/readiness can fail under existing rights; that ends the experiment. Debugging can perturb behavior; changed outputs/exit never pass. First successful open cannot rule out a later failed reopen. Unsupported ABI/bootstrap is an honest terminal result rather than grounds for broader access.

### Reviewed aggregate-pin correction

The AppLocker audit also binds the aggregate bytes of44 broker source files. This boundary was missed in the initial impact assessment and was caught by the regression. Exactly four members differ: PilotRunner.cs, cmd-observations-audit.py, pilot-audit.py and run-pilot.ps1; the other40 remain byte-identical. The two aggregate hash constants are recomputed only from this reviewed inventory. All330 existing test identities, their identity digest and all negative mutation logic remain unchanged. This replaces the optional README path within the13-file envelope; no AppLocker query, event acquisition or interpretation changes.

### First-candidate review corrections

The return trap owns only RIP correction, not TF: preserve the fresh return TF, including TF=1, and test that invariant. A returned CREATE/LOAD image handle is adopted before dispatch and initial-thread checks. Early wrong-TID/aliased-thread aborts close each valid returned image once or retain it explicitly; failed/throwing closes are never retried and retain the pending debugger state rather than hand back to legacy cleanup. These repairs add no native API, receipt key or file.

## v2 reason/mask revision (implementation authorized, execution undecided)

Base: published49edb3d3e65093ae7408cbe3a49e450118119a4f, tree10f01917959c9340a964ffa988cc8aa3ec13f662. Its authenticated run37188532811 ended incomplete at the immediate Set/Get verification before any matched open pair. That evidence remains immutable. This increment does not establish a batch root cause, a legal OS normalization, or a justified guard relaxation. Corresponds to FR-7.

Only CmdDebugSession.SetContext changes observation granularity. It resets context_mismatch_mask=-1 before its existing Set. Set false remains context_failed / SetThreadContext / immediate api.Error. The existing immediate Get is made directly: false is context_get_failed / GetThreadContext / immediate api.Error, including zero. A true Get with null context is context_roundtrip_unavailable / none /0 and mask-1. A true nonnull Get computes RequestedMismatchMask solely from those two managed context buffers, stores it, and uses the unchanged SameRequested predicate as the guard. A failed predicate is context_roundtrip_mismatch / none /0. Managed failures retain internal_exception / none /0. Standalone Context reads and the later MatchesAfterMov comparison do not gain reasons or calls.

RequestedMismatchMask returns long -1 for null; otherwise exactly21bits:0 ContextFlags,1CS,2SS,3EFLAGS,4RAX,5RCX,6RDX,7RBX,8RSP,9RBP,10RSI,11RDI,12R8,13R9,14R10,15R11,16R12,17R13,18R14,19R15,20RIP. Bit0 is set if either flags field is not0x00100003, including equally invalid fields. Bits1/2 compare16-bit selectors; bit3 compares32-bit EFLAGS; bits4..20 compare existing64-bit offsets120..248. Null is not a completed comparison. For every completed comparison, mask0 iff SameRequested returns true. The original SameRequested method is byte-identical. A mismatch still takes the same throw/Record/Abort path before continuation. No changed thread state is accepted because its differing field is identified.

The existing first-failure Record guard stays unchanged. No context round-trip occurs in abort/cleanup; thus cleanup cannot overwrite the first mask. Reset occurs before Set so a later Set/Get failure cannot retain a prior success mask. No additional native call, read, write, retry, raw register value, path, pointer, exception detail, privilege, setting or persistent access is introduced. The22API allowlist and all state/cleanup ownership rules above remain exact.

The emitter uses own-child-open-v2 with36numeric/6enum keys. The only new numeric key is context_mismatch_mask, initialized-1 and reset per immediate round-trip. The v1 validator remains strict35numeric/6enum and rejects all v2 keys/reasons. The v2 validator requires its exact36keys and adds only the three fixed reasons above. A native Get failure requires API GetThreadContext and mask-1; mismatch requires API none/native0/mask1..0x1fffff; unavailable requires API none/native0/mask-1. Each of these three new errors requires pair_complete0. The existing context_failed/SetThreadContext route requires mask-1 and pair_complete0 because reset precedes Set and failure precedes pair completion. Other outcomes cannot carry a positive mask. Schema interpretation never infers facts missing from archivedv1 evidence.

Cumulative envelope grows13→15 solely by adding CmdDebugContextTests.cs and receipt_contract.py. Existing480-line fake suite keeps all tests with minimal hooks and calls a pure helper. The496-line audit extracts the existing projection validator and keeps all old test identities/negative guards. Test helper is included only in the workflow test-compilation list alongside ContractTests.cs. run-pilot continues to compile only Native.cs/Session.cs and stays byte-identical, as does the AppLocker44-file aggregate. Native adapter API declarations and original broker implementation remain unchanged. Each new code file stays<=500readable lines.

Verification: all21one-field bits and multidiff, valid/equally-invalid flags, null, exact equivalence, fake Set false, Get false error0/nonzero, successful Get mismatch/null, managed throw, stale mask reset after prior success, first-failure retention through cleanup, unchanged call ordering/counts, strict separate v1/v2 key/reason/range/type/cross-version tests, archivedv1 projection, all retained regressions, staged graph and independent exact-candidate review. Local managed compilation is unavailable unless an already-installed compiler is found; never substitute syntax-only for execution. No new native attempt is authorized by this document.

## v3 same-buffer EFLAGS XOR revision (source-only approval)

Corresponds to FR-8. Base888378cb08dbe434f23f7a1bfea7b2c5031c1d1a/tree5f0e2ed5a6bdc6147250e1fdd4a93d3cd922fdaf. Authenticated v2 run37191549430 ended incomplete: Set/Get succeeded, field mask8 identifies only EFLAGS, no target-open pair. It did not identify the differing flag bits or justify normalization. Both earlier experiments remain closed.

Session alone adds numeric eflags_difference_mask. Reset it and context_mismatch_mask to-1 before the existing Set. After the existing Get returns true and nonnull, first compute both local values: long fields=actual.RequestedMismatchMask(requested); uint flags=actual.U32(68)^requested.U32(68). Only after both computations, emit fields and (long)flags. This keeps bit31 positive and uses the exact requested object passed to Set. The requested/actual register values, change direction, contexts, paths and pointers are never emitted. There are no new native calls, remote reads/writes, retries, settings or access rights. Native.cs, SameRequested, RequestedMismatchMask, TF repair, failure Record and all abort/cleanup code are byte-identical. The existing SameRequested predicate remains the sole acceptance decision.

Emitter protocol is own-child-open-v3 with37 numeric/6 enum keys, the existing error enum, and exactly one new key. Existing v1/v2 schema objects retain their fields, error sets and behavior. v3 applies all v2 constraints, including pair_complete0 for the three context errors and mask-1/pair_complete0 for context_failed/SetThreadContext. Additional v3 rules: flags XOR is-1 or0..0xffffffff; both diagnostics are unavailable together; otherwise both are nonnegative, and ((fields &8)!=0) iff flags XOR!=0. Successful comparison/none-error requires both0. A non-EFLAGS field mismatch has positive fields with bit3clear and XOR0. Native Set/Get failure, null context and precomparison managed failure leave both-1. First recorded failure and its diagnostics survive cleanup unchanged. No bit identity, including TF or RF, authorizes a looser guard.

Scope:9 incremental paths,16 cumulative. Modify Session, existing ContractTests and ContextTests, audit.py, receipt_contract.py and3specs; add receipt_tests.py only. The500-line audit extracts existing fixture/encoded and ContextReceiptContracts to the pure test helper, loaded by exact sibling path without sys.path or module-cache reliance. Explicit re-export must preserve actual unittest test.id() inventory and discovery, including module names, with no omission/duplicate. Existing test bodies/mutations are preserved; v3 tests are added separately. Each code file remains<=500 readable lines. Native.cs, workflow, both compile lists, run-pilot, broker source/audits and AppLocker aggregate are unchanged.

Validation: all32 XOR bits including31; zero, multibit and allbits; TF set/clear failures; non-EFLAGS mismatches with XOR0; native false with error0/nonzero, null and managed failures; unavailable parity, stale reset, first-failure immutability; exact native call count/order; strict v3 type/range/version/missing/extra/consistency contradictions. Compare v1 and v2 behavior to the published validator over retained cases and their contradictions; revalidate both archived artifact bytes/projections. Preserve actual test IDs during extraction. Run all applicable local regressions and C# syntax checks, report managed execution unavailable locally, refresh staged graph and obtain exact independent review. Publication/native execution remains separately gated.

## Observer push-path integration correction

Corresponds to FR-6 and FR-9. Published54af1826e7c52dc145941351bc3f8bb5f82bf4cb/tree72aea3454cad7125a6bae42e1b5105acdc869874 was verified, but no workflow run was created: its changes were confined to specs and tests/windows-cmd-debugger-observation, absent from the existing push.paths list. Earlier observer increments also changed covered workflow/broker files, which concealed this gap.

Add exactly one line, tests/windows-cmd-debugger-observation/**, to the current workflow push.paths list. Preserve the dedicated branch filter ci/windows-lpac-runtime-diagnostic, all four existing paths, workflow_dispatch, contents:read permission, jobs, native/managed gates, invocation and all published v3 runtime/C# bytes. This deliberately extends CI coverage only to the observer subtree on the already-designated branch, not other branches or system access. No old run is rerun and no browser dispatch occurs.

Five incremental paths within the same16-path cumulative ceiling: workflow, observer audit.py and the existing three specs. The source audit locates the exact observer path once in the actual push.paths block and tests missing/altered/duplicate/misindented/out-of-block variants. No YAML dependency or generalized workflow framework is introduced. Run retained regressions, preserve all existing audit identities/guards, refresh staged graph and independently review the exact correction before publication. The resulting controlled run must pass compilation, managed/PowerShell and audit gates before the one pending v3 observation.

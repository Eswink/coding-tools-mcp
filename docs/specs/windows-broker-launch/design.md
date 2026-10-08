# 设计文档：windows-broker-launch

## 概述
Covers FR-1 through FR-7 and NFR-1/NFR-2. All implementation is a standalone scripts fixture; the existing Windows VM session and application call graph are untouched.

## 技术方案
### 技术选型
Native C++17/MSVC with Windows SDK: CreateProcessW, FileIdInfo, BCrypt, debug APIs, explicit inherited pipes and owned _beginthreadex readers. PowerShell uses already installed VS tooling, builds two marker images, verifies imports and writes their manifest. Use installed vswhere/VS tools and fixed commands that call VsDevCmd then compile the known sources; never dump/serialize the complete CI environment (including `VsDevCmd && set`). Capture compiler version/build/import output only. No dependency installation.
### 架构设计
prepare.ps1 creates an unguessable owned run directory containing separate trusted harness/code and trusted cwd areas plus isolated mutation fixture directories. It creates only owned directory junctions whose targets are inside that run directory. The harness owns every case, image handle, process handle and reader; no caller cancellation abandons them.
State sequence: Prepared -> CreatedUnadmitted -> ImageCompared -> Admitted -> ExitEventContinued -> ProcessSignaled -> PipesJoined -> Retired. Any failure becomes Terminating; retirement still requires actual signaled death and joined EOF readers. Failed completion becomes UnknownRetained and fails the suite.
The creating thread runs launch and every WaitForDebugEvent/ContinueDebugEvent call. Readers use owned _beginthreadex handles and independently drain the two pipes with bounded PeekNamedPipe/read loops and record EOF. Their heap-owned state survives any uncertain join until harness exit. Parent copies of child pipe ends close immediately after creation, enabling EOF; only three required child ends are inherited. Reader completion is joined before result return and cleanup.
An owned PROCESS_INFORMATION process handle is retained as the independent wait/terminate authority, distinct from OS-owned debug-event handles; any duplication is checked. The initial thread handle from PROCESS_INFORMATION is closed once; debug-event process/thread handles remain OS-owned.
At the first actual create event, capture raw hFile availability/identity/hash separately from the effective fault-injected decision. Query/hash the retained and OS image handles; require volume+128-bit ID and SHA-256 equality, a matching manifest, and no pre-admission marker. Close event hFile after inspection, retain the checked image handle through death and reader join.
Reject by calling TerminateProcess on the owned process handle. Only after success may a pending event be continued for termination drainage; never mark admission. Continue exit event, then wait for the independent handle to signal. Do not infer death from TerminateProcess success, EXIT_PROCESS_DEBUG_EVENT alone, closing handles, reader cancellation, or a job timeout.
Close LOAD_DLL hFile immediately. Continue ordinary thread/DLL/output-string events. Handle one expected initial first-chance breakpoint; forward other first-chance exceptions, reject unexpected second chance and RIP/unknown events. The expected loader breakpoint is recorded in normal cases; unexpected exception handling remains a fail-closed reviewed path.
Post-admission fault deadlines start only after marker-file and both output-pipe observations establish stub entry, within the original execution deadline. All fixture files are retained as evidence; only the retained handle is retired after complete lifecycle proof. Deadlines bound the loops, not every potentially stalled Win32 syscall; the finite Actions job is the outer limit. Deadlines are finite and independent for admission, execution, drain and reader shutdown; failed waits/continuations/EOF preserve failure. If safe completion cannot be established, retain owned artifacts and let normal debugger-exit kill behavior remain intact; that fallback is not counted as observed death or successful cleanup.

## 数据模型
ImageIdentity = unsigned 64-bit volume serial, 16-byte file ID, 32-byte SHA-256 and byte length. RetainedImage owns a noninheritable handle and verified identity. LaunchRequest contains only fixture-generated absolute paths, fixed stub args, expected manifest hash, bounded fault enum and case ID.
LaunchResult records actual OS hFile observations, effective decision, no-marker-before-admission, admission flag, termination result, event error and exit code, independent wait result, reader EOF/join states, cleanup eligibility and retained/observed identities. Output is bounded JSON written by the harness after each case.
Fault modes act at named boundaries after real creation/event delivery, except a manifest failure which prevents creation. They do not replace the native process, event, wait, terminate or pipe lifecycle with a fake.

## API 设计
fingerprint(HANDLE) -> ImageIdentity/error (FR-1); run_launch(LaunchRequest) -> LaunchResult (FR-1..FR-4); run_case(Case) -> verified evidence (FR-5/FR-7); marker entrypoint -> fixed marker then exit or bounded hold (FR-2/FR-5).
No exported application API, service, shell command interface, network endpoint, persistent configuration or dependency contract changes.

## 文件结构
scripts/windows_broker_launch/launch.h defines the narrow owned types; launch.cpp implements fingerprinting, launch, pump, readers and failure drainage; cases.cpp owns fixture mutations and per-case assertions; fixture.cpp is the harmless no-CRT marker.
scripts/windows_broker_launch/prepare.ps1 builds and manifests the binaries. .github/workflows/windows-broker-launch.yml runs only on pushes to `ci/windows-broker-launch-followup-20261008`, checks out exact reviewed source with sole parent equal to baseline, invokes preparation/harness and validates bounded allowlisted evidence before upload. Three docs/specs/windows-broker-launch documents contain the spec; exact budgets are in tasks.md.

## 设计决策
### 决策 1: OS image-event authority (FR-1/FR-2)
The documented create event occurs before user-mode execution. Gate on its hFile, not a reopened launch path. Bytes and identity are both necessary; retained FILE_SHARE_READ protects ordinary data/delete opens but is not metadata/ancestor authority.
### 决策 2: Reject and drain on one owner thread (FR-3/FR-4)
The same owner that created the child services its debug port through exit. A rejected event may continue only for confirmed termination drainage. Event-owned handles and CreateProcess-owned handles are tracked separately to avoid double close.
### 决策 3: Keep DLL authority explicit (FR-6)
All executable parent directories and the CI account are trusted; mutation tests contain only self-built images and no DLL planting. Import inventories, no-CRT marker and restricted child environment reduce ambiguity but do not prove general DLL authority. No registry/ACL or loader policy changes are made.
### 决策 4: Sequential owned mutation fixtures (FR-5)
Each case starts fresh. The v2 ancestor case requires an actually denied first rename (5/32), no replacement, and unchanged-A launch; unexpected rename success fails without launch. The separate junction case must actually replace only owned junction names and reject selected B. Identical-byte copies must have different full FileIdInfo or setup fails.

## 风险评估
High semantic security risk despite no baseline callers: errors in pre-execution gating, debugger continuation or cleanup could overstate safety. Independent source review, real Windows lifecycle evidence and explicit unknown retention are mandatory. Graph absence for new C++ symbols is not proof of low semantic risk.
Unproven native details remain observations: OS hFile availability/readability, full-ID support, share/delete behavior of ancestor redirects, pipe EOF timing and runner MSVC availability. Unsupported outcomes fail/defer the affected claim; they do not justify broader changes.

## 官方依据
- [Debugging Events](https://learn.microsoft.com/en-us/windows/win32/debug/debugging-events): create event ordering, image handle access/closure, event-owned handles and kernel-shutdown wait.
- [CREATE_PROCESS_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-create_process_debug_info): nullable image hFile and ownership.
- [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info): volume plus 128-bit identity.
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew): sharing and reparse limitations.
- [WaitForDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent) and [ContinueDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-continuedebugevent): creating-thread affinity, exceptions, event-handle closure.
- [DLL search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order): executable directory and dependent DLL resolution.
- [UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute) and [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags): explicit inheritable handle list and DEBUG_ONLY_THIS_PROCESS limits.

## V2 终止后证据边界
LaunchResult adds stdout_peek_error/stderr_peek_error (DWORD), deferred_closed_pipe_observation/no_pipe_output_after_retirement (bool); Case adds marker_checked. Raw errors, pre-admission absence and terminal pipe proof are separate JSON facts.
Only the qualified injected wait109 path in the v2 requirement may defer the observation; its Reason::Wait/error31 remain sticky and it cannot enter admission. Non109, positive bytes/seen flags or failed marker query remain failure.
After actual signaled death plus joined EOF/zero-byte readers, compute terminal pipe proof before cleanup eligibility; absent proof is sticky failure. run_case then performs the marker-file check before retiring the pin and passing. Retain v1 failed records unchanged and require contract_version=2 on the new exact branch.

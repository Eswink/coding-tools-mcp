# 设计文档：Windows VM session

## 概述

FR-1 through FR-7 and NFR-1 through NFR-3 are one bounded engineering increment. The current dispatcher still rejects remote Windows exec. Existing LocalAdmissionPermit, NativeGuard, RootIdentity, exec and session implementations are unchanged.
**Production launch authority is unresolved:** the current increment compares the actual first debug-event image identity/hash before continuation. This local image proof still trusts code ancestors, host account and DLL directories; it does not grant production launch authority.

## 技术方案

### 技术选型

Use a concrete Rust WindowsVmSession and a private child Go executable with inherited anonymous pipes. This reuses measured HCS handling without rewriting HCS/resource/GCS internals in Rust or introducing a cgo DLL/ABI. No backend trait or public API is added.
Compile the Go sources inside the exact official hcsshim checkout because its measured packages are internal. Use its unchanged vendor graph, CGO disabled and the exact reviewable two-line patch (literal \t indentation is decoded and separately hash-checked before git apply). Keep experimental registry/canary code out of this binary.

### 架构设计

- Rust owns NativeGuard, pinned helper file, actual child, request writer, output/error readers and detached worker. Only child test modules can construct the CI entry.
- Go owns UVM/container/resources and guest streams. Image import is a separate short-lived invocation; only that invocation temporarily enables Backup/Restore after both blob hashes pass.
- A trusted bootstrap installs the fixed guest supervisor and stock runtime bundle into the private VM filesystem. Two processes consume exactly six stdio IDs; GCS is the seventh allowed service.
- The pinned GCS allocation/one-accept-close source hashes and exact service configuration are build gates. No late process/channel creation, optional mappings, registry, NIC or dynamic policy update.
- Fixed guest operations are runtime roundtrips and synthetic descendant/input fixtures. Untrusted guest output is nested data, never executable host instructions or a lifecycle receipt.

## 数据模型

Version 1 frames are little-endian u32 length followed by UTF-8 JSON, length 1..65536 and total 1MiB. Every host envelope binds source SHA, session UUID and monotonic sequence. Go generates an owned VM UUID before creation; the first prepared/creating identity binds all later events.
Requests are fixed Prepare, Start, Cancel and Finish operations; no arbitrary executable, host path, HCS JSON, security descriptor, image URL or VM target is accepted from a caller. Internal CI paths enter only through the source-bound trusted bundle.
Events are typed Prepared, Creating, Running, GuestOutput and HostCleanup. GuestOutput has a separate nested schema. Terminal must be last, followed by EOF and successful helper wait; success requires all independent cleanup and quarantine fields.
Rust deserializes directly into deny_unknown_fields typed structs/variants, preserving duplicate-field errors. Go first rejects invalid UTF-8/lone surrogate escapes, walks Decoder.Token with exact required field names, per-object key sets and depth limit 8, then performs typed decoding; null lists, duplicates and trailing values fail. Decoding into a generic map first is forbidden.

### Frozen wire v1

Every field below is required, including empty strings/lists/nulls; unexpected fields are rejected. Frames use u32 little-endian length. Requests have `version,source,session,seq,op,fixture`; op is prepare/start/cancel/finish and fixture is runtimes/live-child. Request seq starts at 0 and increments per send. Source is the 40-character build SHA, session a canonical UUID. Broker rejects source different from its link-time buildSource.
Events have `version,source,session,seq,kind,vm_id,runtime_id,guest,cleanup,error`; kind is prepared/creating/running/guest/cleanup. Event seq is independent and starts at 0. vm_id is generated/retained by the broker before prepared; runtime_id is empty until CreateWCOW succeeds, then immutable. guest and cleanup are nullable typed records; error is a bounded string. Only their matching kind may carry a non-null record.
GuestResult has `cases,input_sha256,output_sha256,data_base64,child_alive`. Case has `name,stdout,stderr,exit_code,passed`. Cleanup has `terminate_ok,whole_vm_exited,exit_ok,close_ok,guest_io_joined,quarantine,input_sha256,output_sha256,owned_data_retained,network_denial_proven,workspace_integration,production_admission,errors`. quarantine is written/withheld/not-started; all three qualification flags must be false. No host path is returned in wire data.
Normal flow: prepare/prepared, start/creating/running/guest, finish/cleanup/EOF. Live-child flow reaches running/guest with child_alive, then cancel/cleanup/EOF. Cancellation at any point initiates cleanup; only complete native evidence permits drained cancellation. Prepare does no HCS work. Start is the irreversible uncertainty boundary. Missing/malformed frames cause sticky error and teardown; no synthetic helper event is treated as authoritative in production.
Runtime fixtures are fixed in the guest binary; synthetic input is `ctm-synthetic:` plus the session UUID, <=1KiB, and output is its uppercase byte sequence. Quarantine locations are known internal children of the fresh CI session directory. The Rust/native test observer receives only validated outcome/identity/guest/cleanup, not a new execution capability.

## API 设计

Private constructor acquires the paired child guard synchronously; no exported arbitrary-path constructor exists. An internal read-only observer waits for completion without owning cancellation. Dropping the controlling session sends Cancel; dropping only a waiting future does not terminate the worker.
The detached worker calls native_drain::begin before creating the broker. Prepared means no HCS creation yet. Before attempting to write Start, Rust transitions to CreatingMayExist; partial/broken write or broker failure thereafter cannot become NotStarted.
State order: RegisteredNoEffects -> BrokerPreparedNoHCS -> CreatingMayExist -> RunningOwnedVM -> Terminating -> ExitedAndIOJoined -> QuarantineHandled -> Retired. Any uncertain stage ends with the existing persistent root/cloud fence.
Definite pre-Start failure can retire only after no Start attempt and any owned helper/I/O is finished. VM retirement requires bound host cleanup proof, independent Terminate/Wait/ExitError/Close, joined guest and host I/O, helper exit and quarantine handling. Guest exit/host Job accounting is never sufficient.
Normal result writes the new quarantine output after VM exit and verifies input identity/hash and output readback. After validated guest readiness, cancellation closes/waits the supervisor before terminating the UVM containing its detached child; early cancellation cannot use that readiness. Teardown releases real channels before joining pending half-closes. Known drained cancellation records output withheld and remains cancelled. Malformed protocol, unknown create, missing joins or cleanup errors are sticky uncertainty, even if a later event looks successful.
No running guard is tied to the caller JoinHandle. On panic/owner loss its Drop retains the existing recovery fence. Data is never deleted automatically on uncertain exit.

## 文件结构

`src-tauri/src/tools/windows_vm.rs` owns the session; child protocol/test modules hold wire validation and tests. `services/windows-vm-broker` contains the concrete owner, guest supervisor, protocol and quarantine. The fixed preparation script and isolated Actions workflow build/test these exact files. Full path/cap inventory is in tasks.

## 设计决策

### 决策 1: Separate host and VM completion authority (FR-2, FR-3, FR-6)

A trusted broker receipt is necessary but insufficient. Rust additionally proves its owned process and pipes have finished and validates exact identity/order. A guest can corrupt its supervisor but cannot create a host HCS completion event.

### 决策 2: Preserve measured policy without qualification canaries (FR-4)

Reuse the restricted creation profile only. The previous matched static experiment remains source-specific evidence; extracting unchanged policy mechanics does not prove all aliases or global egress. Changes to those mechanics require review, not an automatic rerun or inherited PASS.

### 决策 3: Keep deployment and workspace gates separate (FR-1, FR-5)

All new storage is synthetic, using the established Go os.Root mechanism. No production RootIdentity/copyback/snapshot migration occurs. Default build compiles the private module; native tests opt in explicitly. No packaging, default feature or public route is enabled.

## 风险评估

- HIGH: mistaken retirement can release root/cloud fences. Require legal state/identity and every independent lifecycle/IO/quarantine field; faults remain uncertain.
- HIGH: native syscalls and writer work can stall. Cooperative owner deadlines publish sticky uncertainty and keep fences; they cannot interrupt a kernel call or promise bounded host shutdown.
- HIGH: path-launch authority is unqualified. Limit to trusted immutable CI parent and no public construction; retain a separate production gate.
- HIGH: cross-language schema drift/guest spoofing. Duplicate-aware typed parsers, source/version binding, bounded frames and nested guest-only data.
- MEDIUM: pinned runner/compiler/runtime changes. Fail before import, diagnose actual differences, never silently replace the runtime.
- Evidence limits: Server2025 runner only, no user machine/Windows11 qualification, no global network proof or real workspace authority. Microsoft client license use is coding development/test.

## 验证与迁移

No existing application data, ledger, workspace or protocol migration. Two native tests are serial on one fresh standard windows-2025 runner after all pure tests/builds pass. The first covers four stock runtimes, caller-wait loss, held native fences and quarantine; the second cancels a live guest descendant and proves drained cancellation/output withheld.
Raw errors and traces are bounded; artifacts contain evidence and hashes, no credentials, signed URLs, runtime bundles or images. Source and tree are rechecked after execution. Installation, signing and actual backend routing await their own review.

## Finite admission design (FR-8)

The latest Git-budget profile gains exactly four select-dispatch and two normalization lines. The new Windows profile pins actual F commit bytes/tree/parents, freshly calls historical selected_profile(F), permits only ordered D/I/J, and applies four existing release-document overlays. Only topology mismatch may delegate. Content, historical, overlay and budget exceptions remain terminal.
All 24 changed paths use100644 blob mode. The 23 nonself paths bind blobSHA1/SHA256/bytes/lines; independent complete-tree review binds the profile itself. Four byte inverses restore tools/mod.rs, latest Git-budget profile/cases and publisher workflow. The workflow passthrough set contains exactly its nine Git-budget PRIOR identities plus BASE; no dynamic history enumeration.
Twelve fixed cases cover baseline identity, topology, pins/entries/caps, complete inverses, finite historical passthrough, corruption, terminal failures, fresh validation, preserved1541/303/452 inventories/assertions and workflow outcome receipts. Historical tests change only one import and eight finite source-reading operands; their IDs and assertions remain unchanged.
Native workflow keeps read permissions, events, timeout and fixed two serial cases, switches to exact publisher Windows branch and actual F sole-parent equality with F receipt. Publisher adds12 explicitly counted cases. D/I source trees must be equal; J differs by exactly four release documents. Reused61 runtime IDs require fresh newD hosted provenance and matching source/test/fixture/workflow/envelope joins; admission context always reruns.
CRITICAL graph impact: Git-budget normalize has46affected symbols/13direct callers/10flows; select has9affected/3direct/0flows. Root explicitly acknowledged this impact before implementation. Four complete byte inverses, unchanged old assertions, fresh admission and independent final tree/diff review remain required.
Integration baseline is actual merged F `7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116`, tree`2862d635ab7ce082ad863d9315514537df8864f1`, ordered parents[`8bdd5f327b4603c5570dc764e2d62fecbe6e02d2`,`76949e7e496ee4a5a3a7554d26e2cd67691f07e0`]; signed raw1227bytes/SHA256`38f560ddd99ace241b4925b558ddb386ec45f40fac111e9134a574be1f73901c`. `8bdd5f32` remains only the measured runtime donor baseline; exact native source is`79ac13ca`. Previous native evidence cannot qualify newD.

## Verified launch ownership (FR-9–FR-14)

Runtime-preparation baseline is actual PR144 F649dc0fcb0bd299ebf7910e567e09c32b7962a9b, tree956807f8c35b6ce12272b3abcfbbd85493e9c9f9; ordered parents7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116 and970b5aba7b69b3a9d0a86c85e6cbaeac72839e9a. The publisher source-budget increment has merged; final launcher admission uses actual F13cd343d942b7a68912d42a8f9235c02ed647764.
The detached run_owner owns a non-Send OwnedBroker, retained image and NativeGuard. launch.rs owns supported windows0.61.3 CreateProcessW/debug APIs; image.rs owns full identity, bounded hash and checked handle closure; host_io.rs owns one capacity-one writer and two output workers. Only Diagnostics_Debug/Pipes/SystemInformation features are added. No handwritten ABI or dependency change.
Launch ledger: NoCreateAttempt, CreateCallEntered, ChildOwnedUnadmitted, ImageMatched, FirstContinueSucceeded, ExitEventContinued, ProcessSignaled, HostIOJoined, LocalHandlesRetired. Create errors with no child and checked owned-resource closure can be definite; partial results/panic/unknown call are uncertain. Local ledger is independent from unchanged HCS protocol.
Creation uses absolute application name, quoted mutable UTF16 command line, fixed session-root argument, trusted fresh code cwd, explicit inheritable stdin/stdout/stderr list and DEBUG_ONLY_THIS_PROCESS/EXTENDED_STARTUPINFO_PRESENT/CREATE_UNICODE_ENVIRONMENT. Minimal SystemRoot/WINDIR/PATH/TEMP/TMP environment uses supported system-directory APIs. Parent ends/pin/process handles are noninheritable; attribute storage and handle array outlive creation.
At the actual first process event, compare hFile volume64/all16 ID bytes/size/SHA256 with retained pin, then checked-close hFile. Do not reopen a path. Pre-admission output observations precede reader threads. First Continue must succeed before any Prepare or Start; later debug service never stops while local work remains. Close DLL event files without claiming DLL admission; forward ordinary first-chance exceptions, admit one loader breakpoint, and fence second-chance/RIP/unknown errors.
Owner scheduling services one50ms debug wait then at most8 messages, deadlines and finished joins. One writer serializes unchanged protocol bytes through a capacity-one queue; owner latches Cancel when full. Start-attempt is set before enqueue. Stdout parse errors cannot manufacture EOF; bounded stderr reader drains to actual EOF. Cooperative budgets: admission5s, write acknowledgement10s, Prepared30s, retirement180s, total9min. Admission checks before debug wait and before first Continue share one sticky first-expiration/late-ms decision; the owner observes it immediately after pump. Pin hashing precedes that clock; setup/create or another native call that never returns can prevent observation. Blocking native calls can prevent progress; no hard shutdown promise.
Completion extends only the private struct with launch:Option<LaunchReport> and OwnershipStatus {Unobserved,Active,Retired,RecoveryFenced}. Existing snapshot(outcome,errors), watch receiver and session control fields stay identical. Enrich snapshots before Arc publication. Sticky Uncertain never reverts to Pending/success. Retain owner/handles/pin and guard until process and actual joins; then drop uncertain guard into existing recovery fence.
Before Start, failure may terminate the owned helper and drain it. After Start, only cooperative Cancel is sent; debugger/process exit never proves HCS retirement. Known success requires both local image/process/EOF/join/checked-handle proof and unchanged trusted HCS cleanup/quarantine validation. Raw wait/continue/native errors remain evidence. Wait-fault raw109 rejection is qualified only after termination, signaled process, joined zero-byte EOF and final marker absence, never early admission.
Trust remains the disposable windows-2025 x64 CI host account, code/cwd ancestors, system DLL directories and imports. Retained read sharing does not establish ancestor authority, DLL closure or hostile-host protection. V2 C++18-case pass is source-specific precedent; v1 remains11/18 failure. Only its29-line marker fixture is reused. No real workspace, privilege, ACL, mitigation or named endpoint changes.
Required sequence: exact source/spec/impact review; locked native compile/format/pure inventories; six harmless Rust cases; two actual HCS cases; final D/I/J admission and independent tree/evidence review. No native stage is claimed before it executes. Exact final admission inventories await actual post-source-budget F.

## Finite launch admission (FR-15)

Actual F is `13cd343d942b7a68912d42a8f9235c02ed647764`, tree `f2be2e09cca27081cccad11d94ed29858b955df9`, ordered parents[`649dc0fcb0bd299ebf7910e567e09c32b7962a9b`,`af5ca34eebe0a6c1c55153acdd1ef1855df037a9`]. Signed raw1236bytes/SHA256`7facd10b0d1d2bd44b1cecd637f99a9360acb404a8be5af86cd1731f36933e13`; baseline1840 entries, final1848 from eight additions.
The new Windows-launch profile is reached by exactly four select and two normalize lines in the source-observation profile. Check D/I/J shape before the release-anchor assertion so unrelated historical shapes delegate. Once selected, bad release/content/baseline/cap data remains terminal. Validate actual F through the unchanged historical selector and pin its full raw bytes, tree and ordered parents; no inferred ancestry or equal-tree substitution.
Exactly19 paths change. Eleven modified paths have complete actual-F inverses; unique finite fragments may reconstruct them, with full original-byte/hash/count checks afterward. Eighteen nonself sources have exact mode/blob/SHA256/bytes/lines pins; independent tree review binds the profile itself. Historical passthrough is exactly12 publisher-workflow identities and one preceding Windows-case identity.
Eight finite source-observation test operands use the new normalizer. Three existing Windows operands (donor owner/native-test hashes, native workflow, spec census) reuse source_observation_bytes. Its existing AST restoration removes them; the original changed-method set already covers both methods, so line295 stays unchanged. Every old assertion and ID is preserved, without a generic whitelist.
Only test fixtures may memo the exact immutable historical F after ref/tree/parents/raw and callback/argument identity match. Freshness and terminal-failure probes bypass that memo. Runtime F and candidate checks remain uncached. Publisher adds12 explicit cases with loaded/executed/exceptional-outcome receipts; all D/I/J source contexts execute their required gates before normal integration.
Compiler evidence is source-specific: run37792525154 failed formatting/type inference; run37794972328 passed locked Rust1.98.1/windows0.61.3 checks and18 non-VM IDs; run37800018511 passed compilation/18 IDs but failed formatting. Its only formatter delta is two method-chain line wraps (launch493 lines), verified by complete syntax-tree equality. Six harmless native cases and two HCS cases were not executed in those compiler workflows.
Final native source must freshly pass default format, locked build/library lint, exact inventories,18 non-VM Rust/12 Go/six harmless launch cases before image import, then two sequential HCS cases. All38 bind the final candidate source/raw/tree and actual runner/toolchain. No prior compiler outcome or earlier HCS source qualifies the new candidate by itself.

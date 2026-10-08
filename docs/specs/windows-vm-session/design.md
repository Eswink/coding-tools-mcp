# 设计文档：Windows VM session

## 概述

FR-1 through FR-7 and NFR-1 through NFR-3 are one bounded engineering increment. The current dispatcher still rejects remote Windows exec. Existing LocalAdmissionPermit, NativeGuard, RootIdentity, exec and session implementations are unchanged.
**Production launch authority is unresolved:** retained-file hashing is only an extra CI mutation check. The trusted private parent assumption is not a production executable identity guarantee; future production admission needs reviewed launch-image/ancestor authority.

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
- HIGH: trusted-broker pipe writes/receives/joins are currently unbounded if it stalls; the recovery fence remains held, but bounded host shutdown is not claimed.
- HIGH: path-launch authority is unqualified. Limit to trusted immutable CI parent and no public construction; retain a separate production gate.
- HIGH: cross-language schema drift/guest spoofing. Duplicate-aware typed parsers, source/version binding, bounded frames and nested guest-only data.
- MEDIUM: pinned runner/compiler/runtime changes. Fail before import, diagnose actual differences, never silently replace the runtime.
- Evidence limits: Server2025 runner only, no user machine/Windows11 qualification, no global network proof or real workspace authority. Microsoft client license use is coding development/test.

## 验证与迁移

No existing application data, ledger, workspace or protocol migration. Two native tests are serial on one fresh standard windows-2025 runner after all pure tests/builds pass. The first covers four stock runtimes, caller-wait loss, held native fences and quarantine; the second cancels a live guest descendant and proves drained cancellation/output withheld.
Raw errors and traces are bounded; artifacts contain evidence and hashes, no credentials, signed URLs, runtime bundles or images. Source and tree are rechecked after execution. Installation, signing and actual backend routing await their own review.

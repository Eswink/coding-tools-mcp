# 需求文档：Windows VM session

## 功能概述

Add a concrete Rust-owned session backed by the measured Go HCS path, using only synthetic CI inputs and quarantined outputs. Historical PR144 admission baseline: merged F `7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116`. Verified-launch runtime preparation uses PR144 merge `649dc0fcb0bd299ebf7910e567e09c32b7962a9b`; final admission binds actual PR145 merge `13cd343d942b7a68912d42a8f9235c02ed647764`. The measured runtime donor baseline remains `8bdd5f327b4603c5570dc764e2d62fecbe6e02d2`; preserved donor source is `79ac13ca4f2236d0a81576200c47d8d240eb02a3`.
This is latent engineering code, not a Windows execution admission path. Production launch-image authority, workspace authority, network qualification, desktop qualification and packaging remain unresolved gates.

## 历史经验与坑（来自记忆库）

- Source-specific evidence: [static policy and whole-VM pass](https://github.com/Eswink/coding-tools-mcp/issues/81#issuecomment-6055366932), source `18f2aaaf682b35f80152b7e2803d38ae772cdd22`.
- Dynamic descriptor updates did not deny the tested connections; use creation-time policy only. A host process/job exit is not whole-VM proof.
- An image file handle/hash does not establish ancestor-path launch authority. The bounded CI assumption below cannot qualify production launch.

## 范围边界

- In scope: private Rust session, fixed Go owner/supervisor, strict pipe protocol, paired NativeGuard, fresh synthetic quarantine, native CI evidence.
- Out of scope: public constructor/dispatch, real workspace/copyback, snapshots, host setup/security/network changes, registry canaries, user computers, packaging or production enablement.
- Host trust assumption: one fresh task-owned directory under RUNNER_TEMP on a dedicated ephemeral runner; trusted host tooling does not rename/replace its parent during launch. Guests cannot map it. No protection from hostile same-user host processes is claimed.
- Client-host container use remains development/test. No runtime or image redistribution in evidence.

## 需求列表

### FR-1: Preserve admission and launch boundaries

**优先级:** Must. **用户故事:** As an engineer, I need the actual VM owner testable without enabling unqualified Windows execution.
#### 验收标准（EARS）
1. WHEN compiled THEN the Windows module SHALL remain crate-private with no public caller constructor, routing or arbitrary path activation.
2. WHEN launched by its native test THEN the owner SHALL verify the retained broker image hash and source-bound CI bundle under the explicit trusted-parent assumption.
3. IF production image/ancestor authority is unqualified THEN production admission SHALL remain false; file hashing alone SHALL NOT qualify it.

### FR-2: Enforce a bounded cross-language protocol

**优先级:** Must. **用户故事:** As the host owner, I need untrusted guest bytes unable to forge host completion.
#### 验收标准（EARS）
1. WHEN reading a frame THEN both languages SHALL enforce version, source, session UUID, sequence, typed payload, length and aggregate bounds, duplicate/unknown-field rejection and no trailing value.
2. IF a frame is malformed, replayed, oversized or mismatched THEN the owner SHALL fail conservatively and never accept a guest payload as a host cleanup receipt.

### FR-3: Retain paired native work independently of callers

**优先级:** Must. **用户故事:** As the root/cloud drain, I need actual native work to outlive cancelled waiters.
#### 验收标准（EARS）
1. WHEN starting a session THEN register synchronously and begin NativeGuard before broker/HCS side effects; the independent worker SHALL own the guard, child and I/O tasks.
2. WHEN a caller or waiting future disappears THEN the worker SHALL continue owned teardown; caller cancellation SHALL NOT abort the owner.
3. IF Start may have been written or HCS creation was attempted THEN helper failure SHALL NOT be converted into definite no-effects completion.

### FR-4: Reuse the measured fixed HCS boundary

**优先级:** Must. **用户故事:** As an engineer, I need a concrete supported runtime path rather than a generic unused adapter.
#### 验收标准（EARS）
1. WHEN creating THEN use pinned HCS sources/default-deny patch, exactly GCS plus six stdio entries, no NIC, 2vCPU/2GiB and ContainerUser.
2. WHEN bootstrap and supervisor channels are established THEN retire their one-accept listeners before guest workload; use existing streams, no policy update or later HCS process creation.
3. WHEN finishing THEN Terminate, whole-VM Wait, ExitError and handle/resource closure SHALL be independently checked; close alone SHALL NOT imply exit.

### FR-5: Bound synthetic transfer and quarantine

**优先级:** Must. **用户故事:** As an engineer, I need observable byte transfer without asserting real workspace authority.
#### 验收标准（EARS）
1. WHEN preparing THEN create fresh owned synthetic roots, retain os.Root and file identities, and bind at most 1KiB of input to its hash/session.
2. WHEN returning normal output THEN write a create-new quarantine file only after whole-VM completion; verify retained identity, unchanged input, output hash and readback.
3. WHEN cancelled THEN withhold output and record that disposition; no actual workspace application SHALL occur.

### FR-6: Fence uncertain completion

**优先级:** Must. **用户故事:** As a recovery owner, I need uncertainty to remain sticky across helper and protocol failures.
#### 验收标准（EARS）
1. IF create, helper, identity, protocol, I/O join or required cleanup is uncertain THEN retain owned data and the existing root/cloud recovery fence.
2. WHEN retiring THEN require a bound final host receipt, whole-VM proof, all guest/host I/O joined, helper exit, and completed quarantine disposition; cancellation SHALL remain a cancelled result.

### FR-7: Bind native evidence to the actual candidate

**优先级:** Must. **用户故事:** As a reviewer, I need native evidence for this source and its explicit limits.
#### 验收标准（EARS）
1. BEFORE import/boot SHALL run compiled inventory, 18 Rust and 12 Go pure tests, native broker/guest builds and Rust production-library checks.
2. WHEN CI executes THEN run exactly two sequential owned VM cases: stock-runtime/quarantine success and cancellation with a live descendant; no new registry entries or existing-service probes.
3. WHEN reporting THEN bind source/tree/parent, toolchains, runtime/image hashes, protocol/lifetime outcomes and cleanup; all production/network/workspace qualification flags remain false.

## 非功能需求

- NFR-1: 64KiB/frame, 1MiB/protocol stream aggregate, nesting depth 8, 64KiB guest command output per stream; overflow is sticky failure.
- NFR-2: Source files below 500 lines; current launch increment has19 paths/3,800 changed lines; historical PR144 scope remains recorded in tasks. Native tests must be nonzero and match the compiled inventory.
- NFR-3: No Cargo/npm/Go dependency lock changes. No automatic feature/service/network remediation or hidden runtime substitution.

## 依赖关系

Rust 1.98.1 and existing desktop crates; Go 1.24.13; hcsshim `fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd` with vendored locks and reviewed default-deny patch; Node 22.23.3, pwsh 7.6.6, ServerCore 10.0.26100.33438 pinned manifest. Missing pins fail before import.

## FR-8: Finite Windows engineering admission

**优先级:** Must. **用户故事:** As a reviewer, I need exact new source admission without granting production authority.
1. WHEN selecting THEN validate actual merged F `7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116` SHA/raw size/SHA256/tree/ordered parents freshly through its historical profile; accept only D[F], I[F,D], J[R,I] with the four frozen release documents.
2. WHEN validating content THEN require exact 24-path delta, 1833 entries, 23 nonself pins, four complete byte inverses, ten fixed historical workflow identities and individual/4700 aggregate changed-line caps.
3. IF topology differs THEN delegate; IF selected content, baseline, release overlay or cap fails THEN fail terminally without cache, dynamic whitelist or correction chain.
4. WHEN verifying THEN preserve all original1541 IDs/assertions, strict303 and consumer452; add exactly12 admission cases and explicit publisher receipts. D1553=1184local+369hosted; I1214=398local+755hosted+61qualifiedD; J1214=1153local+61qualifiedD.
5. WHEN executing native validation THEN rerun newD16Rust/12Go/two serial HCS cases, preserving old runtime bytes and all false authority flags; previous79ac proof is source-specific only.

## Verified launch increment

The initial nineteen-path D750 packet passed native38 but failed the historical native Cargo fixture. D2 adds one sealed fixture operand; its Ubuntu425 run exposed the old1553 AST guard also needing the exact byte inverse before comparison. The next forward repair accepts only pinned D2 as sole parent, retaining exact D750 origin, twenty paths and twelve inverses. All original assertion ASTs must survive inverse removal; require fresh D/I/J and native CI. No authority or held snapshot boundary changes.

### FR-9: Admit the actual image before entry
**优先级:** Must. WHEN CreateProcessW returns an owned child THEN compare its first CREATE_PROCESS hFile volume64/file-ID128/length/SHA256 against the retained manifest-checked image before the first Continue. Reject null/query/hash/identity failures; no Prepare bytes until checked first Continue. Hash at most64MiB, use explicit handles/cwd/environment and no shell.
### FR-10: Preserve launch ownership uncertainty
**优先级:** Must. WHEN creating THEN record call-entry before Windows; distinguish definite no-child from partial/in-flight/created failure. WHEN rejecting a child before Start THEN terminate only that retained process and require exit-event continuation, process signal, joined EOF and checked handles before known local retirement. WHEN Start may escape THEN never kill the broker as a VM-retirement substitute.
### FR-11: Keep the owner responsive cooperatively
**优先级:** Must. WHILE native effects exist THEN one owner pumps one debug event then at most8 queued messages, with a capacity-one writer and nonblocking owner enqueue. Record Start before writer access, retain terminal Cancel when full, and poll finished workers before actual joins. IF a deadline expires THEN publish sticky Uncertain/Active and continue ownership; after actual local accounting drop the running guard and publish RecoveryFenced. The first observed5s admission expiration SHALL retain its monotonic lateness, request cancellation and latch owner uncertainty in that turn; later observations or proposed clean outcomes cannot erase it. No hard syscall or host-shutdown deadline is claimed.
### FR-12: Bind independent local evidence
**优先级:** Must. WHEN normal completion is reported THEN require admitted image/first Continue, continued exit, independent successful process exit, writer/readers joined with genuine EOF, checked handle/pin retirement and unchanged Validator::finish HCS proof. Completion snapshots default to launch=None/Unobserved; real owners publish actual report and Active/Retired/RecoveryFenced without changing observer/session layout or snapshot signature.
### FR-13: Preserve eight explicit Rust additions
**优先级:** Must. BEFORE VM import THEN compile locked windows0.61.3 with exactly Debug/Pipes/SystemInformation additions and pass18 pure Rust/12 Go plus six real harmless launch cases. THEN run the same two serial HCS cases through this launcher:38 outcomes. Six cases cover match, wrong image, equal bytes/new ID, actual junction redirection, cancel before Continue, and raw109 wait-fault zero-output rejection after real retirement. Two pure cases cover launch-boundary ownership and blocked-writer responsiveness. No skip counts as pass.
### FR-14: Preserve scope and qualification limits
**优先级:** Must. WHEN integrating THEN preserve protocol.rs, old tests.rs, NativeGuard, Go, lockfiles, production/workspace boundaries and frozen pins. Reuse only exact29-line marker fixture hash4d08b93bc62b301b975c05ec54ce810db7fa4b70047f089c54a4a50153578d95. Seal the finite admission on actual post-source-budget F only. No security setup, named endpoints, DLL/ancestor/account authority, descendant-debugger containment or production qualification is granted.

### FR-15: Bind the final launch source and historical contracts
**优先级:** Must. WHEN this increment is selected THEN admit only D[actual D3b9b4e666], I[F,D], J[R,I], validating the three exact D3/D2/D750 raw/tree/parent anchors on actual F13cd343d942b7a68912d42a8f9235c02ed647764 with exact raw/tree/ordered parents, equal D/I source and four fixed release overlays. Validate the historical F afresh; candidate validation is never cached.
1. WHEN validating source THEN require exactly23 changed paths (8 added/15 modified),22 nonself pins,15 complete byte inverses,14 finite historical identities, per-file caps and aggregate3800. Self bytes require independent whole-tree review.
2. WHEN preserving historical tests THEN change exactly six dispatcher/normalizer lines, eight source-observation operands, three Windows operands and the exact Cargo/old1553/workflow read operands; restore all old methods/assertions and IDs. Topology mismatch alone delegates; selected content/baseline/release failures are terminal.
3. WHEN running gates THEN add exactly12 finite Python cases; verify actual inventories before claiming D1609/I1270/J1270 or publisher425. Final D executes fresh18 Rust/12 Go/six harmless launches/two serial HCS cases. Compiler-only evidence is historical and cannot replace these38 outcomes.
4. WHEN reporting THEN retain first compiler failure, corrected compiler pass and deadline compiler formatting failure separately; only exact verified formatter bytes may be folded. All production, launch, network and workspace authority flags remain false.

The actual D3 consumer failure is retained: interrupted fixture telemetry truncated its observation JSON. Only two inert fixture helpers publish via checked closed pending bytes and atomic replacement; original reader, all old test methods and HTTP close faults remain unchanged. Parent total/cleanup/readiness deadlines remain fixed. Both actual D3 Ubuntu425 runs passed the original Staging12 and failed only the historical readonly workflow operand; that operand now uses the exact complete F inverse, with every assertion preserved. Later groups and source-after were absent, so D3 was not admitted. D4 and its new native38/425/303/755/452/full D/I/J evidence remain pending.

The first uncommitted D4 focused138 run failed twice and is retained. The repeated old1328 inverse receives the exact historical supervisor blob e45608f7ae523c25ea5d12cd4d24cbd56a3f1c12 from frozen M981d7b23; only its complete blob/SHA identity is added to the finite prior table. No old test method, assertion, time budget or production source changes. The separate loopback cancellation connection observation failure remains under diagnosis; no final candidate qualification follows from this source correction.

The final D4 focused138 run retained one slow API-header failure: the local fixture socket cap0.10s could complete with a real read timeout before the selected-phase parent deadline0.5s. Only local_* fixture per-I/O cap becomes1.0s; nonlocal fixture0.10s and production15s stay fixed. Parent0.5s, cleanup0.5s, readiness0.9s, DownloadBudget global2.3s/cancel0.3s, all original assertions/method bodies remain unchanged. Controlled150ms gap must still exercise the real fixed parent deadline and confirmed child reap; all fresh same-source/CI gates remain required. The separate pre-connect cancellation observation race is retained and is not resolved by this per-I/O fixture correction.

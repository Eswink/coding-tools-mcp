# 需求文档：Windows VM session

## 功能概述

Add a concrete Rust-owned session backed by the measured Go HCS path, using only synthetic CI inputs and quarantined outputs. Baseline: `8bdd5f327b4603c5570dc764e2d62fecbe6e02d2`.
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
1. BEFORE import/boot SHALL run compiled inventory, 16 Rust and 12 Go pure tests, native broker/guest builds and Rust production-library checks.
2. WHEN CI executes THEN run exactly two sequential owned VM cases: stock-runtime/quarantine success and cancellation with a live descendant; no new registry entries or existing-service probes.
3. WHEN reporting THEN bind source/tree/parent, toolchains, runtime/image hashes, protocol/lifetime outcomes and cleanup; all production/network/workspace qualification flags remain false.

## 非功能需求

- NFR-1: 64KiB/frame, 1MiB/protocol stream aggregate, nesting depth 8, 64KiB guest command output per stream; overflow is sticky failure.
- NFR-2: Source files below 500 lines; 19-path/3,776-line cap in tasks. Native tests must be nonzero and match the compiled inventory.
- NFR-3: No Cargo/npm/Go dependency lock changes. No automatic feature/service/network remediation or hidden runtime substitution.

## 依赖关系

Rust 1.98.1 and existing desktop crates; Go 1.24.13; hcsshim `fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd` with vendored locks and reviewed default-deny patch; Node 22.23.3, pwsh 7.6.6, ServerCore 10.0.26100.33438 pinned manifest. Missing pins fail before import.

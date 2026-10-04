# Requirements: Windows snapshot warning scope (#105)

## 功能概述

New isolated bugfix from canonical c3fcfb1f2617d56f8f395317a18d93884d551789, tree2066e8ae62522e3a9ee579e03d36ebfbdddeafd0. Historical Windows strict desktop library compilation on identical snapshot blobs reports four diagnostics; fresh c3 reproduction is pending: unused Read/Write imports, unread Dir.file, unused non-Linux Dir.sync and unconstructed SnapshotError::Busy. The affected source blobs are e5d2ba5b3eb641a3904710051b58a49de5514f47 and 53daa75fc4b7390403504f2301a539361d0e8e93.

This corrects declarations exposed on unsupported platforms. It does not implement Windows snapshots, repair Issue #86 opened-root authority, complete Issue #81 integration or Issue #101 Windows process completion, or import unmerged PR #102/#104.

## 需求列表

### FR-1: Match declarations to their operating platform
**优先级:** Must
**用户故事:** As a maintainer I need strict Windows builds without suppressing genuine warnings.
### 验收标准（EARS）
1. WHEN compiling for Linux THEN Read/Write imports, Dir.file, Linux Dir.sync and SnapshotError::Busy SHALL remain available with unchanged operational bodies.
2. WHEN compiling for non-Linux THEN only Read/Write imports, Dir.file, unused Dir.sync stub and Busy SHALL be removed from that target surface.
3. File SHALL remain unconditional because non-Linux lock still returns Result<File>.
4. The production diff SHALL contain exactly the four reviewed edits in two source files, with formatting limited to the touched import declaration.

### FR-2: Preserve refusal and security contracts
**优先级:** Must
**用户故事:** As a caller I need unsupported Windows snapshot operations to remain fail-closed.
### 验收标准（EARS）
1. WHEN invoking any existing non-Linux operation THEN its Unsupported refusal body SHALL remain byte-identical, except deletion of the unused sync stub.
2. Authority, adapter, snapshot engine, metadata, transaction recovery, restore and all test files SHALL remain byte-identical to c3.
3. The enabled exact_native_restore_lease_waits_for_real_work_and_restores_saved_tree test SHALL retain its original positive assertions and SHALL execute on Windows. Its Unsupported failure SHALL remain an actual visible failed test until separately repaired.
4. There SHALL be no warning allow/expect, artificial read, constructor/Default, dependency, permission, authority or adapter-enablement change. Error display names and IPC formatting SHALL remain unchanged.

### FR-3: Strict warning evidence on the exact source
**优先级:** Must
**用户故事:** As a reviewer I need the warning fix proved by native compiler evidence.
### 验收标准（EARS）
1. The native Windows baseline SHALL be immutable c3 with the exact two source blobs. Its strict compile SHALL identify exactly the four named diagnostics and their source locations; dependency/setup errors or arbitrary nonzero exits SHALL fail the witness.
2. The exact candidate SHALL pass cargo rustc --locked --lib --manifest-path src-tauri/Cargo.toml -- -D warnings on Windows2025 and Ubuntu24.04, plus cargo fmt --all --check and locked all-target cargo check.
3. Native source/tree, commands, toolchain, exit status, diagnostic/raw logs and artifact identity SHALL be retained. Local syntax or parser checks SHALL NOT be represented as native compilation.

### FR-4: Regression and bounded publication
**优先级:** Must
**用户故事:** As a maintainer I need warning acceptance distinguished from incomplete product features.
### 验收标准（EARS）
1. Actual Linux full existing desktop regressions SHALL run with positive inventory/result counts. Existing Linux lock/Busy, metadata, recovery and restore tests SHALL remain enabled.
2. Actual Windows full existing desktop regressions SHALL run unchanged and retain real failures; expected failure counts SHALL NOT convert that job into success.
3. Warning-only acceptance SHALL be reported separately from Windows runtime, snapshot functionality, aggregate RC, physical-host and release gates.
4. Before publication, exact candidate review, fresh staged GitNexus analysis and gencommit SHALL be completed. Parent controls commits and external publication separately.

## 非功能需求

Two production files and three specification files are allowed. A sixth path for .github/workflows/windows-snapshot-warning-scope.yml has finite approval. No held PR #98 ref movement/run rerun, integration, merge, tag, release, credentials or security settings. Changed source files remain under 500 lines.

## 依赖关系

Existing desktop Cargo dependencies and unchanged native tests. Native CI may reuse existing pinned checkout/Rust and Linux prerequisites after finite workflow approval. No product-binary build is added or duplicated.

# Requirements: Windows snapshot warning scope (#105)

## 功能概述

Adopt the exact PR106 warning repair onto integrated base6edd4e6137a6947319183b3ac8801bfa608ac722, tree35cfad529c2427bac17c344089686b2cf3d46823. Historical run37211158809 proves the four-diagnostic c3 witness and donor strict-library success; fresh current-source native verification is pending. The unchanged baseline snapshot blobs report: unused Read/Write imports, unread Dir.file, unused non-Linux Dir.sync and unconstructed SnapshotError::Busy. The affected source blobs are e5d2ba5b3eb641a3904710051b58a49de5514f47 and 53daa75fc4b7390403504f2301a539361d0e8e93.

This corrects declarations exposed on unsupported platforms. It does not implement Windows snapshots, repair Issue #86 opened-root authority, complete Issue #81 integration or Issue #101 Windows process completion, or import donor/c3 ancestry or the held PR98 correction. The independently integrated Issue103 repair remains unchanged.

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
2. Authority, adapter, snapshot engine, metadata, transaction recovery, restore and all test files SHALL remain byte-identical to6edd (and their reviewed c3 originals).
3. The enabled exact_native_restore_lease_waits_for_real_work_and_restores_saved_tree test SHALL retain its original positive assertions and SHALL execute on Windows. Its Unsupported failure SHALL remain an actual visible failed test until separately repaired.
4. There SHALL be no warning allow/expect, artificial read, constructor/Default, dependency, permission, authority or adapter-enablement change. Error display names and IPC formatting SHALL remain unchanged.

### FR-3: Strict warning evidence on the exact source
**优先级:** Must
**用户故事:** As a reviewer I need the warning fix proved by native compiler evidence.
### 验收标准（EARS）
1. The native Windows baseline SHALL be immutable6edd4e6137a6947319183b3ac8801bfa608ac722 with the exact two source blobs. Its strict compile SHALL identify exactly the four named diagnostics and their source locations; dependency/setup errors or arbitrary nonzero exits SHALL fail the witness.
2. The exact candidate SHALL pass cargo rustc --locked --lib --manifest-path src-tauri/Cargo.toml -- -D warnings on Windows2025 and Ubuntu24.04, plus cargo fmt --all --check and locked all-target cargo check.
3. Native source/tree, commands, toolchain, exit status, diagnostic/raw logs and artifact identity SHALL be retained. Local syntax or parser checks SHALL NOT be represented as native compilation.

### FR-4: Regression and bounded publication
**优先级:** Must
**用户故事:** As a maintainer I need warning acceptance distinguished from incomplete product features.
### 验收标准（EARS）
1. Actual Linux full existing desktop regressions SHALL run with positive inventory/result counts. Existing Linux lock/Busy, metadata, recovery and restore tests SHALL remain enabled.
2. Actual Windows full existing desktop regressions SHALL run unchanged and retain real failures; expected failure counts SHALL NOT convert that job into success.
3. Warning-only acceptance SHALL be reported separately from Windows runtime, snapshot functionality, aggregate RC, physical-host and release gates.
4. Before publication, exact candidate review, fresh staged GitNexus analysis and gencommit SHALL be completed. Publication SHALL use a new nonforce bounded branch after exact source review; no release or held reference is authorized.

### FR-5: Preserve finite current and historical source admission
**优先级:** Must
**用户故事:** As a reviewer I need the warning repair admitted without weakening accepted source identities.
### 验收标准（EARS）
1. D SHALL have sole exact6edd parent; I SHALL have ordered[6edd,D]; J SHALL have ordered[existing R,I] and only four exact R document blobs. No correction chain, same-tree impostor or unbounded descendant SHALL pass.
2. Nine non-self files SHALL have frozen mode/blob/SHA256/size/line pins; an external reviewed manifest SHALL bind the profile itself. Historical constants, pins, assertions and complete inverse bytes SHALL remain exact.
3. Existing303 and452 IDs SHALL remain unchanged. Separate20 warning cases SHALL load by canonical module name, execute explicitly in the Ubuntu native job and reject skips, duplicate/missing/unknown IDs and failed results.
4. Workflow changes SHALL invert exactly to donor PR106: only branch,6edd baseline/tree, ten-path source scope and one delimited case step. All native gates SHALL still execute after preparation if that step fails.
5. Fresh exact D/I/J contexts SHALL pass303+452+20 without donor-only objects. Every changed candidate validation SHALL run fresh; mutable candidates SHALL NOT use cached acceptance.

## 非功能需求

Exactly ten paths are allowed: two production files, three specification files, .github/workflows/windows-snapshot-warning-scope.yml, scripts/rc_pretag_publication_profile.py, scripts/rc_pretag_publication_adapters.py, scripts/rc_pretag_join_once_tests.py and new scripts/rc_pretag_snapshot_warning_cases.py. Five replacements/five additions yield1698 entries. Aggregate added-plus-deleted cap1500; individual final/delta caps respectively342/12,313/1,90/90,110/110,90/90,420/420,500/180,300/140,497/60,480/480 in that order. No held PR98 ref/correction, snapshot implementation, AppImage, main, tag, release, credentials or security-setting changes.

## 依赖关系

Existing desktop Cargo dependencies and unchanged native tests. Native CI may reuse existing pinned checkout/Rust and Linux prerequisites after finite workflow approval. No product-binary build is added or duplicated.

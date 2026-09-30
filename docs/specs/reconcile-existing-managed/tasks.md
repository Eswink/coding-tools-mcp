# Tasks: managed worktree reconciliation

## 交付物清单
20 changed/new files relative to cumulative tree22c8c5e: three specs, Cargo.toml/lock, harness/mod.rs, eight worktree modules, tools/mod.rs, tools/dispatch.rs, tools/registry.rs, native chat scope mapping and two worktree tool modules. Every new Rust module is below500lines.

## 任务列表
- [x] 1.1 Reconcile candidate and preserve existing manager safety assertions
  - 证据块: ee37b271 worktree.rs used deterministic storage, opaque IDs and dirty refusal but trusted roots after construction
  - Files: worktree.rs, worktree_tests.rs; budget500lines each
  - Requirements: FR-1, FR-2, FR-3, FR-4; Design: 技术方案
- [x] 1.2 Perform mandatory upstream impact before edited existing symbols
  - 证据块: all manager/runner impacts LOW; public dispatch HIGH and local scope mapping CRITICAL, reported and reviewed before changes
  - Files: actual impact receipts retained with validation evidence
  - Requirements: FR-5; Design: Test strategy
- [x] 2.1 Replace unsafe subprocesses with bounded isolated ODB engine
  - 证据块: old run_git inherited PATH/config and only killed its direct child; libgit2 worktree API would reopen ambient configuration, so it is not used
  - Files: worktree_git.rs, worktree_objects.rs, worktree_boundary.rs; each below500lines
  - Requirements: FR-2, FR-6; Design: 技术方案 and Resource limits
- [x] 2.2 Preserve ignored content, detached commits and retry safety
  - 证据块: pre-fix regressions reproduced ignored-file loss, NOT_FOUND on repeated removal and accepted replaced roots
  - Files: worktree.rs and security/lifecycle tests
  - Requirements: FR-3, FR-4; Design: 技术方案
- [x] 2.3 Connect exact native tools after existing approval and policy intercepts
  - 证据块: native required() lacked worktree scopes and dispatch had no worktree branch
  - Files: tools/worktree_tools.rs, its tests, module/registry/dispatch/native scope entries
  - Requirements: FR-4, FR-6; Design: Data model and interfaces
- [x] 2.4 Expose validated snapshot read target without inventing quiescence
  - 证据块: snapshot worker needs managed identity; existing mutex serializes only worktree calls and cannot prove execution drainage
  - Files: worktree_snapshot.rs; budget100lines
  - Requirements: FR-2, FR-6; Design: Managed selection and snapshot boundary
- [x] 3.1 Execute native Linux affected/security/public approval tests
  - 证据块: real native application36worktree tests and1registry test passed, noignored; corrected HOME/XDG fullsuite499passed6failed matching existing baseline463passed6failed plus36newpasses
  - Files: local test receipts; no product test removal or safety skip
  - Requirements: FR-1 through FR-6; Design: Test strategy
- [x] 2.5 Pin explicit native workspace registration against broker removal
  - 证据块: native selection creates a separate profile; unpinned removal could otherwise delete its active root
  - Files: worktree_native.rs and pinned-removal regression; budget150lines
  - Requirements: FR-2, FR-6; Design: Native registration pin
- [x] 2.6 Require actual exclusive source-root request admission
  - 证据块: combined native lane passes39worktree cases including active source writer, overlapping child writer and unscoped-helper rejection; final root dependency revision must be retested and hashed with delivery
  - Files: tools/worktree_tools.rs and tests, plus separately owned root_work dependency
  - Requirements: FR-2, FR-6; Design: Exclusive source-root admission
- [ ] 3.2 Obtain final review, Windows CI, cumulative integration and convergence
  - 证据块: Windows-only drive/UNC and junction tests cannot execute on this Linux host; full baseline has six existing sandbox/transport failures
  - Files: release evidence and final reviewed patch
  - Requirements: FR-5; Design: Risks and failure behavior

## 需求覆盖矩阵
FR-1:1.1,3.1; FR-2:1.1,2.1,2.4,3.1; FR-3:1.1,2.2,3.1; FR-4:1.1,2.2,2.3,3.1; FR-5:1.2,3.1,3.2; FR-6:2.1,2.3,2.4,3.1.

## 文件变更清单
Scope-lock above matches the20-file narrow diff. Existing source baseline and other workers' staged files are not part of this patch. No commits or external writes until parent review. detect_changes and gencommit are mandatory before any later commit. Unrun Windows gates remain open.

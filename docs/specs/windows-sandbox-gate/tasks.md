# Tasks: Windows sandbox gate

## 交付物清单
Add platform requirement model, native fixture executable/test harness, native CI and these specs. Existing runtime methods remain unchanged. Candidate source/test files each below500 lines. Full production Windows execution is a separate remaining portion of this same mandatory gate, never waived.

## 任务列表
- [ ]1.1 Define explicit platform requirement/readiness without authorization
  - 证据块: services/local-agent/src/lib.rs exports LinuxSandbox only under cfg(linux); process_tree_windows::spawn has JobObject only
  - Files: services/local-agent/src/isolation.rs <200; lib.rs module/export only
  - Requirements: FR-1, FR-5; Design: Architecture
- [ ]1.2 Build bounded native LPAC fixture harness without global ACL changes
  - 证据块: existing process_tree_windows.rs suspended JobObject startup and pty_windows STARTUPINFOEX
  - Files: test harness launcher split into <=400-line modules; Rust fixture <150
  - Requirements: FR-2, FR-3; Design: Architecture, Threat review
- [ ]1.3 Add real positive/negative kernel tests and exact-source CI
  - 证据块: no native Windows isolation suite exists; original Linux kernel suite services/local-agent/tests/linux_sandbox.rs
  - Files: Windows regression driver <200; workflow <160
  - Requirements: FR-4, FR-6; Design: Verification
- [ ]2.1 Review source changes and preserve all incomplete integrated gates
  - 证据块: full FR8 explicitly requires Windows sandbox and Hooks/worktrees/snapshot/deploy/packages
  - Files: requirements/design/tasks and validation receipt
  - Requirements: FR-5, FR-6; Design: Verification and rollback

## 需求覆盖矩阵
| Requirement | Design | Task |
|---|---|---|
| FR-1 | Architecture |1.1|
| FR-2 | Architecture |1.2|
| FR-3 | Threat review |1.2|
| FR-4 | Verification |1.3|
| FR-5 | Architecture |1.1,2.1|
| FR-6 | Verification |1.3,2.1|

## Remaining completion gates
Actual native result; production workspace permission lifecycle; arbitrary approved tool compatibility; PTY; common dispatch/desktop integration; exact-source installed package coverage. No checked box can substitute for those.

## 文件变更清单
Add isolation.rs(<200), fixture(<150), launcher modules(each<400), test driver(<200), native workflow(<160); lib.rs export only. No existing process launch symbol edits.

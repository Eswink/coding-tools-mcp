# Requirements: Windows sandbox gate

## 功能概述
Deliver the required ISSUE-027 Windows isolation boundary in the full Epic32/Issue81 release. Current bounded increment establishes an honest platform requirement model and actual LPAC/AppContainer fixture gate before permitting any production Windows command. No host-wide security changes, elevation, unsupported fallback, or release-completion claim. Existing Windows Job Objects provide process lifecycle only.

## 需求列表
### FR-1: Explicit fail-closed platform requirement
WHEN a host requests filesystem and network isolation THEN the runtime SHALL distinguish Linux Landlock, Windows LPAC candidate and unavailable enforcement; a candidate SHALL NOT authorize production execution.
### FR-2: Native kernel containment fixture
WHEN the Windows fixture is launched THEN it SHALL run with an actual AppContainer/LPAC token, no network capabilities, explicit inherited handles, bounded lifetime and Job Object ownership before resume; a missing primitive SHALL fail the gate.
### FR-3: Fixture-owned resources only
WHEN native test resources are prepared THEN all ACL changes SHALL be limited to newly created temporary fixture files/directories and private package identity; system drive, device, user profile and unrelated ACLs SHALL remain untouched.
### FR-4: Failure-first isolation assertions
WHEN the test executes THEN an unsandboxed control SHALL reproduce outside read/write and loopback access before the unchanged sandbox assertions deny them; approved workspace I/O SHALL succeed. Setup or zero-test failure SHALL NOT count as containment.
### FR-5: No authority regression
WHEN building the candidate THEN existing LocalAdmission, ExecPolicy, desktop/non-Linux SANDBOX_REQUIRED and no-replay boundaries SHALL remain unchanged; no model-selected workspace/capability/sandbox-disable fields SHALL be added.
### FR-6: Exact verification and remaining release work
WHEN reporting evidence THEN native Windows, Linux portable checks and never-run gates SHALL be distinct; full Windows production workspace preparation, tools and PTY integration SHALL remain blocking until independently implemented and verified. Hooks/worktrees/snapshots/deployment/full packages remain required.

## 非功能需求
Files below500 lines; bounded metadata and redacted errors; no credentials or arbitrary command arguments logged. Cleanup must kill owned child before revoking fixture grants. Graph limitations retained. Kernel compromise, administrator compromise and physical workstation observations are not claimed covered.

## 依赖关系
LocalAdmission, ExecPolicy, ProcessManager, native Windows APIs and exact CI source. Hooks and full release depend on this complete gate.

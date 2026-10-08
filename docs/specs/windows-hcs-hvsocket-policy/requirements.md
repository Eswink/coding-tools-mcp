# 需求文档：windows-hcs-hvsocket-policy
## 功能概述
One HIGH-risk supplemental canary-only HvSocket policy experiment on standard windows-2025 Actions.
Base a67ba38a4dd1f82aa3c6f0d8cfcc376b8d2d4342, with existing source-specific runtime and surface proofs retained separately.
## 范围边界
The user approved Windows guest-local IPC and bounded VM-local HvSocket descriptor/canary experiments on 2026-10-08.
The proposed Windows boundary forbids external traffic and unapproved host services; Linux keeps its original socket denial.
No production admission, real workspace, copyback, snapshot, user machine or existing host-service probes.
No NIC/HNS/DNS/internet connection, registry registration, firewall/WFP/Defender/feature/service changes.
Only fresh private GUID canaries and this test's existing intrinsic GCS/stdio channels may be addressed.
## 历史经验与坑
No-NIC permits guest sockets. HvSocket descriptors authorize host bind/connect, not guest outbound allocation.
Disabled=true cancels established connections; this experiment uses descriptor updates with Disabled=false.
Descriptor changes might leave previously bound listeners reachable. Such a result fails the candidate.
## 术语定义
Seal: completion of every requested descriptor update before starting any fixed post-seal payload.
Canary: a fresh random private service GUID owned solely by this experiment, carrying a synthetic nonce.
## 需求列表
### FR-1: Fixed default-deny creation document
Priority: Must. As a reviewer, I need the exact HCS creation policy recorded.
WHEN preparing THEN verify the official shim SHA and dependency locks, apply exactly the reviewed default-bind/default-connect patch, and verify its postimage hash.
WHEN creating THEN allow only GCS, the six initial stdio service IDs, and three fresh canary service IDs; keep no NIC or optional host surface.
### FR-2: Positive controls and effective denial
Priority: Must. As a reviewer, I need successful canaries before interpreting connection failures.
WHEN running trusted setup THEN exact-VM, wildcard and children listeners SHALL exchange a <=64-byte nonce with the guest through Parent routing.
WHEN sealing THEN all ten admitted service entries SHALL become deny-bind/deny-connect, wildcard=false, Disabled=false, and each HCS completion SHALL be checked.
WHEN checking THEN fresh guest connections to still-bound canaries SHALL be denied and fresh exact-VM binds to denied and unlisted services SHALL return access denied.
IF a positive control, descriptor update, checked close or denial is missing THEN the candidate SHALL fail and preserve its errors.
### FR-3: Existing channel and runtime continuity
Priority: Must. As a maintainer, I need useful stock execution after restricting new channels.
WHEN sealing completes THEN the same persistent supervisor stdin/stdout/stderr and GCS lifecycle connection SHALL remain useful.
WHEN post-seal execution runs THEN fixed cmd, WindowsPowerShell, Node and pwsh commands SHALL perform their synthetic file checks and exit23; a live child SHALL be observed.
No post-seal HCS CreateProcess or arbitrary command/path input is accepted.
### FR-4: Bounded ownership and honest evidence
Priority: Must. As a reviewer, I need owned resource completion independent of test expectations.
WHEN exiting THEN retained UVM Terminate/Wait/ExitError/Close checks SHALL stay independent and sticky; all owned listeners/connections SHALL be closed and joined.
All three network_denial_proven/workspace_integration/production_admission flags SHALL remain false regardless of matrix results.
## 非功能需求
Twelve source paths: five new Go files <=1050 total and <=500 each; four existing files; three specs <=240 total.
New Go caps: policy_host300, policy_session190, policy_shared220, policy_guest190, policy_test150.
The existing driver stays <=440 lines, fixture<=85, prepare<=145, workflow<=100. Fixed 30-minute CI bound; one VM per candidate.
## 依赖关系
Pinned hcsshim/image/runtime inputs and approved process-only import privileges unchanged.
Parent-route matrix on this build does not prove other aliases, registered endpoints, all hosts or production safety.

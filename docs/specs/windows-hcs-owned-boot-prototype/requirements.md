# 需求文档：windows-hcs-owned-boot-prototype
## 功能概述
One bounded Windows Server Core Hyper-V utility VM experiment on standard windows-2025 Actions.
Observe stock runtime entry and whole-VM termination with synthetic files, before any desktop integration.
## 范围边界
Eight additions only, based on 3481de620b5816a94568652093637b28a305d2c8 (parent39a9ae7e).
Approved scope: ephemeral CI VM, private image import with process-local Backup/Restore privileges, Microsoft container EULA.
Only intrinsic read-only OS shares, private scratch VHDs and HCS guest-control/stdio are permitted.
No host service/feature/security/network changes, HNS/NIC, optional host mappings, user data, credentials, copyback or image redistribution.
Production Windows admission, original network tests, root identity and held snapshot work remain unchanged.
## 历史经验与坑
LPAC initialization and descendant-accounting failures remain unresolved for the existing backend.
Feature presence is insufficient; run37714189441 observed prerequisites but did not boot a VM.
hcsshim CloseCtx suppresses termination/wait failures; it cannot establish completion.
## 术语定义
Owned UVM: fresh random ID plus retained instance from the successful create operation, never an adopted system.
Uncertain: any failed/timed-out lifecycle or I/O observation; cannot be promoted by later success.
## 需求列表
### FR-1: Pinned finite preparation
Priority: Must. As a reviewer, I need fixed public inputs and no hidden host configuration.
WHEN preparing THEN verify the committed hcsshim SHA/vendor locks, fixed MCR layer sizes/hashes and fresh private paths.
WHEN importing THEN only the short-lived import process SHALL enable Backup/Restore and explicitly disable them before exit.
IF preflight, build or pure tests fail THEN import and VM creation SHALL not occur.
### FR-2: Stock runtime experiment
Priority: Must. As a maintainer, I need actual entry, output, file access and exit-code observations.
WHEN the UVM boots THEN one guest container SHALL have nil network, mounts, devices, credentials and annotations.
WHEN bootstrapping THEN fixed public Node/pwsh distribution bytes SHALL enter through HCS stdin, not host mounts.
WHEN each cmd, WindowsPowerShell, Node and pwsh case runs THEN its unique marker, synthetic read/write and exit23 SHALL be checked.
### FR-3: Whole-instance lifetime fence
Priority: Must. As a maintainer, I need completion beyond parent process exit.
WHEN a synthetic parent leaves a child alive THEN a separate guest check SHALL verify the child remains alive.
WHEN finishing or failing after creation THEN terminate the retained UVM and independently wait for its exit with bounded contexts.
IF any operation, exit, I/O or close fails THEN preserve that failure and all owned data; never infer safety from CloseCtx or process census.
### FR-4: Honest source-bound evidence
Priority: Must. As a reviewer, I need exact source, runner, image, runtime and lifecycle evidence.
WHEN reporting THEN always keep network_denial_proven=false, workspace_integration=false and production_admission=false.
WHEN uploading THEN only the explicit bounded JSON/log evidence list SHALL be uploaded, never disks, images or runtime binaries.
## 非功能需求
Functional caps: workflow100, preparation180, driver420, tests180, fixture100 lines; three specs80 each (total1220).
One job, one UVM, no automatic rerun; job timeout30 minutes; bounded I/O64KiB per stream.
No new dependency resolver: GOTOOLCHAIN=local, GOPROXY=off, GOSUMDB=off and -mod=vendor.
## 依赖关系
hcsshim v0.14.1 fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd; existing Actions Go/Node/pwsh.
ServerCore amd64 sha256:22505496dd4229dba63453ba0c6dc31c06fd3e11810e5b8e429aa6b16dab2457, OS10.0.26100.33438.
GitHub nested virtualization remains experimental; a failed boot is useful evidence, not permission to reconfigure the runner.

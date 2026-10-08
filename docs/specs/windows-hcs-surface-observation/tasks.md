# 任务清单：windows-hcs-surface-observation
## 概述
One source-bound supplemental candidate; no existing production isolation or workspace contract changes.
## 交付物清单（Scope-lock）
Six new files, four modified files; ten paths total, approximately15 fixture-only functions.
1. scripts/windows_hcs_boot/surface_guest.go new<=202
2. scripts/windows_hcs_boot/surface_host.go new<=192
3. scripts/windows_hcs_boot/surface_test.go new<=166
4. scripts/windows_hcs_boot/fixture.go modified<=80
5. scripts/windows_hcs_boot/prototype.go modified<=420
6. scripts/windows_hcs_boot/prepare.ps1 modified<=110
7. .github/workflows/windows-hcs-boot-prototype.yml modified<=100
8. docs/specs/windows-hcs-surface-observation/requirements.md new<=80
9. docs/specs/windows-hcs-surface-observation/design.md new<=80
10. docs/specs/windows-hcs-surface-observation/tasks.md new<=80
## 任务列表
- [x] Audit current contract and primary socket/root APIs before implementation
  - Evidence: services/local-agent/src/sandbox/filter.rs:49 denies SYS_socket; dispatch/tests.rs:113 requires PermissionError; Go os.Root documents held Windows directory handle
  - Files: three specs<=240; Requirements FR-1..FR-4; Design 来源/设计决策
- [ ] Implement fixed guest allocations and three closed local-peer nonce exchanges
  - Evidence: pinned hcsshim WCOW uses HvSocket independently of OCI Network; no-NIC is not socket denial
  - Files: guest<=202, fixture<=80; Requirements FR-1/FR-4; Design 技术方案
- [ ] Bind one synthetic input/output to held fixture identities and whole-VM exit
  - Evidence: existing prototype.go calls complete only after retained UVM Terminate/Wait; production RootIdentity stays unchanged
  - Files: host<=192, driver<=420; Requirements FR-2/FR-4; Design 数据模型/API设计
- [ ] Test Root rename/traversal and failed transfer/completion without privileged work
  - Evidence: run37719559925 includes19 passing preboot tests; os.Root available in actual Go1.24.13
  - Files: tests<=166, preparation<=110; Requirements FR-3; Design 测试策略
- [ ] Review finite source, staged impact and gencommit before isolated branch publication
  - Evidence: new-only fixture symbols cannot become production admission; no RootIdentity/core/snapshot path in allowed list
  - Files: same ten paths, workflow<=100; Requirements FR-1..FR-4; Design 文件结构/风险评估
- [ ] Verify one actual candidate and preserve independent observations
  - Evidence: exact source/tree/run/image plus artifact hashes and every API observation must be available
  - Files: no extra repository paths; Requirements FR-1..FR-4; Design 数据模型/测试策略
## 验收标准
All preboot tests precede image import. No host socket connection, network settings or user workspace operation occurs.
Six allocation and three guest-only peer results retain failures/unavailability without global denial conclusions.
Quarantine remains empty on identity/hash/nonce/completion failure and is never a real copyback target.
Existing four stock runtimes, live-descendant and whole-UVM exit evidence remain mandatory.
## 需求覆盖矩阵
FR-1: guest observations/tasks1/2/6. FR-2: synthetic rooted transfer/tasks1/3/6.
FR-3: failure and root tests/tasks1/4/5. FR-4: unchanged claims/source binding/tasks2/3/5/6.
## 文件变更清单
Exactly the ten Scope-lock paths; no module locks, production source, core RootIdentity or held snapshot files.
## 回滚
Keep separate branch unmerged or ordinary revert; never retry an unexplained failure or turn an observation into policy relaxation.

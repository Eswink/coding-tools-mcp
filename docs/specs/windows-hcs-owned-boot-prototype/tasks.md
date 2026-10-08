# 任务清单：windows-hcs-owned-boot-prototype
## 概述
One bounded CI experiment; implementation does not alter the Windows production rejection.
## 交付物清单（Scope-lock）
Eight additions, zero existing-file modifications; approximately18 new functions, no production call sites.
1. .github/workflows/windows-hcs-boot-prototype.yml <=100 lines
2. scripts/windows_hcs_boot/prepare.ps1 <=180
3. scripts/windows_hcs_boot/prototype.go <=420
4. scripts/windows_hcs_boot/prototype_test.go <=180
5. scripts/windows_hcs_boot/fixture.go <=100
6. docs/specs/windows-hcs-owned-boot-prototype/requirements.md <=80
7. docs/specs/windows-hcs-owned-boot-prototype/design.md <=80
8. docs/specs/windows-hcs-owned-boot-prototype/tasks.md <=80
## 任务列表
- [x] Read exact upstream constructors, imports, network defaults and lifecycle behavior
  - Evidence: hcsshim internal/uvm/create.go CloseCtx discards Terminate/Wait errors; internal/hcsoci/create.go configures network only when Windows.Network is nonnil
  - Files: three specs <=240 lines; Requirements FR-1..FR-4; Design 技术方案/风险评估
- [ ] Build pinned-input preparation and source-bound workflow without hidden remediation
  - Evidence: pkg/ociwclayer/import.go:42 requires backup/restore; test/internal/layers/lazy.go uses Add-MpPreference and is forbidden here
  - Files: prepare.ps1<=180, workflow<=100; Requirements FR-1/FR-4; Design 技术方案/数据模型
- [ ] Implement owned UVM, stock runtime cases and sticky completion fence
  - Evidence: internal/uvm/wait.go WaitCtx delegates retained hcsSystem.WaitCtx; create_wcow.go sets readonly OS VSMB and private scratch
  - Files: prototype.go<=420, fixture.go<=100; Requirements FR-2/FR-3; Design 技术方案/API设计
- [ ] Test fixed options, negative completion paths and evidence boundaries before import
  - Evidence: existing capability probe has eight synthetic tests before reads; this follows the same fail-before-action ordering
  - Files: prototype_test.go<=180; Requirements FR-1..FR-4; Design 测试策略
- [ ] Review exact source/hash, run staged impact and gencommit, then publish dedicated nonforce branch
  - Evidence: GitNexus new symbols are not indexed; UNKNOWN requires manual HIGH-risk review rather than a zero-impact claim
  - Files: same eight paths; Requirements FR-1..FR-4; Design 文件结构/风险评估
- [ ] Monitor one actual run and verify finite artifact before drawing conclusions
  - Evidence: run37714189441 proves prerequisite reads only; this experiment must supply actual boot/runtime/lifetime evidence
  - Files: no extra repository paths; Requirements FR-2..FR-4; Design 数据模型/测试策略
## 验收标准
No import or boot before pure tests/build and root source review; exactly one owned UVM attempt.
All four actual runtime cases and child-live observation are required for runtime compatibility evidence.
Whole-UVM wait and errors are explicit; no uncertainty becomes success and no data cleanup hides it.
Network/workspace/production flags remain false and original contract tests remain unchanged.
## 需求覆盖矩阵
FR-1: preparation/tests/workflow, tasks1/2/4/5.
FR-2: guest cases and runtime bootstrap, tasks1/3/6.
FR-3: retained-instance termination, descendant fixture and negative tests, tasks1/3/4/6.
FR-4: source-bound fixed artifact and independent review, tasks2/4/5/6.
## 文件变更清单
Exactly eight Scope-lock additions; no package locks, production settings, source or existing workflow edits.
## 回滚
Leave dedicated branch unmerged; do not repeat a failed experiment automatically or clean uncertain resources.

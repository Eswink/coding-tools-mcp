# 任务清单：windows-hcs-capability-probe
## 概述
Build one finite observer, not an execution backend or a release gate.
## 交付物清单（Scope-lock）
Six new files, zero modified files. Three functional files total <=540 lines, three specs <=80 each.
1. scripts/windows_hcs_capability_probe.ps1 (280)
2. scripts/windows_hcs_capability_probe_tests.ps1 (160)
3. .github/workflows/windows-hcs-capability-probe.yml (100)
4. docs/specs/windows-hcs-capability-probe/requirements.md (80)
5. docs/specs/windows-hcs-capability-probe/design.md (80)
6. docs/specs/windows-hcs-capability-probe/tasks.md (80)
## 任务列表
- [x] Read exact source, primary API contracts and coordinate isolated branch baseline
  - Evidence: src-tauri/src/tools/cloud_host.rs:207 rejects non-Linux exec.run with SANDBOX_REQUIRED; this remains unchanged
  - Files: three specs only; total <=240 lines
  - Requirements: FR-1, FR-2, FR-3; Design: 概述/来源
- [ ] Implement fixed read-only observations and negative reporting
  - Evidence: Microsoft HcsGetServiceProperties accepts PropertyTypes Basic; WHvGetCapability reads capabilities without creating a partition
  - Files: probe <=280 lines; new functions have no preexisting call sites
  - Requirements: FR-1, FR-2; Design: 技术方案/数据模型
- [ ] Add eight fixed synthetic tests and dedicated source-bound workflow
  - Evidence: existing Windows CI uses pwsh; only the dedicated branch may invoke this observer
  - Files: tests <=160, workflow <=100; no existing workflow changes
  - Requirements: FR-3; Design: 测试策略
- [ ] Review source, detect staged changes, generate commit and publish isolated branch
  - Evidence: exact source diff must contain only the six additions; production and held PR98 stay unchanged
  - Files: same six paths only
  - Requirements: FR-1, FR-2, FR-3; Design: 文件结构/风险评估
- [ ] Observe actual Actions outcome and verify downloaded evidence
  - Evidence: source/tree/run/attempt/image and eight test IDs must bind to the measured run
  - Files: no new repository paths
  - Requirements: FR-2, FR-3; Design: 数据模型/测试策略
## 验收标准
All eight tests execute exactly once before native observations; no skipped test becomes a pass.
Actual missing capabilities or read failures remain visible and block further execution claims.
No feature/service/network settings or VM/container state is changed by this probe.
## 需求覆盖矩阵
FR-1: fixed probe/native reads, tasks1/2/4; synthetic and source-review evidence.
FR-2: raw failures/blocker labels/untested conclusions, tasks2/5; negative synthetic cases and actual observation.
FR-3: eight tests and source binding, tasks3/4/5; test inventory and source-bound artifact.
## 文件变更清单
Exactly the six additions listed in Scope-lock; every baseline path remains byte-identical.
## 回滚
Leave the isolated branch unmerged or apply an ordinary revert; never rerun a negative result automatically.

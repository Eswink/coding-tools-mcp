# 任务清单：windows-cmd-open-observation

## 概述

One finite diagnostic feature linked to the unresolved cmd batch bug. No task here closes that bug or expands access.

## 交付物清单（Scope-lock）

- Expected file count:13
- Expected task count:7
- No publication or native attempt before exact-candidate review

## 任务列表

- [x]1.1 Freeze requirements/design and pass check_spec before source
  - 证据块: PilotRunner.cs:54-160; QualificationCleanup.cs:10-52; DirectHandles.cs:15-25; exact source-bound graph context/impact
  - Files: the three spec files, each<=500lines
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6_ · _设计: entire frozen contract_
- [x]2.1 Implement typed native adapter, aligned AMD64 layouts and bounded PE parser,<=500lines
  - 证据块: DirectNative.cs; DirectHandles.cs; official sources in design.md
  - File: CmdDebugNative.cs
  - _需求: FR-1, FR-2_ · _设计: native allowlist, exact ABI, module readiness_
- [x]2.2 Implement fixed one-shot state and retained cleanup gate,<=500lines
  - 证据块: PilotRunner.cs:107-149; QualificationCleanup.cs:10-52
  - File: CmdDebugSession.cs
  - _需求: FR-2, FR-3, FR-4, FR-5_ · _设计: state and cleanup transition tables_
- [x]2.3 Insert selected-case observer and pre-classifier gate while preserving both pinned boundaries
  - 证据块: cmd-observations-audit.py:40-51; workflow:75-90; run-pilot.ps1:27
  - Files: Runner, both Add-Type sites, existing two source audits and the AppLocker44-file aggregate hash check
  - _需求: FR-1, FR-4, FR-5, FR-6_ · _设计: selected-case integration_
- [x]3.1 Implement and run fake-native ABI/lifecycle fault tests and Python receipt/source adversaries
  - 证据块: design.md exact ABI/state/cleanup/receipt contract and current PilotCmdObservationsTests.cs
  - Files: CmdDebugContractTests.cs and audit.py, each<=500lines
  - Acceptance: all finite verification cases in design.md, including wrong MOV delta, denial, pending, uncertain continue, foreign return, target-close mutation, unchanged-catch leak and perturbation before journal
  - _需求: FR-2, FR-3, FR-4, FR-5, FR-6_ · _设计: finite verification_
- [x]3.2 Run all affected existing audits/regressions and measure results without inventing skipped passes
  - 证据块: current workflow audit commands and repository test instructions
  - _需求: FR-6_ · _设计: finite verification_
- [x]3.3 Independently review exact diff and staged graph/source scope before gencommit/publication decision
  - 证据块: exact candidate diff, graph impact evidence, and immutable source audit pins
  - Acceptance:13paths, all immutable spans, no extra native API or security authority; report unavailable compiler/native tests explicitly
  - _需求: FR-1, FR-6_ · _设计: implementation envelope_

## 检查点

- [ ] Specification checked before implementation
- [ ] Source and fake-native tests match frozen ABI/state contract
- [ ] Applicable regressions and exact-candidate review complete
- [ ] Separate parent decision precedes publication and one native attempt

## 需求覆盖矩阵

| Requirement | Design sections | Tasks | Status |
| --- | --- | --- | --- |
| FR-1 | target/readiness/integration |1.1,2.1,2.3,3.3|pending|
| FR-2 | API/ABI/open pairing |1.1,2.1,2.2,3.1|pending|
| FR-3 | step transitions |1.1,2.2,3.1|pending|
| FR-4 | cleanup gate |1.1,2.2,2.3,3.1|pending|
| FR-5 | receipt/perturbation |1.1,2.2,2.3,3.1|pending|
| FR-6 | integration/verification |1.1,2.3,3.1,3.2,3.3|pending|

## 文件变更清单

| File | Operation | Line ceiling | Purpose |
| --- | --- | --- | --- |
|tests/windows-broker-direct/PilotRunner.cs|modify|350|bounded diagnostic delivery|
|tests/windows-broker-direct/run-pilot.ps1|modify|150|bounded diagnostic delivery|
|tests/windows-broker-direct/pilot-audit.py|modify|450|bounded diagnostic delivery|
|tests/windows-broker-direct/cmd-observations-audit.py|modify|450|bounded diagnostic delivery|
|.github/workflows/windows-lpac-runtime-diagnostic.yml|modify|500|bounded diagnostic delivery|
|tests/windows-applocker-observation/audit.py|modify|500|two reviewed aggregate hashes only; unchanged330 test identities|
|tests/windows-cmd-debugger-observation/CmdDebugNative.cs|new|500|bounded diagnostic delivery|
|tests/windows-cmd-debugger-observation/CmdDebugSession.cs|new|500|bounded diagnostic delivery|
|tests/windows-cmd-debugger-observation/CmdDebugContractTests.cs|new|500|bounded diagnostic delivery|
|tests/windows-cmd-debugger-observation/audit.py|new|500|bounded diagnostic delivery|
|docs/specs/windows-cmd-open-observation/requirements.md|new|200|bounded diagnostic delivery|
|docs/specs/windows-cmd-open-observation/design.md|new|500|bounded diagnostic delivery|
|docs/specs/windows-cmd-open-observation/tasks.md|new|200|bounded diagnostic delivery|

## 交付前自检

- [ ] Every task maps to FR and actual evidence
- [ ] No placeholder implementation or weakened audit
- [ ] File inventory equals scope lock; each new code file<=500 readable lines
- [ ] Root-cause and runtime feasibility remain honestly separate from synthetic validation

## Authenticated v1 outcome

Published49edb3d3/tree10f01917 passed all372 Python methods, both PowerShell synthetic suites and managed compilation/contracts before run37188532811. The single observer attached but ended incomplete at immediate context verification; no paired target-open result exists. Termination/individual cleanup were confirmed, while case/run recovery journals remained retained. This closes the v1 experiment as inconclusive and does not complete the original batch root-cause goal.

## Finite v2 revision tasks (FR-7)

- [x]4.1 Record exact published baseline, approved15-path helper scope, fresh symbol impact and checked specification
  - Evidence: reason-preimpact.json; root scope review; unchanged source-bound graph file hashes
- [x]4.2 Add pure mask and immediate Set/Get reason split; extract strict schema and isolated fake-test helper
  - Evidence: SameRequested:Native.cs48; SetContext:Session.cs216; check_receipt:audit.py90; GetContext/SetContext:ContractTests.cs172
  - Files: Native,Session,ContractTests,ContextTests(new),audit,receipt_contract(new),workflow,three specs
- [ ]4.3 Run retained Python regressions, new schema/source negatives, C# syntax check; report unexecuted managed tests honestly
  - Evidence: exact commands/results and immutable archivedv1 validation
- [ ]4.4 Freeze exact candidate, staged GitNexus, independent review and gencommit before publication decision
  - Evidence: candidate diff/tree; review; no new native experiment unless separately approved

Additional scope rows: tests/windows-cmd-debugger-observation/CmdDebugContextTests.cs (new,<=500lines); tests/windows-cmd-debugger-observation/receipt_contract.py (new,<=500lines). The workflow test list gains the C#helper; run-pilot and AppLocker audit are unchanged in this increment. The earlier13-path inventory is the historical v1 increment, not a claim that the cumulative v2 inventory is13.

## Finite v3 XOR revision tasks (FR-8)

- [x]5.1 Record published888 baseline, source-only design approval,16-path helper scope and checked specification
  - Evidence: xor-preimpact.json and xor-preimpact-graph-binding.json; independent reviewer constraints
- [x]5.2 Emit unsigned same-buffer XOR in Session and separate strict v3 schema; extract pure receipt tests preserving actual IDs
  - Evidence: Session217-224; Native45-64; audit fixture/encoded/ContextReceiptContracts; receipt_contract check_context_roundtrip
  - Files: Session, two existing C#tests, audit, receipt_contract, receipt_tests(new), three specs
- [ ]5.3 Run all32-bit, availability, contradiction and first-failure tests; retained regressions and v1/v2 differential checks
  - Evidence: actual commands/results, old/new test inventory and archived digest equality
- [ ]5.4 Freeze exact source/tree, staged graph and independent review before any publication/native decision
  - Evidence: exact candidate and unavailable-stage disclosure; no normalization or extra experiment

Additional scope row: tests/windows-cmd-debugger-observation/receipt_tests.py (new,<=500lines), pure receipt fixtures and versioned unit tests only. Native/workflow/runtime wrappers/AppLocker remain unchanged in this increment. The published v2 attempt ended incomplete with field mask8; it established no flag whitelist or batch root cause.

## CI path-filter correction (FR-9)

- [x]6.1 Bind published54af source and verify the omitted observer path plus exact guard impact
  - Evidence: workflow lines2-10, trigger-preimpact.json and source-bound graph hashes
- [x]6.2 Add only the exact observer push path, a focused audit regression and updated scope requirements
  - Files: workflow, audit.py and existing three specs; no runtime/C# changes
- [ ]6.3 Run retained regressions and path mutations, then independently review exact diff/tree before publication
  - Evidence: commands/results, path-only preservation proof and staged graph

No v3 runtime observation occurred at54af. The pending experiment is not an old-run retry; the reviewed integration correction must first reach the unchanged test gates.

## v4 architectural comparison correction (FR-10)

- [x]7.1 Bind publishedbf baseline, primary-source rationale, approved17-path design and exact call-site impact
  - Evidence: v4-reserved-bit1-proposal.json, v4-preimpact.json and v4-preimpact-graph-binding.json
- [x]7.2 Add the separate exact(0,0)/(8,2) state predicate at only the two named runtime comparisons
  - Evidence: Native raw helpers/WithRipTf/marshaling and Session immediate Set/Get; raw requests and fake setter freshness preserved
- [x]7.3 Add strict v4 receipt rules and complete all-bit/direction/combination/error tests; extract guard data without inventory loss
  - Evidence: evaluated ordered guards, actual old test IDs, v1-v3 behavior/archive preservation and raw/latest-immediate semantics
- [ ]7.4 Run retained/local contracts, refresh staged graph and independently review the exact candidate before publication/native decision
  - Evidence: measured commands, explicit local compiler limitation and exact source/tree proof

Additional scope row: tests/windows-cmd-debugger-observation/source_guards.py (new,<=500lines), data-only fixed guard inventory. No runtime helper or workflow change. Original batch exit1 remains unexplained until valid target-open evidence supports a cause-directed conclusion.

V4 local validation: all362 retained Python methods and37 observer methods pass; 9,401 legacy differential calls have zero differences and all three archived interpretations/hashes are preserved. The four C# files pass syntax-only parsing; managed compilation and PowerShell execution are unavailable locally and remain Windows CI gates. Exact candidate review and any publication/native decision remain separate.

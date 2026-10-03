# 任务清单：windows-applocker-script-observation

## 概述

Preparation is authorized; implementation requires root's exact packet review and any required HIGH/CRITICAL warning. Baseline859/tree4234 remains intact. A diagnostic observation can finish inconclusive; no successful policy event or green original aggregate is assumed.

## 交付物清单（Scope-lock）

- New code files:6, all in tests/windows-applocker-observation
- Existing modified paths:2 (diagnostic workflow and broker-direct README)
- New specification files:3; total prospective paths11
- Proposed new implementation functions:17 (seven PowerShell, seven pure Python, three fixed-read driver functions), plus32 Python unittest methods and16 named PS synthetic scenarios
- Existing implementation functions modified:0
- Existing330 portable test identities and seven managed entrypoints remain unchanged

## 任务列表

### 阶段 1: 准备工作

- [x] 1.1 Resume the converged explicit-relative Plan, verify no resumable Plan at the fresh exact859 root, and establish a bounded new Plan
  - **证据块:** AGENTS.md:5 requires resume_plan first; the old Plan reports converged and new-root resume reports found=false
  - **涉及文件:** Preparation evidence only, no source implementation
  - _需求: FR-5_ | _设计: 概述, 风险评估_
- [x] 1.2 Verify primary event fields and service-side filter feasibility without executing a log query
  - **证据块:** Microsoft AaronLocker selects Event/UserData/RuleAndFileData/TargetProcessId and FilePath; EvtQueryTolerateQueryErrors can discard a malformed suffix
  - **涉及文件:** requirements/design specifications, each below500lines
  - _需求: FR-2, FR-3, FR-5_ | _设计: Exact identity and query, Primary sources and interpretation_
- [x] 1.3 Define exact11-path scope, failure tests and immutable-source graph proof
  - **证据块:** PilotRunner.cs:237 `journal.Resolve();` is the final required fallible pilot action; cmd-observations-audit.py:212 inventories the old top-level executable files
  - **涉及文件:** Three specifications, each below500lines; external evidence/graph files
  - _需求: FR-1, FR-4, FR-5_ | _设计: 文件结构, 风险评估_
- [x] 1.4 Pass check_spec and root pre-edit review with exact packet hashes and HIGH/CRITICAL disclosure
  - **证据块:** AGENTS.md requires pre-edit impact/warnings and check_spec before implementation
  - **涉及文件:** No implementation changes until disposition
  - _需求: FR-5_ | _设计: 风险评估_

### 阶段 2: 核心实现

- [x] 2.1 Implement strict pure target/bracket/query and reviewed-correlation contracts
  - **证据块:** cmd_observation_artifact.py:50 strict duplicate JSON handling; :409 parses all pilot JSON; :457 requires full validate_completion. New sibling bytes currently receive only manifest/hash verification
  - **涉及文件:** applocker_observation_contract.py <=450lines; audit.py <=480lines; extracted contract_fixtures.py <=220lines
  - _需求: FR-2, FR-4_ | _设计: 数据模型, Exact identity and query, API 设计_
- [x] 2.2 Implement the fixed bounded file-read driver with no arbitrary inputs
  - **证据块:** PilotRunner.cs:72 writes ownership-process.json after successful owned creation; PilotSubjects.cs:203 explicitly labels PID correlation only; existing Python3.12 setup is workflow lines21-24
  - **涉及文件:** prepare_query.py <=200lines; audit.py <=480lines
  - _需求: FR-2, FR-3_ | _设计: 技术方案, API 设计_
- [x] 2.3 Implement one local exact EventLogQuery and bounded raw observation persistence
  - **证据块:** Existing run-pilot.ps1:101 says terminal evidence preceded final journal rename and adds no writes; new outer observation must use sibling evidence only
  - **涉及文件:** observe.ps1 <=450lines; contract-tests.ps1 <=480lines
  - _需求: FR-1, FR-3_ | _设计: 技术方案, 数据模型_
- [x] 2.4 Add the guarded outer workflow bracket and new isolated contract entries
  - **证据块:** workflow:103 contains the single literal pilot call; old audits require that exact occurrence and forbid continue-on-error; manifest follows with always()
  - **涉及文件:** Existing workflow below500lines; README documentation
  - _需求: FR-1, FR-5_ | _设计: 技术方案, 文件结构_

### 阶段 3: 集成测试

Local execution: all330 retained identities and32 new methods pass; the new methods exercise327 expanded parameter variants, including78late failures and six contradictory completions. The approved summary persistence correction uses pending-write/flush/close then final no-overwrite rename; its new failure subcases remain under the32 existing test identities. The16 named PS5.1 synthetic scenarios are implemented but unexecuted locally; parsing, runtime assertions and actual event availability remain hosted pending. The approved final-run input cap is2MiB, with exact-limit/one-byte-over checks; all other input limits remain unchanged. Checkout-only transient core.autocrlf=false keeps raw source hashes aligned with Git blobs.


- [x] 3.1 Execute all retained330 Python identities plus32 new methods and verify no fixture becomes real event proof
  - **证据块:** Previous exact859 hosted run37102342565 executed old8entry counts20/46/30/57/34/33/81/29. Seven managed counts were521/35/140/166/219/555/6138
  - **涉及文件:** New audit.py and both Python modules within declared caps; no old audit edits
  - _需求: FR-2, FR-3, FR-4, FR-5_ | _设计: 测试策略_
- [ ] 3.2 Test every named late-failure/exception/exit/query/close boundary and independently review semantics
  - **证据块:** Existing78 late-failure variants and six contradictory completions already reject old acceptance; favorable sibling evidence cannot repair them
  - **涉及文件:** New tests within declared caps; read-only real859 artifact regression
  - _需求: FR-1, FR-4_ | _设计: 测试策略_
- [ ] 3.3 Refresh staged graph, validate source/caps/specs, run gencommit, and present exact staged tree/sole parent/message
  - **证据块:** AGENTS.md requires detect_changes before committing; new symbols have no pre-edit UID and need staged exact-symbol review
  - **涉及文件:** Exactly declared11paths; no remote mutation before candidate review
  - _需求: FR-5_ | _设计: 风险评估_
- [ ] 3.4 After exact publication approval, run existing Windows lane and independently verify actual artifact
  - **证据块:** Existing original foundation/nested/pilot failures stay expected observations, while actual observer availability is unknown before a new run
  - **涉及文件:** No extra implementation files; validate exact commit/tree/run/job/attempt/artifact, SHA256/CRC/manifest/member set and complete journals
  - _需求: FR-1, FR-3, FR-4, FR-5_ | _设计: 测试策略, Primary sources and interpretation_

## 检查点

- [x] Published baseline and current authoritative boundaries read
- [x] Schema/query and correlation limitations documented
- [x] Checked specifications and root exact pre-edit disposition
- [x] Local executed checks separated from hosted pending checks
- [ ] Exact staged candidate reviewed before publication
- [ ] Actual terminal run/artifact interpreted without laundering old failures

## 需求覆盖矩阵

| Requirement | Design | Tasks | Status |
|---|---|---|---|
|FR-1|技术方案, 数据模型|2.3,2.4,3.2,3.4|Preparation only|
|FR-2|Exact identity and query, API 设计|1.2,2.1,2.2,3.1|Preparation only|
|FR-3|技术方案, 数据模型|1.2,2.2,2.3,3.1,3.4|Preparation only|
|FR-4|API 设计, 设计决策|2.1,3.2,3.4|Preparation only|
|FR-5|风险评估, 测试策略|1.1,1.3,1.4,2.4,3.1,3.3,3.4|Preparation only|

## 文件变更清单

| Path | Operation | Budget |
|---|---|---|
|tests/windows-applocker-observation/observe.ps1|New|450|
|tests/windows-applocker-observation/contract-tests.ps1|New|480|
|tests/windows-applocker-observation/applocker_observation_contract.py|New|450|
|tests/windows-applocker-observation/prepare_query.py|New|200|
|tests/windows-applocker-observation/audit.py|New|480|
|tests/windows-applocker-observation/contract_fixtures.py|New extracted test-only helpers/literals|220|
|.github/workflows/windows-lpac-runtime-diagnostic.yml|Modify|Below500|
|tests/windows-broker-direct/README.md|Modify|Documentation|
|docs/specs/windows-applocker-script-observation/requirements.md|New|Below500|
|docs/specs/windows-applocker-script-observation/design.md|New|Below500|
|docs/specs/windows-applocker-script-observation/tasks.md|New|Below500|

## 检查清单

- [x] Scope and readable budgets named before implementation
- [x] Every task has source evidence and requirement/design linkage
- [x] All old executable/evaluator/security boundaries retained
- [x] No implementation or Windows/event/CI operation performed by this preparation
- [ ] Implementation, tests, review, publication and hosted work remain gated by exact review

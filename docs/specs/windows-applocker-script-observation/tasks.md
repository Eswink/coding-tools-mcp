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

## Published201 correction tasks (FR-2, FR-5)

Publication of the original eleven-path increment is verified:20128605b3ecb39257e86c20f215412653cb8132/tree6ee934230cb9975f9b3a9787ec51937a510e6524, Draft99. Run37110825877 failed only after330 retained tests passed:32 new methods/327 expanded variants reported two open-metadata errors and one inventory-order failure. All PowerShell/native/event stages were skipped. Artifact11268983773 is736bytes, SHA256ff12c8b40cf01a91d70df39d7e1d344daf51df8226904f4e2830204711f0536c, CRC and two manifest records verified; its three members contain no pilot observation. The feature Plan remains active.

- [x] C1 Resume the existing Plan and authenticate published201/source/artifact; record the real failing stage
  - **证据块:** run37110825877 step8; source.txt binds201/tree6ee; failure log identifies prepare_query.py:58 and audit.py:420, but contains no differing stat field values
  - **涉及文件:** External evidence only; new source checkout exact201
  - _需求: FR-5_ | _设计: Published201 portability correction_
- [x] C2 Reproduce Windows filename ordering and unlike timestamp comparisons without source edits
  - **证据块:** Exact raw-byte Windows ordering gives63118873; ordinal gives unchanged1509f8ae. Literal proxy creation100/change200 fails original reader; equal100 passes with one close
  - **涉及文件:** External proof and these three specification updates
  - _需求: FR-2, FR-5_ | _设计: Published201 portability correction_
- [x] C3 Complete fresh exact-UID impact, checked specifications and root pre-edit disposition
  - **证据块:** AGENTS.md requires upstream impacts before existing function edits; full exact201 graph and source/index hashes are required
  - **涉及文件:** Six exact correction paths in design; prepare_query200, audit480, new driver_contract_tests240, each spec500lines
  - _需求: FR-5_ | _设计: Published201 portability correction_
- [x] C4 Implement comparable metadata identities and independent test matrix/capture; preserve all old cases and guards
  - **证据块:** prepare_query.py:49-83 currently compares path creation ctime against descriptor metadata ctime; audit.py:418 uses platform-specific Path sorting
  - **涉及文件:** Only prepare_query.py, audit.py and new test-only driver_contract_tests.py within reviewed caps
  - _需求: FR-2, FR-5_ | _设计: Published201 portability correction_
- [x] C5 Execute focused then all portable checks; retain330+32 test identities and report actual expanded counts
  - **证据块:** Hosted32-method failure means local prior passes did not establish Windows portability; negative matrices must use independent literal values
  - **涉及文件:** Reviewed three Python files; old tests/runtime/workflow unchanged
  - _需求: FR-2, FR-5_ | _设计: Published201 portability correction_
- [ ] C6 Fresh staged graph/detect_changes/full review/gencommit and exact tree/sole201parent/message disposition
  - **证据块:** New helper has no pre-edit UID; staged callable/source validation and dynamic unittest coverage proof required
  - **涉及文件:** Exactly six correction paths; no publication until root candidate review
  - _需求: FR-5_ | _设计: Published201 portability correction_
- [ ] C7 Publish only reviewed candidate; verify actual Windows portable/PS/native/query stages and authenticated artifact
  - **证据块:** Prior run skipped PS/native/event query; no success or AppLocker availability may be inferred from local or synthetic checks
  - **涉及文件:** Existing diagnostic branch/PR/workflow, no workflow changes or skipped gates
  - _需求: FR-2, FR-5_ | _设计: Published201 portability correction_

Correction local results: all330 retained methods pass with unchanged identities; all32 observation methods pass with407 expanded variants. The increase from327 comprises70 independent metadata cases, seven bounded-capture self-tests, two path-flavor ordering cases and one new source-inventory cap case. The helper has204lines, driver133 and audit462. These are Linux execution and synthetic Windows metadata branches only. Actual Windows portable/PowerShell/native/event stages remain pending a reviewed candidate; no new real observation or original failure verdict is inferred.

## Published2dd harness correction tasks (FR-1, FR-5)

The portability correction is published and actually passed all362 Windows Python methods/407 variants in run37113307310. PS5.1 then failed after the normal-return scenario because script-scoped wrapper text and the compiled Wrapper variable alias under case-insensitive name resolution. Artifact11270481225 is737bytes, SHA2563c0b7e3a5c52479588be00c2716e281078fdb2348b256d05b79e36aff109db99; CRC, two manifest records and2dd/tree8cb3 binding verified. No real query or native execution occurred. The existing feature Plan remains active.

- [x] P1 Resume the existing Plan and preserve authenticated failed-stage evidence and exact2dd source
  - **证据块:** job111175227786 log reports ScriptBlock lacks Replace at contract-tests.ps1:365; published source269/277 establishes the same script-scope storage collision
  - **涉及文件:** External evidence and these three specifications only
  - _需求: FR-1, FR-5_ | _设计: Published2dd PowerShell harness correction_
- [x] P2 Complete fresh exact-source graph/rename-availability/manual reference proof, check_spec and root pre-edit review
  - **证据块:** AGENTS.md requires pre-edit impact and graph-aware rename; unsupported PS symbols require explicit limitation rather than fake graph proof
  - **涉及文件:** Exactly contract-tests.ps1<=480, audit.py<=480 and three existing specifications<=500; no new code file
  - _需求: FR-5_ | _设计: Published2dd PowerShell harness correction_
- [x] P3 Apply seven compiled-variable token edits, two type assertions and three Python source-mutation regressions
  - **证据块:** Compiled references occur at277/297/363/365/367/370/372; all twelve text references and the existing audit token can remain unchanged
  - **涉及文件:** Only the two reviewed test files; observer/runtime/workflow immutable
  - _需求: FR-1, FR-5_ | _设计: Published2dd PowerShell harness correction_
- [x] P4 Execute retained330 plus32 observation methods and prove all previous assertions/scenario/variant identities remain
  - **证据块:** Source enumeration retains16 names and95 wrapper variants; actual prior run completed only the normal-return name, so static counts are not a PS runtime pass
  - **涉及文件:** Existing test entries only, exact final candidate bytes
  - _需求: FR-1, FR-5_ | _设计: Published2dd PowerShell harness correction_
- [ ] P5 Complete staged graph/detect_changes/full review/gencommit and exact sole2ddparent candidate disposition
  - **证据块:** New nested Python checker needs exact current-definition review; PS dynamic scriptblock execution needs manual/source proof
  - **涉及文件:** Exactly five reviewed paths; no publication before disposition
  - _需求: FR-5_ | _设计: Published2dd PowerShell harness correction_
- [ ] P6 Publish reviewed candidate, verify actual Windows PS/compiler/managed/Rust/native stages and authenticated artifact
  - **证据块:** No local PS runtime is available; no gate may be skipped and no synthetic event may become real observation proof
  - **涉及文件:** Existing diagnostic branch/PR/workflow only, no new workflow or settings
  - _需求: FR-1, FR-5_ | _设计: Published2dd PowerShell harness correction_

Harness-correction local results: all330 retained and32 observation methods pass; the observation audit executes410 expanded variants, adding exactly three binding-source mutations. The source checker rejects the exact published aliasing source. Whole-file byte comparison proves only seven compiled-token changes and two type assertions in the477-line PS file; the479-line Python audit retains all previous assertion calls and identities. Independent review confirms all56 old PS assertion sites,16 scenario names,95 intended wrapper variants and four writer modes remain. These are local Python/source results; full PS5.1/runtime success is still hosted pending the reviewed candidate.

## Published9d fixture-clock correction tasks (FR-1, FR-5)

The compiled-wrapper correction is published9d/treec984. Run37114718919/job111179180060 passed all362 Python methods/410 variants and16 named PS scenarios; a later writer fixture failed because the culture result overwrote fixed Bracket. Artifact11270168969 is737bytes, SHA2567daed473c9e17ce5040bd126b078e64f42dd224e32beb2526f96a56da86a0f65; CRC, two manifest records and source/tree verify only source/scope, with no pilot/event evidence. The existing Plan remains active. The denied stale PR-body call was abandoned unretried; a separately reviewed accurate terminal update succeeded.

- [x] F1 Resume the existing Plan, verify exact9d failure/artifact and scope the fixture collision
  - **证据块:** contract-tests.ps1:441 assigns actual culture clock to the fixed fixture name; observe.ps1:263 preserves exact timestamp binding and rejects it;448 is the only remaining normal invocation after all16 PASS lines
  - **涉及文件:** External evidence and these three specs only
  - _需求: FR-1, FR-5_ | _设计: Published9d culture-clock fixture correction_
- [x] F2 Complete fresh impact/rename-availability/manual byte scope, check_spec and root pre-edit disposition
  - **证据块:** Existing AGENTS graph/rename rules and explicit PS UNKNOWN limits require exact source proof
  - **涉及文件:** Exactly PS<=480, audit<=480 and three specs<=500; no new file
  - _需求: FR-5_ | _设计: Published9d culture-clock fixture correction_
- [x] F3 Apply two explicit cultureBracket token edits, one fixture assertion and one Python source regression
  - **证据块:** Only culture result441/442 changes; fixed fixture/request/observer comparison remain immutable
  - **涉及文件:** Only contract-tests.ps1 and audit.py within existing caps
  - _需求: FR-1, FR-5_ | _设计: Published9d culture-clock fixture correction_
- [x] F4 Verify published source fails the new regression, all362/410 portable tests pass, and exact whole-file/old-assertion preservation
  - **证据块:** Prior full PS suite did not reach writer completion; local source tests cannot establish actual PS success
  - **涉及文件:** Existing test entries and reviewed five paths only
  - _需求: FR-1, FR-5_ | _设计: Published9d culture-clock fixture correction_
- [ ] F5 Fresh staged graph/detect_changes/full review/gencommit and exact sole9dparent publication disposition
  - **证据块:** No code after the staged gate without current-definition impact; PS dynamic behavior remains hosted pending
  - **涉及文件:** Exactly five reviewed paths
  - _需求: FR-5_ | _设计: Published9d culture-clock fixture correction_
- [ ] F6 Publish only reviewed candidate and verify actual complete PS/writer/native/event stages plus artifact provenance
  - **证据块:** No local PS5.1 execution; unchanged existing workflow must run all required gates without skips
  - **涉及文件:** Existing diagnostic branch/PR/workflow, no settings or scope expansion
  - _需求: FR-1, FR-5_ | _设计: Published9d culture-clock fixture correction_

Fixture-clock local results: all330 retained plus32 observation methods pass;410 variants are unchanged. The new anchored source guard rejects the exact published9d assignment and a mixed-case script-qualified alias, and accepts the candidate. Exact byte proof permits only two culture-result tokens and one fixture assertion in the478-line PS file; the480-line Python audit adds only its one regression assertion. All58 prior PS assertion sites and prior Python assertions remain. Independent source review found no defect. Actual full PS/writer/native/event execution remains pending a reviewed candidate.

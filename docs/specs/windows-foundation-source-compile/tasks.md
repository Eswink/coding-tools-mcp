# Tasks: Windows foundation source compile

## Task Overview
Seven finite management files, zero pure core changes.

## 任务列表
- [ ] T1 (FR-1): fresh impact; write manifest and native restoration guard.
- [ ] T2 (FR-2, FR-3): fixed disposable compiler/data-only jobs, raw evidence.
- [ ] T3 (FR-4): execute local good/tampered guard validation.

## Test Tasks
- [ ] Local native Git exact source trees/counts, positive unchanged (FR-1).
- [ ] Corrupted payload SHA/mode and patch rejected before compiler (FR-4).
- [ ] Genuine Windows compile and explicit data test logs (FR-2).
- [ ] Full source after guard and native test NOTRUN (FR-3).

## 交付物清单
Workflow, PowerShell runner, Python guard, finite JSON manifest, requirements/design/tasks. Raw independent receipts.

## Acceptance Checklist
- [ ] check_spec passes, exact seven paths only.
- [ ] Guard tests pass, fresh detect_changes/gencommit and peer review.
- [ ] Genuine CI results captured without RC qualification.

## 需求覆盖矩阵
| Requirement | Task | Evidence |
|---|---|---|
| FR-1 | T1,T3 | exact tree, count, hashes |
| FR-2 | T2 | compiler/data raw logs |
| FR-3 | T2 | fixed actions/commands/native NOTRUN |
| FR-4 | T3 | good/bad local guard receipts |

## 文件变更清单

- .github/workflows/windows-foundation-source-compile.yml
- scripts/windows_foundation_source_compile.ps1
- scripts/windows_foundation_source_guard.py
- scripts/windows_foundation_source_manifest.json
- docs/specs/windows-foundation-source-compile/requirements.md
- docs/specs/windows-foundation-source-compile/design.md
- docs/specs/windows-foundation-source-compile/tasks.md

## Frozen02 peer-review corrections
- [ ] T4 (FR-1, FR-3, FR-4): root/peer-reviewed actual compiler payload+Git closure, seven management HEAD/source beforeafter guards, literal source leases.
- [ ] Test manager byte/mode/HEAD tampering; preserve01 initial failures and native NOTRUN.

## Bounded runtime-selection repair tasks
- [ ] FR-1: preserve real run37912328111 attempt1 original receipts, command-empty/restore-NOTRUN failure and raw artifact SHA.
- [ ] FR-2: reproduce original multiapplication invocation using actual PowerShell; fix scalar selection and check actual git/Python calls.
- [ ] FR-3: ordinary negative controls missing/alias interpreter, executable-byte drift and selected-path drift; preserve guards, original pins and budgets.
- [ ] FR-4: fresh checkout-specific impact (UNKNOWN/manualHIGH disclosed), spec, independent source peer, detect_changes/gencommit, small management commit. New real GitHub run remains required after parent push.

This repair delta is exactly six tracked paths: five changes to the existing PS/workflow/three specifications and one new ordinary control script. The new eighth management-associated tracked file is a local control, excluded from the unchanged seven-file verify_manager lease and never called by compiler CI. The existing exact-seven delivery statement describes the initial carrier; this repair does not claim all tracked management files belong to that seven-file lease. Actual compiler payload byte-drift has its own ordinary rejection control with no invocation/log/command side effect.

# 任务清单：windows-broker-launch

## 概述
Single bounded experiment; parent/root acknowledged the exact pre-edit packet and source implementation is prepared. Publication and Actions wait for a separate final independent exact-source review. Native tests have not run.

## 交付物清单（Scope-lock）
Exactly nine added paths, six tasks, 1380 maximum total lines; every file fewer than 500 lines. Baseline source/tree stay `8bdd5f327b4603c5570dc764e2d62fecbe6e02d2` / `b75fdae6b9a2cb9589b51d832d7ba638384cb6b8`.

## 任务列表
- [x] 1. Complete spec, architecture, fresh impact and independent pre-edit packet review
  - 证据块: AGENTS.md; docs/project-context/{how-to-develop,how-to-test,architecture}.md; official sources in design.md; new gates directory outside source
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7_ · _设计: all sections_
- [x] 2. Add retained image identity and creating-thread debug owner, launch.h <=90 and launch.cpp <=420 lines
  - 证据块: official Debugging Events, FileIdInfo, CreateFileW, WaitForDebugEvent and ContinueDebugEvent docs; fresh upstream impacts for proposed symbols before writing
  - _需求: FR-1, FR-2, FR-3, FR-4_ · _设计: 架构设计, 数据模型, API 设计_
- [x] 3. Add finite actual-process cases <=380 lines and harmless marker stub <=60 lines
  - 证据块: exact retained/open-image comparison contract and owned mutation scope from requirements.md; independent source review of every fault seam
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5_ · _设计: 决策 4_
- [x] 4. Add preinstalled-tool preparation <=100 lines and dedicated-push workflow <=130 lines
  - 证据块: existing workflow checkout/upload action pins; host-account/code-parent trust stated in FR-6; native source hash manifest
  - _需求: FR-6, FR-7_ · _设计: 技术选型, 决策 3_
- [ ] 5. Review exact source, run finite native matrix after approval, verify artifacts
  - 证据块: spec check, static prohibited-action scan, final source/tree/diff, independent review, exact-commit Actions job/results/import logs
  - _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7_ · _设计: 风险评估_
- [ ] 6. Record source-bound result, failed/unknown cases and remaining production gates
  - 证据块: actual per-case results, nonzero case census, cleanup/join observations, staged detect_changes and Probe review/convergence
  - _需求: FR-7_ · _设计: 数据模型, 风险评估_

## 固定验收用例（18；每个 ID 恰好一次）
1. native_correct_image; 2. native_different_image; 3. native_identical_bytes_new_id
4. native_ancestor_redirect; 5. native_junction_redirect
6. native_pin_write_denied; 7. native_pin_delete_denied; 8. native_pin_rename_denied
9. manifest_rejected; 10. fault_null_image_decision; 11. fault_file_id_query; 12. fault_hash_query
13. fault_debug_wait; 14. fault_debug_continue
15. fault_preadmission_timeout; 16. fault_preadmission_cancel
17. fault_postadmission_timeout; 18. fault_postadmission_cancel
Each required ID must appear once; missing, duplicate, unsupported, setup-failed, unknown or failed cases fail the suite. Native and injected facts stay separate.

## 检查点
Before implementation: check_spec passes, fresh impacts reported (new symbols may be unresolved), parent acknowledges exact packet. Before publication: final independent reviewed source meets all budgets and prohibited-action checks. After Actions: exact job source/tree and every required case's real evidence are checked; unknowns stay failed.

## 需求覆盖矩阵
FR-1/FR-2 -> architecture/image gate -> tasks 1,2,3,5; FR-3/FR-4 -> owner/drain -> tasks 1,2,3,5; FR-5 -> owned mutations -> tasks 1,3,5; FR-6 -> DLL trust -> tasks 1,4,5; FR-7 -> evidence -> tasks 1,4,5,6.

## 文件变更清单
| Added file | Maximum lines |
|---|---:|
| scripts/windows_broker_launch/launch.h | 90 |
| scripts/windows_broker_launch/launch.cpp | 420 |
| scripts/windows_broker_launch/cases.cpp | 380 |
| scripts/windows_broker_launch/fixture.cpp | 60 |
| scripts/windows_broker_launch/prepare.ps1 | 100 |
| .github/workflows/windows-broker-launch.yml | 130 |
| docs/specs/windows-broker-launch/requirements.md | shared 200 |
| docs/specs/windows-broker-launch/design.md | shared 200 |
| docs/specs/windows-broker-launch/tasks.md | shared 200 |

## 交付前自检
- [ ] Nine added paths only, exact source/tree evidence, all line caps met
- [ ] No unrelated baseline edits or prohibited actions; no placeholders
- [ ] Actual success/substitution/fault/cancellation/termination/EOF/join evidence reviewed
- [ ] DLL and descendant limitations explicit; VM-session result remains separate

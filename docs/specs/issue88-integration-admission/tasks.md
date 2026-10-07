# Tasks: authentic full integration admission

## 交付物清单（Scope-lock）
Exactly26 paths,7 additions/19 replacements,1752 entries, aggregate2300 changed lines; four production modules. Preserve original1232/strict303 IDs and add36; no other source, permission, event or runtime scope.

## 文件变更清单
| File | Action | Final/delta line ceiling |
| --- | --- | --- |
| scripts/rc_publication_admission.py | add | 240/240 |
| scripts/rc_publication_admission_cases.py | add | 480/480 |
| scripts/rc_pretag_integration_admission_profile.py | add | 400/400 |
| scripts/rc_pretag_integration_admission_cases.py | add | 400/400 |
| docs/specs/issue88-integration-admission/requirements.md | add | 40/40 |
| docs/specs/issue88-integration-admission/design.md | add | 80/80 |
| docs/specs/issue88-integration-admission/tasks.md | add | 60/60 |
| scripts/rc_release_policy.py | replace | 180/35 |
| scripts/rc_publication_github.py | replace | 500/55 |
| scripts/rc_publication_executor.py | replace | 255/30 |
| scripts/rc_publication_https_fixture.py | replace | 220/8 |
| scripts/rc_publication_github_cases.py | replace | 370/4 |
| scripts/rc_pretag_policy_tests.py | replace | 255/6 |
| scripts/rc_pretag_publisher_executor_profile.py | replace | 190/4 |
| scripts/rc_pretag_publisher_executor_cases.py | replace | 330/55 |
| scripts/rc_pretag_composition_tests.py | replace | 493/8 |
| scripts/rc_pretag_join_once_tests.py | replace | 500/6 |
| scripts/rc_pretag_snapshot_warning_cases.py | replace | 450/12 |
| scripts/rc_pretag_appimage_cases.py | replace | 410/14 |
| scripts/rc_pretag_linux_package_cases.py | replace | 470/48 |
| scripts/rc_pretag_yoke_repair_cases.py | replace | 302/28 |
| scripts/rc_pretag_publication_adapters.py | replace | 256/12 |
| scripts/rc_pretag_linux_package_inverse.py | replace | 178/8 |
| scripts/rc_pretag_appimage_profile.py | replace | 157/4 |
| .github/workflows/issue88-publication-executor.yml | replace | 90/35 |
| scripts/rc_publication_executor_cases.py | replace | 350/60 |

## 任务列表与证据块
- [ ] 1. Implement exact live integration observations and digest. Evidence: release_tag_gate.successful_run selects latest across statuses; rc_consumer_snapshot._ObservedAPI protects repeated run snapshots; rc_publication_stage._bind binds exact invocation/jobs. Files: new admission240; policy180/35. _需求: FR-1,FR-2,FR-3,FR-4_; _设计: Source and workflow, Run/attempt/jobs, Canonical digest_.
- [ ] 2. Wire owning transport and one deadline through entry and sink. Evidence: rc_publication_github.py:52 currently raises synthetic fence_blocked; :224 reauthenticates before sendall; executor.py:57 authenticates before staging. Files: GitHub500/55, executor255/30; shared fixture220/8 and one GitHub case370/4 adapter. _需求: FR-4,FR-5_; _设计: Fixed production boundary, Deadline and interruption_.
- [ ] 3. Preserve historical assertions with exact inverse adapters. Evidence: policy_tests.py:156 requires every verifier unimplemented; publisher_executor_cases.py:244/262/263/272 protect historical bytes; finite publisher select permits only topology mismatch fallback. Files: policy test255/6, new profile400 and composition cases400, all listed legacy adapters at declared caps. _需求: FR-6_; _设计: Historical composition_.
- [ ] 4. Exercise authentic TLS reads and both changed old contracts. Evidence: executor_cases original entry test asserts no connection; HTTPSFixture supplies trusted local TLS while authorities() mocks authentication and must not be used in new authenticity proof. Files: new admission cases480, original executor cases350/60. Preserve both original IDs; require actual GETs/zero mutation/no stage/global block. _需求: FR-1,FR-2,FR-3,FR-4,FR-5,FR-7_; _设计: 测试策略_.
- [ ] 5. Validate exact source contexts and read-only hosted cases. Evidence: existing issue88-publication-executor.yml executes explicit48 with source hashes; new source needs original48+new36=84, unchanged permission/event/action/platform setup. File: existing workflow90/35 plus these three specs40/80/60. Run focused36/affected legacy then required D1268/I929/J929; independent source review and repository submission gates before draft/CI, all gates before engineering merge. _需求: FR-6,FR-7_; _设计: Historical composition, 测试策略_.

## 需求覆盖矩阵
Preparation: read AGENTS/context/Probe, freeze26 paths and exact fragments, fresh pre-edit impact/manual CRITICAL review, independent design review, check_spec and estimate.
FR-1/2/3: tasks1,4; FR-4/5: tasks1,2,4; FR-6: tasks3,5; FR-7: tasks4,5. Implementation and tests must match this exact source, with source-specific evidence limits.
Final: seal all nonself pins, verify complete candidate tree/inverses/36 IDs, perform detect_changes/source review/gencommit, publish bounded draft and run actual hosted/local contexts in parallel. Keep main/live release/native/held paths untouched.

## 风险与验收记录
All acceptance boxes remain pending until measured tests/review. Preserve failed attempts as failed; never count fixture positives as genuine current integration acceptance. Live session admission remains blocked by missing gates even when this one protocol authenticates.

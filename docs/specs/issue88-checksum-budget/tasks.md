# Tasks: cooperative checksum budget
## 交付物清单
One production checksum control change, exact historical source admission,24 new tests and three specs.
## 文件变更清单
Values are (final lines, additions+deletions); actual aggregate≤1800, sum of per-path caps1701.
- scripts/rc_artifact_consumer.py (255,4)
- scripts/rc_consumer_archive.py (390,70)
- scripts/rc_consumer_io.py (450,100)
- scripts/rc_pretag_ownership_tests.py (378,2)
- scripts/rc_pretag_staging_budget_profile.py (205,6)
- scripts/rc_pretag_staging_budget_cases.py (383,15)
- .github/workflows/issue88-publication-executor.yml (119,14)
- scripts/rc_consumer_checksum_budget_cases.py (480,480), new
- scripts/rc_pretag_checksum_budget_profile.py (400,400), new
- scripts/rc_pretag_checksum_budget_cases.py (440,440), new
- docs/specs/issue88-checksum-budget/requirements.md (40,40), new
- docs/specs/issue88-checksum-budget/design.md (70,70), new
- docs/specs/issue88-checksum-budget/tasks.md (60,60), new
Exactly13 paths,7 replacements,6 additions and1776 tracked entries. Caps are ceilings, not targets.
## 任务列表
### Task 1: freeze checksum contract and pre-edit gates (FR-1,FR-2,FR-3,FR-4)
Read actual source/context, create Plan, measure exact closure, and run fresh upstream impacts before any symbol edits.
Retain CRITICAL normalizer13direct/41affected/12flows and FTS limitation; independent exact design review plus root manual acknowledgment precede runtime edits.
Complete specs, check_spec and estimate before implementation; do not turn estimates into RC completion promises.
### Task 2: wire original controls and real checksum cases (FR-1,FR-2)
Implement only the three runtime files and12 named runtime tests with real multi-chunk reads and two real TLS workers.
Preserve omitted calls/no clock, content errors, original ownership/receipt bytes, lateEOF rejection and sticky cleanup uncertainty.
### Task 3: extend finite source admission (FR-3)
Implement the checksum profile and12 composition cases; exactly seven inverses and six finite prior identities must roundtrip whole bytes.
Change only the one ownership operand and seven staging operands plus import; preserve all prior assertion bodies and IDs.
Enroll24 new cases in existing read-only Ubuntu22/24 workflow; keep old168 tests, action pins, events, permissions and limits.
### Task 4: validate actual candidate and engineering integration (FR-4)
Run focused new/affected tests, exact independent source review, staged detect_changes and gencommit.
Publish reviewed draft/real CI in parallel with necessary independent local contexts; reconcile D1376 and I/J1037 with zero skipped/exceptional/duplicate outcomes.
Retain failed and composed evidence source-scoped; all required gates must pass before normal integration.
Verify actual ordered merge parents/tree, exact four-document PR89 overlay and five fresh hermetic checks.
### Task 5: close bounded evidence (FR-4)
Update Issue88, keep it open and PR89 draft, converge Plan and preserve a private durable checkpoint.
No full bundle/native/security/release claim follows from checksum mechanics.
## 需求覆盖矩阵
FR-1→Tasks2,4; FR-2→Tasks2,4; FR-3→Tasks3,4; FR-4→Tasks1,4,5.

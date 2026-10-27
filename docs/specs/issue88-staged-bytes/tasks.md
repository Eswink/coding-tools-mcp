# Tasks: cooperative publisher staged-byte budget
## 交付物清单
One finite capability:5existing runtime symbols, exact admission,18runtime+12composition cases and3specs. Exactly15paths=8replacements+7additions; expected1790entries.
## 文件变更清单
Values are (final lines, additions+deletions), sumdelta ceilings1753, aggregate1800, everyfile≤500.
- scripts/rc_publication_stage.py (380,100)
- scripts/rc_consumer_io.py (445,30)
- scripts/rc_publication_executor.py (275,30)
- scripts/rc_publication_staging_budget_cases.py (361,4)
- scripts/rc_pretag_archive_budget_profile.py (184,6)
- scripts/rc_pretag_archive_budget_cases.py (398,15)
- scripts/rc_pretag_checksum_budget_cases.py (380,4)
- .github/workflows/issue88-publication-executor.yml (139,14)
- scripts/rc_publication_staged_bytes_cases.py (500,500), new
- scripts/rc_publication_staged_bytes_support.py (60,60), new
- scripts/rc_pretag_staged_bytes_profile.py (350,350), new
- scripts/rc_pretag_staged_bytes_cases.py (460,460), new
- docs/specs/issue88-staged-bytes/requirements.md (40,40), new
- docs/specs/issue88-staged-bytes/design.md (80,80), new
- docs/specs/issue88-staged-bytes/tasks.md (60,60), new
## 任务列表
### Task1: freeze exact design and pre-edit gates (FR-1–FR-4; design Caller-owned invocation controls/Exact source and history)
Evidence: scripts/rc_publication_stage.py:264 `def revalidate(self):`; scripts/rc_publication_executor.py:170 `self._deadline = time.monotonic() + OPERATION_SECONDS` shows per-operation renewal outside stage.
Read AGENTS/context/Probe, retain one-worker exact source impacts and graph limitations, obtain root and independent exact review, then pass check_spec and estimate.
Only the three scoped specs and metadata may change during design; no runtime/test/workflow edits before acceptance.
### Task2: wire five byte-budget symbols without changing owners (FR-1,FR-2; design Caller-owned invocation controls/Error order and cleanup)
Evidence: scripts/rc_publication_stage.py:236 `self._output.copy(name, bundle.path / name)` and scripts/rc_consumer_io.py:333 `def copy(self, relative, source_path):` omit controls.
Use only the three runtime paths/caps above; original activation pair and later per-operation pair remain distinct. Keep bare defaults, original bytes, nofollow descriptors and EOF/close precedence.
Convert only revalidation timeout/cancel at its actual executor call. Keep cleanup, core transitions and authority unchanged.
### Task3: bind eight inverses and exact historical adapters (FR-3; design Exact source and history)
Evidence: scripts/rc_pretag_archive_budget_profile.py:97 `def normalize(path, current):`; scripts/rc_pretag_checksum_budget_cases.py:315 directly reads current source; scripts/rc_publication_staging_budget_cases.py:276 `def parsed(*args):` needs forwarding.
Use the five existing adapter/workflow paths and two new composition paths/caps above. Preserve all old methods/IDs through declared operand/spy inverses only.
Bind actual merged PR139 F before final production pins/topology/publication; verify exact parents and fulltree equality to D2. No placeholders or ancestry allowances.
### Task4: run complete real-IO/current-source evidence (FR-1–FR-4; design Real IO and source evidence)
Evidence: scripts/rc_consumer_archive_budget_support.py:108 `def trace_calls(self):` delegates real IO; .github/workflows/issue88-publication-executor.yml source checks remain read-only and exact.
Use the new runtime-case/support paths/caps,18complete cases and12composition cases. The unexecuted18case sketch fits496lines with unchanged boundary/activation helpers in60support lines; no inherited tests.
Run focused/new and original affected groups only when a local slot is free; global local test workers≤2, integrations sequential. No PR139 slot overlap.
Reconcile exact D1433/I1094/J1094 and hosted249 IDs/source/outcomes with zero skips; prior/provisional outcomes do not prove new bytes.
Run independent exact source/whole-byte review, staged detect_changes and gencommit before authorized draft/CI; preserve exact original workflow triggers/permissions/hosts/actions.
### Task5: close only engineering scope after real gates (FR-3,FR-4; design Risks and limits)
Evidence: requirements NFR-3 excludes hard global/native acceptance; actual source must match each outcome receipt.
After all required gates, verify actual integration parents/tree and exact four-document overlay, fresh mandatory checks, bounded Issue88 update and durable checkpoint.
Keep Issue88 unresolved acceptance, PR89 draft, PR98/snapshot holds and live publication/native/security limits. No main/tag/release or credentials/security action.
## 需求覆盖矩阵
FR-1→Tasks1,2,4; FR-2→Tasks1,2,4; FR-3→Tasks1,3,4,5; FR-4→Tasks1,4,5.

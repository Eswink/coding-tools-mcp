# 任务文档：issue88-stage-retirement

## 交付物清单

One stage-only ownership ledger and retirement pass,36 real regression cases,12 finite composition cases, exact historical inverses, unchanged live-admission blockers and source-bound validation receipts.

## 任务列表

- [ ] T1: Complete actual-F spec, fresh impacts and independent ownership/whole-byte review, including explicit buffered/raw closed checks (FR-1, FR-2, FR-3, FR-4)
- [ ] T2: Implement creation registration, stream/raw descriptor ownership and partial-constructor handling (FR-1)
- [ ] T3: Implement complete all-owner preflight, exact known-entry removal and one-pass failure/descriptor handling (FR-2)
- [ ] T4: Integrate sticky stage cleanup and two original test adapters without changing consumer/core/executor contracts (FR-3)
- [ ] T5: Implement finite D/I/J admission, seven full-byte inverses, twelve historical identities and exact workflow inventory (FR-4)
- [ ] T6: Run36 real filesystem/process/TLS cases, original ownership/consumer tests and12 new composition cases, including CPython3.12 reused-FD sentinel coverage (FR-1, FR-2, FR-3, FR-4)
- [ ] T7: Join independent actual-source review, staged GitNexus/gencommit, draft hosted309/303/755/452 and full D1493/I1154/J1154 coverage before ordinary engineering integration (FR-4)
- [ ] T8: Verify ordered merge parents/tree, exact four-document overlay and five fresh postmerge gates; update Issue88 and durable checkpoint while retaining all release blockers (FR-4)

## 需求覆盖矩阵

| Requirement | Tasks | Required evidence |
|---|---|---|
| FR-1 | T1,T2,T6 | Real partial acquisition, close uncertainty, exact stream/raw quiescence and reused-FD/late-flush/GC sentinel cases |
| FR-2 | T1,T3,T6 | Complete registered file/directory membership, aliases/drift rejection, no unowned deletion, first-failure stopping and repeated-close no-op |
| FR-3 | T1,T4,T6 | Default retained outputs, actual worker reaping, uncertain cleanup retention and original executor effects |
| FR-4 | T1,T5,T6,T7,T8 | Exact source/inventory/inverses/topology, fresh negative validation and actual source-bound local/hosted results |

## 文件变更清单

Caps are final lines / added+deleted lines; aggregate delta2250 overrides individual ceilings.

| Path | Cap | Action |
|---|---|---|
| scripts/rc_consumer_io.py | 480/90 | replace |
| scripts/rc_publication_stage.py | 380/40 | replace |
| scripts/rc_publication_stage_cases.py | 360/6 | replace |
| scripts/rc_publication_staged_bytes_cases.py | 500/4 | replace |
| scripts/rc_publication_retirement.py | 260/260 | add |
| scripts/rc_publication_retirement_cases.py | 470/470 | add |
| scripts/rc_publication_retirement_lifetime_cases.py | 280/280 | add |
| scripts/rc_pretag_supervisor_readiness_profile.py | 185/6 | replace |
| scripts/rc_pretag_supervisor_readiness_cases.py | 350/30 | replace |
| scripts/rc_pretag_stage_retirement_profile.py | 350/350 | add |
| scripts/rc_pretag_stage_retirement_cases.py | 450/450 | add |
| .github/workflows/issue88-publication-executor.yml | 165/14 | replace |
| docs/specs/issue88-stage-retirement/requirements.md | 60/60 | add |
| docs/specs/issue88-stage-retirement/design.md | 90/90 | add |
| docs/specs/issue88-stage-retirement/tasks.md | 70/70 | add |

Baseline F has1795 entries; candidate1803. Preserve1445 original IDs and all assertions; add48 IDs. Every rejected attempt stays source-scoped, and no failed gate is replaced by overlapping coverage.
No executor/worker/transport/archive/core/eligibility/Windows/held-source changes, live publication, credential expansion, security-setting change or generic cleanup framework.

# 任务清单：ubuntu-sandbox-dispatch

## 交付物清单

Parent/child integration specifications, an actual HTTP dispatch probe, a strict result
classifier with unit tests and a read-only CI workflow. Production integration is blocked,
not complete; #73 and the global delivery manifest must remain unverified.

## 任务列表

- [x] Review baseline source and fresh pinned impact output; stop HIGH/CRITICAL production edits.
- [x] Write exact acceptance probes and classifier unit tests.
- [ ] Execute and retain native baseline evidence (update receipt after the workflow).
- [ ] Review/implement authority and enforcement in a subsequent scoped production increment.
- [ ] Pass mandatory acceptance plus lifecycle/toolchain regression before closing #73.

## 需求覆盖矩阵

| FR ID | 子规格 | 任务引用 | 状态 |
|---|---|---|---|
| FR-1 | authority | authority/1.1 | 阻断/待实现 |
| FR-2 | authority | authority/1.2 | 阻断/待实现 |
| FR-3 | authority | authority/1.3 | 阻断/待实现 |
| FR-4 | enforcement | enforcement/1.1 | 阻断/待实现 |
| FR-5 | enforcement | enforcement/1.2 | 阻断/待实现 |
| FR-6 | verification | verification/1.1 | 阻断/待实现 |
| FR-7 | verification | verification/1.2 | 阻断/待实现 |

## 子规格任务覆盖矩阵

The requirement matrix above links every child task; child files are the implementation task authority.

## 文件变更清单

Only this specification directory, diagnostic files in tests/cloud-gateway and the read-only workflow. No production symbol or dependency changes.

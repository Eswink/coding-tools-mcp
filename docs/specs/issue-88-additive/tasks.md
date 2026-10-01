# Tasks: pure publication contracts

## 交付物清单
Three pure modules, one fixture, four test modules, one diagnostic CI workflow and nine specification files.

## 任务列表
- inventory/1.1: pure recipe/inventory implementation and adversarial tests
- inventory/1.2: boundary/size/checksum and original regressions
- journal/1.1: attempt/checkpoint and reconciliation implementation/tests
- journal/1.2: failure/replay/CI diagnostic retention checks

## 需求覆盖矩阵
| Task | Requirements |
|---|---|
| inventory/1.1 | FR-1, FR-2, FR-4 |
| inventory/1.2 | FR-1, FR-2, FR-4 |
| journal/1.1 | FR-3, FR-4 |
| journal/1.2 | FR-3, FR-4 |

## 文件变更清单
New scripts/rc_publication_{types,contract,reconcile,fixtures}.py and rc_publication_{types,contract,reconcile,boundary}_tests.py; .github/workflows/rc-publication-contract-checks.yml; this parent/subspec directory only. No predecessor edits.

Details live in subspecs/inventory/tasks.md and subspecs/journal/tasks.md. Implementation follows check_spec; final proof includes new+420tests with zero skips, compilation/actionlint, exact predecessor blobs/modes, fresh staged graph and independent review. Hosted and operational acceptance remain separate.

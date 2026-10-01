# 子任务：Ordered attempts, checkpoints and conservative observation-only reconciliation

- [ ] 1.1 Implement the pure records/functions and adversarial tests
  - 证据块: existing scripts/rc_pretag_types.py:64–130 and parent design contracts
  - 涉及文件: scripts/rc_publication_reconcile.py; scripts/rc_publication_reconcile_tests.py; scripts/rc_publication_boundary_tests.py; .github/workflows/rc-publication-contract-checks.yml
  - _需求: FR-3, FR-4_
- [ ] 1.2 Verify bounds, forbidden authority and original regressions
  - 证据块: exact53/159/208 loaded groups and new zero-skip tests; synthetic evidence only
  - 涉及文件: scripts/rc_publication_reconcile.py; scripts/rc_publication_reconcile_tests.py; scripts/rc_publication_boundary_tests.py; .github/workflows/rc-publication-contract-checks.yml
  - _需求: FR-3, FR-4_

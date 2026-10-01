# 子规格：Ordered attempts, checkpoints and conservative observation-only reconciliation

## 范围
Ordered attempts, checkpoints and conservative observation-only reconciliation.

## 需求回链
FR-3, FR-4

## 验收标准（EARS）
WHEN validating a journal THEN the system SHALL require contiguous wrapper entries, fixed recipe/source/target, unique attempts and fresh post-success checkpoints. IF an attempt is prepared-only, unknown or failed THEN the system SHALL no later attempt is permitted. WHEN later read checkpoints report new IDs THEN the system SHALL retain them without accounting success/ownership or clearing uncertainty. WHEN publication is reported THEN the system SHALL preserve it through later failed/unknown reads and suggest no rollback.

## 涉及文件
scripts/rc_publication_reconcile.py; scripts/rc_publication_reconcile_tests.py; scripts/rc_publication_boundary_tests.py; .github/workflows/rc-publication-contract-checks.yml

## 不做项
No authenticating collector, authority, network/CLI/mutation, old-file edit or held transport work.

## 设计要点
Follow the parent design model and all shared non-authority invariants. Observation consistency never establishes live evidence.

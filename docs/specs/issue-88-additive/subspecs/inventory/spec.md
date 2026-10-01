# 子规格：Source-bound exact recipe and untrusted inventory classification

## 范围
Source-bound exact recipe and untrusted inventory classification.

## 需求回链
FR-1, FR-2, FR-4

## 验收标准（EARS）
WHEN validating input THEN the system SHALL deeply revalidate exact record types and immutable false authority flags. WHEN deriving recipe identity THEN the system SHALL require canonical asset ordering/domain separation. IF checksum/inventory/MIME/visibility/source/target/count data is missing, duplicated, malformed or conflicting THEN the system SHALL reject or classify unknown/collision without authority. WHEN accepting consistent supplied data THEN the system SHALL retain every fixed blocker.

## 涉及文件
scripts/rc_publication_types.py; scripts/rc_publication_contract.py; scripts/rc_publication_fixtures.py; scripts/rc_publication_types_tests.py; scripts/rc_publication_contract_tests.py

## 不做项
No authenticating collector, authority, network/CLI/mutation, old-file edit or held transport work.

## 设计要点
Follow the parent design model and all shared non-authority invariants. Observation consistency never establishes live evidence.

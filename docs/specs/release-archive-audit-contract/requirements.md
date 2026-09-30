# 需求文档：release-archive-audit-contract

## 功能概述
Bind the exact four-binary cloud archive to complete Cargo build evidence and trusted CI producer outputs before final packaging consumes it. Preserve raw dependency findings and all independent release gates.

## 历史经验与坑
Co-located archive receipts are not independent trust anchors. The existing exact-build helper deliberately does not authorize a release and does not enforce the particular producer or unsound-warning policy.

## 术语定义
- Trusted outputs: digests and producer identity delivered through the reviewed CI dependency graph
- Applicability: absence of an affected package from both complete actual and conservative graphs

## 范围边界
In scope: a separate policy adapter, archive digest verification, same-commit reusable cloud workflow, final evidence join, synthetic negative tests and bounded engineering proof.
Out of scope: dependency versions, GLib implementation, verify_records changes, frozen release manifest, installer/native/security policy changes, publication and release approval.

## 需求列表
### FR-1: Authenticate archive and producer
**优先级:** Must
**用户故事:** Release reviewers need independently bound archive and build evidence.
#### 验收标准（EARS）
1. WHEN archive evidence is consumed THEN the system SHALL require trusted archive and envelope SHA256 values plus exact repository/source/run/attempt/workflow/job identity.
2. IF any identity, stream, member or executable differs THEN the system SHALL fail before using the executable.

### FR-2: Preserve findings and reject unresolved security evidence
**优先级:** Must
**用户故事:** Security reviewers need truthful raw reports and narrowly scoped conclusions.
#### 验收标准（EARS）
1. WHEN cloud applicability passes THEN the system SHALL retain the original raw report byte-for-byte and classify each vulnerability using complete actual and conservative build evidence.
2. IF a vulnerability is active/unmapped/unproven or an unsound warning is active/unknown THEN the system SHALL reject the contract.
3. WHILE desktop GLib uses a local backport THE system SHALL require separate live source provenance verification and retain the original advisory; cloud absence proof SHALL NOT cover it.

### FR-3: Preserve release DAG and boundaries
**优先级:** Must
**用户故事:** Engineers need evidence production without an approval dependency cycle.
#### 验收标准（EARS）
1. WHEN final packaging runs THEN the system SHALL invoke same-commit cloud evidence before final contracts, preserving source/version/integration and installed/native/security gates.
2. IF final version or Windows/snapshot gates are unresolved THEN the system SHALL NOT claim final acceptance.
3. WHEN engineering evidence runs THEN every receipt SHALL state release_approved=false and publish_approved=false.
4. WHEN final packaging runs THEN all 14 topology cases SHALL run through the same-commit reusable issue40 workflow after source approval; failed, skipped or cancelled topology SHALL block the final bundle.

## 非功能需求
- NFR-1: Local verification performs bounded parsing and hashing; no live application invocation before authentication
- NFR-2: No advisory ignore, report editing, broad cleanliness exception, credentials or production deployment
- NFR-3: Python3.12 and current pinned Rust/Cargo1.98.1 remain supported

## 依赖关系
Existing exact_build_audit, cloud_release_bundle, final_rc_evidence and independent GLib verifier; official RustSec database; GitHub needs outputs.

## 检查清单
- [x] Stable requirements, explicit scope and independently testable negative cases

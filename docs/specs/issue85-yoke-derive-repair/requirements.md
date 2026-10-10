# Requirements: supported yoke derive replacement

## 功能概述
Repair the compiled yanked yoke-derive 0.8.3 in the two cloud lockfiles at F b97c469b1bd7ffb9973a65e19b798d2573561d92. The official 0.8.4 replacement fixes the documented MSRV regression and satisfies yoke 0.8.3's ^0.8.2 dependency. This is an engineering dependency repair, not release approval.

## 需求列表
### FR-1 Supported resolution
WHEN resolving either cloud workspace, the implementation SHALL use Cargo 1.98.1 to select official non-yanked yoke-derive 0.8.4, checksum ec8ebde2db3681e8c9980cc27822030e68752690ddfa9473e739aeb4dbde6d71.
### FR-2 Minimal lock change
WHEN comparing either updated lock with F, only one complete yoke-derive record's version and checksum SHALL differ; dependencies, ordering and every other package SHALL remain identical. Unrelated resolution SHALL block implementation.
### FR-3 Closed composition
WHEN admitting a candidate, the profile SHALL accept only D[F], I[F,D] with the complete D tree, or J[R,I] with exactly the four existing pinned release documents. F identity/tree/ordered parents and R SHALL be immutable.
### FR-4 Fail-closed content
WHEN topology selects this profile, exact paths, modes, blob/digest/size/line pins, budgets and full-byte lock/dispatcher inverses SHALL be required. Historical or content failure SHALL remain terminal; only topology mismatch may delegate.
### FR-5 Preserved regressions
The implementation SHALL preserve all 1174 existing IDs/assertions and strict303 discovery, adding ten disjoint named cases. Missing, duplicated, skipped or exceptional outcomes SHALL fail; repeated contexts SHALL not inflate unique coverage.
### FR-6 Changed-lock native coverage
The new read-only push workflow SHALL admit exact D on Ubuntu with full history and bind every native row to its successful same-run SHA/tree/two lock hashes and exact run ID/attempt, independently verifying exact checkout parents, tree/index modes and raw tracked bytes; missing or mismatched outputs SHALL fail. It SHALL test the standalone cloud-agent on Ubuntu22/Windows2025 and the existing portable gateway command on Windows2025, and preserve source/lock/toolchain/log evidence on failure.
### FR-7 Existing real evidence
The unchanged issue40 workflow SHALL run on the identical candidate, retaining Linux portable contracts, the real audited four-binary build, actual 45/57 geometry inventories and native11/TLS9. Raw RSA and all warnings SHALL remain visible; no separate duplicate audit or desktop package build is required.
### FR-8 Protected authority
The repair SHALL preserve desktop/local-agent locks, product versions, runtime/security/eligibility policies, historical pins/inverses, held PR98 paths/ref and snapshot implementation. Workflow permissions SHALL stay contents:read; credentials and live publication SHALL remain outside scope.

## 非功能需求
Require the frozen nine-path/720-line contract, exact source review, original303/755/452 hosted gates, source-context1184/845/845 coverage and fresh changed-lock native evidence. Earlier receipts retain their original source identity. Issue85 and final RC gates remain open until their original acceptance is met.

## 依赖关系
Reuse existing Cargo manifests, exact source profiles/inverses, read-only workflows and current compiler/audit/runtime contracts.

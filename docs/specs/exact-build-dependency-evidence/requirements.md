# 需求文档：exact-build-dependency-evidence
## 功能概述
Add a fail-closed exact Rust build dependency evidence collector/verifier for Issue85. Raw lockfile advisories remain unchanged and visible. No parent release gate is changed by this increment.
## 需求列表
### FR-1 Capture exact build provenance
WHEN collecting evidence, the helper SHALL require a clean exact committed source, fixed release/locked/four-bin command, toolchain/target/features, original lock and manifest digests, complete Cargo JSON and all output binary hashes.
### FR-2 Reconcile complete build units
WHEN verifying, the helper SHALL compare exact target normal/build package IDs, versions, sources and enabled features against every compiler-artifact event including fresh=true; require four expected root executables, successful process and build-finished, and reject missing, extra, ambiguous or unmapped packages.
### FR-3 Preserve raw security findings
WHEN auditing, the helper SHALL keep the real unfiltered original lockfile report and advisory database identity, disallow ignores/severity/target filters, reject active findings, and classify absent optional findings separately without claiming raw audit zero. An all-target/all-feature normal/build/dev graph remains a conservative second check.
### FR-4 Detect tampering and regressions
WHEN source, binary, provenance or reports differ from externally expected identities, verification SHALL fail. Mutation tests cover omitted unit/root, failed finish, altered hashes/targets/features, active RSA/advisory, modified reports and stale evidence.
## 非功能需求
NFR-1 Stable existing Python/Cargo tools only; no nightly, SQLx fork, production configuration or parent gate edits. Evidence does not prove function-level reachability or native-library safety.
## 依赖关系
Existing source identity/package audit contracts; real RustSec database and Cargo JSON output. Parent reviews release-contract adoption separately.
## 验收标准
- [ ] FR-1 through FR-4 verified by real capture plus deterministic negative tests
- [ ] Raw RSA remains disclosed; Windows/Ubuntu and all final artifact gates remain independent

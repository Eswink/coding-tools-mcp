# 设计文档：exact-build-dependency-evidence
## 概述
Covers FR-1,FR-2,FR-3,FR-4,NFR-1. Additive helper with no release gate caller yet.
## 技术方案
Collector runs metadata, exact selected tree, conservative tree, release locked four-bin build JSON and unfiltered cargo-audit against original lock. Verifier treats metadata only as an identity map; selected tree and compiler events must agree completely. Runtime/compiler package findings are checked against full raw audit output. Original raw lockfinding status is retained.
## 数据模型
Version1 evidence envelope binds source commit/tree, original source-root location, lock/manifest/product-version, target/toolchain, exact commands/exit statuses, input-stream SHA256 and four binary names/hashes. An externally supplied envelope digest is mandatory for independent verification. Self-hashes alone do not provide authenticity.
## API 设计
scripts/exact_build_audit.py collect --root ROOT --expected-sha SHA --version VERSION --target TARGET --output OUTSIDE_REPO --audit-bin BIN --audit-db DIR; verify additionally requires --expected-envelope-sha256 and exact source/version/target. Optional binary directory verifies extracted artifacts. No --ignore or applicability override.
## 文件结构
New scripts/exact_build_audit.py; scripts/exact_build_audit_tests.py; docs/releases/exact-build-audit-integration.md; three spec files, and a isolated-CI-prefix/manual engineering workflow. No existing files modified.
## 设计决策
Keep raw lock audit failure data and exact-build result as separate fields. Fail on Cargo tree/artifact disagreement rather than inventing an equivalence. Every source ID resolves to original lock package, including build/proc-macro units. No panic-string fallback. Root four executable names are fixed. Full original audit advisories are intersected with exact compiled/selected/conservative IDs; no synthetic cleaned lockfile is used.
## 测试策略
Synthetic unit fixtures validate verifier fail-closed invariants, not real build completion. Native real release capture is a separate parent CI requirement. Tests mutate individual dependency/root events, JSON, exit, hash, package, feature, advisory, settings and expected identity. Fresh=true must remain accepted.
## 风险评估
Cargo tree is approximate; mismatches are blockers. Evidence needs trusted CI provenance plus external digest; internally recomputed checksums alone cannot defeat malicious wholesale forgery. Build scripts/native libraries require other scans. Existing raw-zero gate is not automatically waived.
## 检查清单
- [x] All FRs mapped to source/evidence model
- [ ] Parent release adoption and exact native build evidence

Parent review hardening: JSON decoding rejects NaN, Infinity and overflow-to-infinity; envelope schema must have exact integer type. GitHub producers are bound to Eswink/coding-tools-mcp and Cargo/Rust 1.98.1. GitHub acquisition is a collector-owned official shallow clone with UTC start/completion and command/exit provenance, bound to the snapshot before compilation and again before/after audit. Existing local snapshots remain explicitly local; raw database null telemetry is untouched.

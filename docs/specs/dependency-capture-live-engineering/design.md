# 设计文档：dependency-capture-live-engineering

## 概述
Add a narrow evidence-only layer around unchanged production capture and source verification.

## 技术方案
FR-1: A new Python collect command invokes the existing collector in a subprocess with new external output/database paths. A command recorder saves exact stdout/stderr/exit/timing before interpreting success. The gateway audit uses the collector's database. Failed collection leaves diagnostic execution records and cannot produce a verified receipt. No subprocess output is rewritten.
FR-2: A successful receipt hashes every capture file and binds source and CI identities. The verify command checks an independently supplied receipt digest, exact inventory, expected producer context, current source and four lock hashes. It validates raw counts, findings identities and exits without interpreting findings as acceptable. The existing desktop_source_proof function rechecks GLib against its pinned archive, current vendored source, captured locked metadata and paired raw audits. The unchanged final noncloud policy is not invoked or bypassed; it remains a later security gate.
FR-3: A two-job workflow captures on Ubuntu 24.04 and independently downloads/verifies on Ubuntu 24.04. It accepts only one exact branch/repository push, has read-only contents permissions and no dispatch/publish/build mechanism. Toolchain is Rust 1.98.1, cargo-audit 0.22.2 and Python 3.12. Available diagnostics are uploaded even after ordinary failure.

## 数据模型与接口
CLI collect: --root, --output, --audit-bin, --audit-db, --expected-sha, --version. CLI verify: --root, --output, --expected-sha, --version, --expected-receipt-sha256. Consumer expectations derive from its GitHub context with producer job fixed as capture. Receipt schema 1 contains source identity, producer identity, tool command records, all four report records, advisory snapshot and full capture-file hashes. Receipt and summary explicitly distinguish integrity verification from raw vulnerability and warning counts and deny release/publish/raw-zero authority.

## 文件结构
1. scripts/engineering_dependency_capture.py, below 300 lines
2. scripts/engineering_dependency_capture_tests.py, below 300 lines
3. .github/workflows/issue85-dependency-capture.yml, approximately 130 lines
4. docs/specs/dependency-capture-live-engineering/requirements.md
5. docs/specs/dependency-capture-live-engineering/design.md
6. docs/specs/dependency-capture-live-engineering/tasks.md
Existing source, policies, workflow gates, manifests and locks stay unchanged.

## 设计决策
Use an additive wrapper to keep release behavior unchanged. Do not adapt the existing final verifier to allow engineering producers or findings. Trust the digest from the producer job output, never a digest inside the downloaded receipt. Record only a small allowlist of CI identity fields, never the process environment. A successful collector proves its own database clone returned zero; the wrapper records collector timing without claiming exact clone timestamps.

## 测试策略
FR-1: synthetic subprocess-boundary tests for successful collection, findings, every exit/count mismatch, tool failure, source drift and database drift; assert retained bytes and failure records. FR-2: fixture receipts and files test independent digest mismatch, recomputed inner hashes, report/lock/tool/producer mismatches and existing GLib proof invocation. Real GLib/source/registry/metadata capture is hosted evidence, not a mocked test claim. FR-3: assert all nonapproval flags and exact workflow guard/permissions, and run actionlint plus existing capture, dependency and exact-build contract suites.

## 风险评估
Production impact is low because all existing symbols remain unchanged. CI/evidence risk is medium: live network/tool failures, real GLib metadata mismatch and future advisories can fail the lane. GitNexus capture impact has 2 direct callers and 10 upstream nodes; shared source_identity and final verifier reach 20/17 nodes, so neither is edited. Current graph lacks FTS but exact symbol upstream analysis succeeded. The wrapper cannot reconstruct per-command exits from a collector that fails before writing its receipt; it retains the collector's nonzero exit and partial raw files and declares capture incomplete.

## 检查清单
Requirements map to tests and bounded CI. No positive release/security conclusion follows from pipeline integrity. Final candidate must recapture all required evidence.

The capture artifact is fully inventoried and digest-bound. Installation/test/source logs and the producer convenience summary are uploaded separately as diagnostic-only evidence; the consumer recomputes its own integrity result.

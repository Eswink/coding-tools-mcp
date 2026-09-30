# 设计文档：strict-legacy-release-gates
## 概述
Separate stable/RC source classification from publication policy and frozen cumulative scope from historical additive lab scope.
## 技术方案
FR-1: source_provenance_gate.py delegates to existing stable/RC verify_source after strict fullmatch. Six-field and clean-source checks remain authoritative.
FR-2: reviewed_source_gate.py reads a tracked frozen manifest from HEAD, compares exact Git diff against pinned base, and independently computes before/after blob hashes and modes. Deletions are first-class. Rename detection disabled; rename is delete+add.
FR-3: only one literal manifest path is excluded from its own file digest map. Its actual blob is recorded. No workflow/helper/test/document exceptions. The manifest is review material, not a signature or owner approval proof.
FR-4: both workflows run contract tests before scope validation, independent failure remains visible. Old branch exact guard remains unchanged.
FR-5: no manifest file is created by this increment; missing manifest must fail with an explicit reviewed-source blocker.
## 文件结构
scripts/source_provenance_gate.py and tests; scripts/reviewed_source_gate.py and tests; two existing workflows; docs/releases/legacy-source-gates.md; three spec files.
## 数据模型
Manifest schema1: pinned base, reviewed version, review_reference (human audit locator), entries sorted by path containing status and nullable before/after objects with mode, blob_sha and sha256. Report includes actual source SHA/tree and manifest Git blob; no publish_approved true.
## 测试策略
Real temporary Git repos for stable/RC and reviewed manifest positive/deletion/extra/missing/digest/status/mode/base mutations. Existing stable and RC suites unchanged. actionlint validates workflows. Current candidate without frozen manifest expected fails.
## 风险与决策
A PR can edit both validator and manifest; branch protection and external code review are the trust anchor. CI proves consistency only. Manifest metadata is exact bounded path, not a broad directory exclusion.

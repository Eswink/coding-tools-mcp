# 需求文档：issue-88-additive

## 功能概述
Implement only pure publication recipe, inventory and transaction-journal consistency contracts. Existing pretag identities/codecs and payload contracts are reused unchanged. Schema success is not evidence authentication.

## 范围边界
In Scope: three pure modules, fixtures/tests, this layered specification, exact isolated read-only diagnostic CI.
Out of Scope: CLI, HTTP/request builders, network, filesystem/environment access in runtime modules, tokens, tag/Release/dispatch operations, existing helper changes, held transport work, security settings, permission expansion and real admission/approval.

## 需求列表
| FR ID | Requirement | Owner |
|---|---|---|
| FR-1 | Exact source-bound six-asset recipe, canonical fingerprint and checksum consistency | inventory |
| FR-2 | Bounded explicit visibility/completeness and release/asset observation classification | inventory |
| FR-3 | Single-attempt ordered journal, terminal uncertainty/failure and read-only reconciliation | journal |
| FR-4 | Immutable non-authority boundary, strict bounds, original regressions and synthetic diagnostic evidence | inventory, journal |

### FR-1 (Must)
WHEN a recipe is supplied THEN require the unchanged SourceIdentity, exact RC tag, four PayloadObservation-validated payloads and two fixed evidence assets in canonical family order. WHEN checksums are supplied THEN require exact sorted five-file coverage and verify the checksum file's own size/digest. IF names, types, bounds or hashes differ THEN reject. Fingerprinting SHALL use a fixed domain and deeply revalidated canonical encoding.

### FR-2 (Must)
WHEN inventory is classified THEN preserve explicit source/target, lookup, completeness and draft-visibility observations. IF evidence is inaccessible, incomplete, conflicting, missing or contains duplicate/extra identities THEN return unknown/collision, never inferred absence or ownership. Exact observations SHALL include MIME. Reported target_commitish SHALL NOT authenticate a tag.

### FR-3 (Must)
WHEN a journal is validated THEN require contiguous entries, exactly one attempt/checkpoint payload, one attempt per operation/asset, one release target, and a fresh matching checkpoint after each successful operation. IF any attempt is prepared-only, unknown or failed THEN reject all later attempts while retaining later read checkpoints. Unknown-result IDs SHALL be retained for reconciliation without adding them to accounted success or clearing uncertainty. Publication observation and uncertainty SHALL remain independent monotonic facts.

### FR-4 (Must)
WHEN any result is produced THEN evidence_authentication SHALL be unverified; execution_enabled, release_approved, publish_approved and snapshot_atomic SHALL be false, with all fixed unresolved prerequisites retained. No eligible factory exists. WHEN CI runs THEN all53 pretag+159 consumer+208 original cases and a nonzero new suite SHALL succeed with zero skips. Diagnostic Actions artifacts SHALL retain bounded actual source/tree/count/exit/tool receipts and logs when the runner remains available; retention success SHALL NOT replace test failure. No Release assets are uploaded.

## 非功能需求
All Python files <=500 lines. Existing256KiB JSON/16-level codec limits remain; six expected assets,<=16 observed assets,<=2 matching releases,<=32 journal entries. Payload bounds reuse2GiB; provenance<=256KiB/checksums<=8192bytes. No freeform secrets/URLs/paths/commands. Runtime imports, including the existing data-only transitive chain, remain free of side effects and dynamic caller-directed execution.

## 依赖关系
Unchanged rc_pretag_types, rc_pretag_evidence and their data-only policy/eligibility imports. Complete release-policy inventory is not duplicated. Operational no-implicit-tag atomicity, authenticated admission/consumer handoff, real visibility/freshness and FINAL/public proof are unresolved, not bypass flags.

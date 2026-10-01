# Design: typed pre-tag evidence boundary

## 概述

Covers FR-1 through FR-5 and NFR-1 through NFR-3. This schema-only phase preserves the existing consumer as a post-tag verifier; it neither invokes nor changes it. All supplied observations remain untrusted until a later independently reviewed authenticated collector exists.

## 技术方案

Use frozen dataclasses with constructor validation and explicit exact-field JSON codecs. New primitive/identity types validate actual-shape invocation observations, source/tree/version and current attempts. Strict decoding rejects duplicate keys, nonfinite values, oversized input, excessive nesting, unknown fields and coercion. Integration pull_request observations require actual `refs/pull/<positive N>/merge` plus matching workflow_ref; push requires a head ref. JSON integer-limit errors produce fixed diagnostics. Negative reported review states remain failed while unproven positive reports stay unknown. No environment or network is read; no file is finalized.

The fixed policy maps every current release-ledger row, including all21 issue IDs from canonical source `e2e011f7f2a3a1df838bbd588106205b999db610`. Issue88 publication/post-tag acceptance is explicitly mapped as later blocked scope, avoiding a circular pre-tag dependency. Requirements are not executable URLs supplied by a caller. Every gate declares read endpoints/artifact contract, nominal permission set, visibility, source and attempt requirements, completeness and admission fence. Unknown mapping details are explicitly unimplemented and cannot pass. Post-publication requirements remain mapped but cannot accidentally become pre-tag success prerequisites; real-host observations stay deferred.

## 数据模型

- SourceIdentity: fixed repository, SHA/tree, strict canonical RC version
- InvocationIdentity: pretag/integration/final/consumer role, exact workflow/event/ref/source/workflow SHA and positive run/attempt/job IDs; FINAL alone is attempt1
- PreTagCandidate: source, observed pretag invocation, frozen manifest blob/digest, policy revision and separate local/remote absent-tag observations
- GateRequirement and GateObservation: fixed gate ID and typed reported status/permission/visibility/source/run/review evidence digest; a report never authenticates itself
- ReleaseEligibility: complete ordered results, missing/failed/unknown row reasons, blocked status and immutable false approvals
- PreTagEvidenceReceipt: candidate, optional selected source-bound integration/FINAL/consumer identities, bound bundle metadata, four payload records, original structural blocker observation and audit summaries; collection remains unverified and finalization false

## API 设计

Pure constructors, exact-field decoding and deterministic serialization; an evaluator consumes typed observations and returns blocked results. There is no CLI, eligible factory, verifier injection, authenticated=true input, tag state override, network adapter or side effect. Schema validity is reported separately from evidence verification. A future collector must establish fresh authenticated provenance and undergo separate review; it cannot be enabled merely by setting a flag.

## 文件结构

New files only: `scripts/rc_pretag_types.py`, `scripts/rc_pretag_evidence.py`, `scripts/rc_release_policy.py`, `scripts/rc_release_eligibility.py`, focused `scripts/rc_pretag*_tests.py`/fixtures, `.github/workflows/rc-pretag-contract-checks.yml`, and this three-file spec. Split any module before500 lines. Existing producer/consumer/workflow code is unchanged.

## 设计决策

1. No shared-helper extraction: fresh GitNexus marks resolve_candidate HIGH (43 impacted,6 direct,3 flows). Keeping it untouched avoids weakening source/tag checks (FR-1, FR-5)
2. No passed-capable aggregate: authenticating producers do not exist for the complete map, so reported passed becomes unknown/unverified, never approved. Separate reported status preserves observations (FR-2, FR-3)
3. Frozen records use tuples and immutable nested types; serializers revalidate to reject malformed direct construction. Strict identity includes repository numeric ID and source/tree across every nested row (FR-1, FR-3, FR-4)
4. Historical blockers are preserved exactly, accompanied by identity/digest/time. Unknown blockers block rather than disappearing (FR-4)
5. No real workflow invocation is fabricated. Fixture workflow names are distinct from the later pretag collector path; fixture data expressly remains synthetic (FR-5)

## 测试策略

Table-driven malformed-type/identity/extra-field/duplicate-key/numeric/nesting tests; remove/change every policy row individually; wrong source/tree/current attempt and provenance substitution; FINAL attempt2 versus consumer/integration attempt3; missing draft/review/engineering/postmerge evidence; structural passed plus blockers; no side-effect imports/calls or successful serialization flag; exact job/payload/ledger coverage; existing159+208 regressions unchanged; actionlint and Python compilation. Hosted execution is not claimed by local tests.

## 风险评估

Semantic trust confusion is the principal risk: schema-valid observations may be misused externally. Mitigate with unverified collection, finalized=false, always blocked, no authenticity/approval switches and explicit limitations. Policy drift is guarded by full ledger-ID mapping tests; GitNexus cannot prove dynamically constructed schema/workflow paths, so manual inventory and static tests complement graph evidence. No endpoint capability or visibility is inferred from a permission label.

## 检查清单

- [x] No runtime source helper edits, live collection, mutator or eligible path
- [x] Every FR is mapped to typed contracts and adversarial tests

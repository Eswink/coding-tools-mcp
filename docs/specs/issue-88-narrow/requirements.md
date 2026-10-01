# Requirements: pre-tag evidence contract (Issue 88)

## 功能概述

Implement only data types, validation, a fixed evidence/permission map and hermetic adversarial fixtures for the next pre-tag boundary. This is not an evidence collector or publication path. The approved full design digest is `e84d3208ba037485857e2b49748734de084b0dec1b4caae500ac73a2cc707ed4`; independent design re-review is `8bb3fa3999ab0c3719de0f5414345682a5aba0d2a2121658d846b6fb40be27f2`. Both approve only this phase. Base source is `6b6ad879bfaeb3246de0a30d965da42c85b17873`.

## 历史经验与坑

Current source shows that structural passed flags and a reviewed manifest's freeform review reference do not prove approval. Existing consumer source/tag/authentication and current-attempt contracts must remain intact. Successful pagination alone does not prove draft visibility. A failed or inaccessible read is unknown, not absence.

## 术语定义

- PreTagCandidate: strict immutable source/version/prospective-tag and observed push identity data, not an authenticated candidate or an existing tag plan
- PreTagEvidenceReceipt: data-only typed record with separate collection and eligibility status; this phase supports only unverified observation records
- ReleaseEligibility: exact policy gate inventory and blocked aggregation; it never grants authority
- Observation: caller-supplied data awaiting independent authenticating producers; valid structure is not authenticity

## 范围边界

In scope: additive Python standard-library data contracts, bounded strict JSON decoding/encoding, complete ledger coverage, typed endpoint/permission/visibility/freshness requirements, fixed blocked reasons, tests and a read-only fixture workflow.

Out of scope: live HTTP/Git/source collection, actual pre-tag controller, finalized success receipt, source extraction/refactoring, tag/dispatch/Release operations, credential changes, elevated visibility probes, selecting a release version, old producer/consumer/stable changes, Issue86 implementation, real eligibility or public publication.

## 需求列表

### FR-1: Bind strict pre-tag identities (Must)

As a reviewer I need distinguishable typed identities so a prospective tag cannot bypass the existing consumer.

1. WHEN a candidate is decoded THEN exact fields/types, fixed repository name/numeric ID, canonical RC version, source/tree, prospective tag and observed push workflow/ref/source shall be validated
2. IF identity is missing, booleans replace integers, any extra field asserts approval, source/workflow SHA differs, or tag is present THEN decoding shall fail
3. WHILE this is a data-only phase THEN no source, invocation or absence observation shall become independently authenticated by parsing

### FR-2: Retain explicit evidence and permission requirements (Must)

As a reviewer I need every original scope mapped so an omitted gate cannot become a pass.

1. WHEN policy is inspected THEN every current full release ledger row shall map to a required gate, later publication scope or explicit deferred host observation; Windows execution/denial/cancel/PTY/Hooks/snapshot/root authority, Linux22/24 isolation, seven-job integration, thirteen-job FINAL, five installed rows, topology and raw audits shall be separate concrete requirements
2. WHEN a row is inspected THEN fixed endpoint/artifact, nominal permissions, effective visibility, source/current-attempt binding, completeness, negative semantics and freshness shall be explicit
3. IF draft visibility, review provenance/permissions, post-merge integration invocation or original engineering evidence is missing THEN status shall remain unknown/blocked; no broader probe or dummy draft is allowed

### FR-3: Fail closed on submitted claims (Must)

As a maintainer I need a schema-valid record to stay separate from verified release evidence.

1. WHEN rows are missing/failed/unknown/skipped/wrong-source/wrong-tree/wrong-attempt THEN aggregation shall block with exact row reasons
2. IF every caller-supplied row says passed, a review string looks approved, or structural passed is true THEN aggregation shall still block because this phase implements no authentication producers
3. WHILE producing any result THEN release_approved and publish_approved shall be false and snapshot_atomic shall be false; no eligible branch exists
4. WHEN integration/consumer attempt is a positive integer including3 THEN its identity may be structurally valid; FINAL shall require attempt1 and exact job inventory, with artifact/source/current-attempt consistency

### FR-4: Preserve the structural record and honest receipt status (Must)

1. WHEN a receipt is decoded THEN the exact four payload names/sizes/digests, source/run/artifact bindings, original structural observations and bounded audit counts shall be represented without making an asset plan
2. WHEN collection observations are retained THEN collection status shall be unverified, eligibility blocked and finalization false; this phase cannot emit an actual successful evidence-collection receipt
3. IF structural blockers are unknown or original blocker text changes THEN fail closed; retain original observed bytes/text separately from gate results, never resolve a blocker using its passed flag
4. WHEN serialized THEN there shall be no arbitrary URLs, logs, credentials, filesystem paths, approval text or unbounded freeform fields

### FR-5: Prove narrow compatibility and isolation (Must)

1. WHEN tests run THEN adversarial schema, identity, missing-row, spoofed-approval, source/attempt, permission/draft/review and inventory cases shall execute with zero skips
2. WHEN old fixtures rerun THEN all159 consumer and208 required producer/stable regressions shall remain passing without old source changes
3. WHEN workflow is inspected THEN it shall run only fixtures on Ubuntu24/Python3.12, with pinned actions, contents-read only, no live token passed to scripts, no release/tag/dispatch/upload step

## 非功能需求

- NFR-1: Every new Python module remains below500 lines; bounded JSON input is at most256KiB and all inventories have fixed limits
- NFR-2: No network, subprocess, environment mutation or filesystem write in runtime contract modules; no authentication escape hatch
- NFR-3: Existing consumer and producer files remain byte-identical; independent implementation review and exact-source hosted fixtures remain separate from local success

## 依赖关系

Standard library dataclasses/JSON; read-only reuse of fixed source constants only when appropriate. Policy references committed ledger/workflow contracts. Live producers, actual invocation provenance, known-draft proof, exact-tree review provenance and genuine final source remain unavailable and explicitly blocked.

## 检查清单

- [x] FR1–FR5 define testable fail-closed acceptance; no release authority is granted
- [x] Scope is this additive phase only; unrelated security work is excluded

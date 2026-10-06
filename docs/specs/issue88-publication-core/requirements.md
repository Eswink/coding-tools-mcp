# Requirements: reusable RC publication core

## 功能概述

Implement the pure decision/sequencing core of the future Issue88 publisher at N `e459c9bec1dc6006eaad6df5f65111491c7b7572`, tree `1eae7b72539740c2a1cc167a82ec2af3b5f951d6`. This increment cannot perform I/O or grant publication authority. Owner 0.7.0 RC intent is settled; the exact canonical version/tag is an explicit frozen input, not a version edit.

## 用户故事

As the maintainer, I need one reusable engine to decide every draft/upload/verify/publish transition, so a later authenticated adapter executes closed intents instead of duplicating publication policy or inventing retries.

## 需求列表

- FR-1: Expose pure start, advance and request_publish APIs with immutable bounded records, one outstanding operation, exact operation/result/subject binding, and no generic command, URL, path, callback or persisted-state importer
- FR-2: Reuse the actual consumer payloads(version) contract and its six-asset plan identity; preserve original provenance, blockers and false approval fields without duplicating archive/evidence authentication
- FR-3: Freeze repository/source/tree/version/lightweight-tag, FINAL/integration/consumer and artifact/plan identities, plus stable/latest identity; repeated fences compare that subject without reselecting a newer success
- FR-4: Sequence existing-tag-only draft creation, six ordered nonoverwriting uploads with individual downloaded-byte verification, final exact inventory, explicit publish request, fresh admission fence, prerelease publication and public verification; bound the modeled happy path to 25 intents
- FR-5: Keep authentic full admission, staged-byte ownership and current action-scoped owner authorization external to the engine; a PublicationRequest or fixture record is never permission. A later adapter must call this same engine and recheck authorization/cancellation immediately before every mutation
- FR-6: Fail closed on malformed/stale/duplicate/out-of-order events, collisions and missing or changed facts. Distinguish no-effect blocking, partial draft, sticky uncertainty and published-but-unverified; never retry, overwrite, delete, compensate or silently clear uncertainty
- FR-7: Preserve all final Windows/security/snapshot/package/source gates. Every source-only report keeps release_approved, publish_approved, snapshot_atomic and live_publication_verified false; modeled success proves no remote atomicity or live no-implicit-tag property
- FR-8: Integrate through a separately pinned finite composition profile: structural S=[N] is not admissible; C=[S], I=[N,C] with tree C, J=[R,I] with only the four existing pinned R documents. Preserve all historical profiles/pins and exact 233 IDs, adding exactly 30 core and 20 guard tests

## 非功能需求

- Exactly 15 approved cumulative paths; immutable S source delta at most 1340, combined guard/ancillary delta at most 1050, all final files at most 500 lines and tighter individual caps
- Bounded integers reject booleans; fixed sanitized result codes exclude raw errors, credentials, signed URLs and freeform logs
- Confirmed pre-dispatch cancellation produces no mutation; uncertain post-dispatch cancellation stays uncertain. An outstanding intent does not authorize stale execution
- No live adapter, CLI, I/O, dependency, credential, version, producer, consumer or production-runtime changes; only the two existing hermetic strict/contracts workflow timeouts change from 15 to 20 minutes
- Preserve both complete workflow byte sequences through exact timeout inverses, all original 283+452 test IDs, historical pins and immutable S source pins; separately pin the six ancillary replacements

## 依赖关系

Reuse existing consumer payload names/media types, snapshot identity contracts, final gate IDs and immutable Git composition helpers. A future adapter must supply authenticated facts and safe upload handles independently; neither a retained path nor a local result is ongoing ownership authority.

## 验收标准

When the pure engine receives any input, it SHALL satisfy every applicable invariant below; missing or mismatched facts SHALL block the relevant transition.

- Exact 30 core cases exercise the 25-intent trace, negative identities, six byte checks, external authority boundary, all failure phases and terminal behavior
- Exactly 283 source-declared, loaded, executed and independently discovered strict IDs occur once; historical 233 and old 452 regressions remain unchanged, with no skips or expected-failure substitutions
- Full trees, ordered parents, modes/blobs/digests/bytes/lines, per-file and aggregate budgets, five original adapter inverses plus the separate ownership inverse and the externally bound profile self bytes pass independent review
- Repeated pure calls create inert decisions only; no public entry point executes a mutation or authenticates owner permission
- Staged impact, Probe/spec/review/gencommit gates and source-bound tests pass before separately authorized publication

## 不在范围

Live GitHub draft/upload/tag/release operations, write-capable workflows, real FINAL admission, credentials/access, current version changes, production deployment, PR98, cancelled Issue86 retries and snapshot work are excluded. Remote race/ownership feasibility and full publication admission remain prerequisites to later live enablement.

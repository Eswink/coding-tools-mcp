# Design: reusable RC publication core

## 对应需求

FR-1 through FR-8 define one inert engine and one exact composition amendment, approved together before implementation.

## 概述

Reuse rc_artifact_consumer.payloads(version) and project its six rows into AssetPlanView; do not change the consumer, snapshot, transport, finalization, policy or eligibility modules. PublicationSubject freezes exact source/tag/evidence/plan and stable/latest identities. These ordinary immutable records are not cryptographic capabilities.

The later live adapter must invoke start(subject, plan), advance(state, result) and request_publish(state, request) unchanged, execute only their closed intents, and never recreate ordering, readiness or retry policy. This increment contains no such adapter or I/O entry point.

## 技术方案

### 数据结构与接口

- Transition returns immutable state plus exactly one Operation, AwaitPublishRequest or terminal outcome
- Closed intents: ObserveFence, CreateDraft, ObserveDraft, UploadAsset, VerifyAsset, PublishPrerelease, VerifyPublished
- Closed results: FenceObserved, DraftCreated, DraftObserved, AssetUploaded, AssetVerified, PrereleasePublished, PublishedVerified, OperationFailed, OperationUncertain
- Every result echoes exact operation ID, subject digest and expected kind; finite field validation rejects booleans as numeric IDs, wrong types, extra fields and unbounded values
- PublicationRequest binds request ID/reference, exact draft ID and subject; it requests progress but does not authenticate or authorize it
- Results contain only bounded sanitized facts/codes, no credentials, raw errors, signed URLs, arbitrary bodies or executable paths
- The transition/request context digest binds the frozen subject together with all six projected asset rows; this does not independently authenticate the original consumer plan bytes

## 状态转换

1. Start emits a full before-draft fence: frozen admission/source/tag/evidence, proven complete collision visibility, stable/latest identity and staged bytes
2. Matching fence with no collision emits CreateDraft for the already existing lightweight tag, draft=true, prerelease=true, latest preserved
3. Bind the returned draft ID and observe that same empty draft with unchanged subject/tag/latest
4. For each of six fixed ordinals: fresh fence, UploadAsset, VerifyAsset using downloaded size/hash; bind unique returned asset IDs
5. Observe the complete draft again; require exactly six verified identities and return AwaitPublishRequest without polling
6. A matching explicit request emits a fresh before-publish fence, then PublishPrerelease for that exact draft
7. Confirmed publication emits VerifyPublished, requiring exact public metadata, anonymous six-asset byte/hash checks and stable/latest unchanged
8. Successful final verification terminates as a modeled result, with all four real-world approval/atomic/live flags false

The happy path emits 25 intents. Every fence compares the same frozen subject; it never reselects source, a newer successful run or another release. Existing drafts/assets/releases are collisions, not resumable ownership. Tag creation, stable promotion, overwrite/delete and compensation operations do not exist.

## 授权和失败边界

Authentic final admission, byte-handle ownership and external action-scoped owner authorization are independent prerequisites at the later live executor. It must recheck current authorization and cancellation/revocation immediately before every mutation, including an already emitted publish intent. Neither fixture facts nor local booleans, JSON, consumer success or PublicationRequest establish permission. Draft/upload permission and public publication permission remain distinct scopes.

Historical pre-tag absence stays evidence at its original phase; a later post-tag fence requires the existing exact tag, not simultaneous absence. Current tag existence does not prove prior admission. Full existing gate IDs and source/evidence identities remain required; no missing authenticator becomes a pass.

Failure before confirmed mutation is blocked_no_effect; failure after a confirmed draft/upload is partial_draft with known IDs retained. Unknown mutation outcomes are sticky uncertain_remote_effect, with no automatic retry/read-based clearing. Confirmed publication followed by failed verification is published_unverified. Confirmed cancellation before dispatch has no remote effect; cancellation after possible dispatch is uncertain. The core classifies transitions; the future adapter owns transport/descriptor cleanup; an external controller owns authorization and recovery decisions.

Existing-tag-only and preserve-latest are required intent/observation invariants, not proof that a future remote API cannot race or implicitly create a tag. Later adapter review must establish those actual mutation constraints. No remote transaction or atomic snapshot is claimed.

## 文件结构与预算

Source S, sole parent exact N, adds five mode100644 files, at most 1340 changed lines and 1683 tracked entries:
- scripts/rc_publication_contract.py: final/delta 460 (approved measured closed-state validation amendments)
- scripts/rc_pretag_publication_contract_tests.py: final/delta 500
- docs/specs/issue88-publication-core/requirements.md: final/delta 120
- docs/specs/issue88-publication-core/design.md: final/delta 180
- docs/specs/issue88-publication-core/tasks.md: final/delta 120

Candidate C, sole parent S, changes exactly seven guard paths, at most 1050 changed lines and 1685 entries:
- scripts/rc_pretag_composition_tests.py: final 500/delta 24
- scripts/rc_pretag_desktop_tests.py: final 400/delta 36
- scripts/rc_pretag_nginx_tests.py: final 480/delta 44
- scripts/rc_pretag_two_hop_tests.py: final 500/delta 44
- scripts/rc_pretag_authenticated_two_hop_tests.py: final 500/delta 100
- new scripts/rc_pretag_publication_profile.py: final/delta 400
- new scripts/rc_pretag_publication_tests.py: final/delta 500

The authenticated adapter starts at 477 lines; 23-line headroom is an estimate, never permission to minify, lose assertions or exceed the cap. Stop for a reasoned scope amendment if the frozen scope cannot fit.

## 精确组合

Profile engineering/issue88-publication-core-composition-v1 accepts only C=[S], I=[N,C] with the entire C tree, and J=[R,I] with the four exact historical R-document replacements. S and [N,S], arbitrary descendants, correction chains, nested/reversed/extra/duplicate parents and same-tree impostors fail.

Freeze N SHA/tree/parents and validate it through the unchanged authenticated profile. Freeze S SHA/tree plus full five-source pins; six non-self guard pins and an external independent manifest bind all seven guard paths including profile self bytes and the full tree. No self-hash cycle or historical repinning is introduced.

Only genuine topology mismatch permits profile dispatch fallback. Once topology selects, all content/pin/budget failures are terminal. Five exact-once adapter inverses recover N bytes. Only the frozen methods, one composition import and disjoint EXPECTED_GROUPS extension may change; all existing method IDs/assertions and Git/inventory helper implementations remain intact.

## 测试和证据

The approved external packet freezes 30 PublicationContractTests and 20 PublicationCompositionTests names. New50 digest: 6cc0bc92f8a9e8bf329dc81bfb8033ef0739a731454c73995dc31713039faaf5; strict283 digest: 8c511a659163f2e88a60246b95f9fbf077efde6d1679f28814ca014a48b3a907. Historical233 digest remains 7103bfa9167d9ec365ab7a6e111de4de226bfd70b7e578cef74d85d567d67765. These are frozen proposed inventories, not execution claims.

Run exact source-bound strict283, independent discovery and old452 regressions with zero skips; preserve named versus count-only hosted evidence. Independent reviews inspect the real engine, all branches, adapter inverses, pins and entire candidate shape. Existing native/hosted proof stays bound to its original source; no production or real publication approval follows.

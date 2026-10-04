# 设计文档：issue88-pretag-adopter

## 概述
FR-1 through FR-7 implement one phase adapter over J, using Python standard library and the retained production validation sequence. Root-reviewed v2 design SHA256 `ed36e36a9c546a05e3b0aa2c24f44e81e002be7017a19bb4cb8a52799bf9471a` governs the bounded increment.

## 技术方案
### 架构设计
actual Actions identity → local/live admission → nonauthoritative discovery → strict frozen selection/artifact → TrustedProducer → shared transfer/ZIP/checksums/TAR/contracts → staging closes → repeated full source/run/artifact fences → sanitized in-memory record → owned report close → anchored output handoff.
Only rc_consumer_snapshot.select_source_runs and rc_artifact_consumer.consume are mechanically extracted. `_select_source_runs_for_identity` owns duplicate pure expectation/source/positive-repository checks and the retained selection body. `_verify_bundle_bytes` owns the exact retained transport through membership sequence. Existing globals/test seams stay in their modules. Original callers retain input/error order (FR-1, FR-4).

## 数据模型
Use immutable SourceIdentity/InvocationIdentity and a private frozen admitted source/invocation snapshot. Live active run excludes mutable updated_at while validating timestamps at each read. Freeze numeric active job ID and attempt; compare live exact attempt endpoint. Discovery values are expectations, authenticated again without replacement (FR-2, FR-3).
Audit/policy/content sanitizers prepare a private `_PreparedObservation` before staging closes and final freshness reads. Only afterward does `_collect` mint and serialize the final observation. Private CollectedPreTagEvidence is a code-structure boundary, not a malicious-same-process or cryptographic capability. It stores only validated serialized bytes after every fence. It has no decoder, public authenticated boolean, imported receipt/plan, arbitrary callback or CLI output destination. False approval fields and blocked legacy policy inventory are separate from bounded byte verification (FR-5).

## API 设计
- admit(root, environment, api): verify actual local/live pretag identity; return immutable admitted snapshot
- discover(api, admitted): existing successful_run/bundle_metadata; freeze expectations then strict authenticate
- collect(root, environment, api, *, opener=None): real private byte pipeline and fences; production opener always None
- main(): GH_TOKEN pop first, fixed source root, validated RUNNER_TEMP, one owned output file and anchored GITHUB_OUTPUT
- Fixed tag observation calls unchanged base gate.GitHub.get for strict constructed suffix; typed403/404 response closes before unknown, every other failure terminal

## 文件结构
All22 paths and limits are enumerated in tasks; retain every other J blob/mode. Eight adopted paths are exactly70aa, including fixture-only historical workflow. No source manifest is generated.

## 设计决策
### 决策1: Truthful push identity (FR-2, FR-3)
No workflow_dispatch shortcut or fake consumer projection. Use only truthful source_sha/source_tree/version projection for retained producer construction; no fake tag or post-tag provenance/finalization.
### 决策2: Bounded collection without approval (FR-5)
Only local tag absent is proven. Remote403/404 remains unknown/denied visibility and never clears tag absence policy. Global release/publish/security/published/finalized/atomic fields false; original blockers remain.
### 决策3: Failure and output ordering (FR-6)
Pop GH_TOKEN before inherited subprocesses, use only fixed API/private worker pipe, drop token references after final reads. Report root outside source is fresh0700; exact rc-pretag-observation.json0600 is written exclusively and completely, fsynced/read back/hash checked with exact inventory, then closed. Register one <=4096-byte absolute path only after close by existing-file nofollow traversal anchored beneath validated RUNNER_TEMP, single-link/owner checks and append/fsync/close. No retry or recursive deletion.
Closed stages: invocation/source/tag_visibility/selection/artifact/transport/archive/contracts/freshness/output/output_handoff. Closed error vocabulary and exact failure fields follow reviewed requirements; uncertain transport teardown remains primary even if output/close later fails. Exceptions/raw bodies/token strings are never serialized.
### 决策4: Honest time bounds (FR-6)
Workflow15-minute outer timeout cannot preempt blocked Popen/kernel I/O synchronously. Metadata30-second socket operations are not absolute session deadlines. Existing300-second transfer plus5-second cleanup is cooperative at synchronous operations. Platform killed/cancelled/missing exit is failed/unknown, never cleanup or success evidence. Success upload predicate is success() && !cancelled() && collect.outcome=='success'; artifacts from later failed/cancelled run/job remain inadmissible.

## 测试策略
FR-1 inverse bytes and exact adopted/source/mode gates; explicit duplicate helper validation and old malformed-input ordering. FR-2/3 temporary Git/live inert API identity/tag/run/job/artifact mutations, typed failures and close faults. FR-4 real ZIP/TAR/contracts positive plus ordered failure-edge traces and frozen-fence drift. FR-5 no receipt promotion, strict sanitizers/enum/nonfinite/size tests. FR-6 credential subprocess checks, file/control ownership/TOCTOU/write/fsync/readback/close/cancellation/uncertain teardown tests. FR-7 actual discovery IDs, unchanged J412/adopted53, frozen new inventory, workflow hash and trigger envelope.

## 风险评估
Manual HIGH authentication/lifecycle risk, dynamic/new-workflow graph UNKNOWN. Fresh exact-symbol impacts before edits and independent frozen review required. J missing reviewed manifest is intentional live blocker. No broader whole-session supervisor, transport change or hold integration is in scope.

## 检查清单
- [x] Existing pipeline, honest evidence scope, failure ownership and finite source budget specified

## Reviewed source profiles and fixture ownership
Pure feature validation reads immutable candidate entries and retains J-first-parent/preservation/adoption/extraction/budget guards. Synthetic requires exactly[R,candidate], validates candidate using only pure profile, then compares the complete candidate map plus four exact100644 R docs to the actual tree; R is not the general baseline. R tree c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3 and four document blobs are pinned in composition tests. Worktree and unique-stage0 index bind to selected tree.
A scoped test-owned Popen delegate starts before PreTagFixture construction in Admission/Collection setup and is registered for cleanup immediately; OutputLifecycle inherits it. Additional temporary roots, including unchanged PlanTests construction, register before Git calls. Known -C normalizes to owned cwd; escaped/shared metadata and context overrides reject before launch. No import-time patch, whole-process Git context, original-helper edit or arbitrary-process sandbox claim.
Each actual Git launch copies its effective env (including env={}), removes inherited GIT_* and installs fixed child-only GIT_CONFIG_GLOBAL/SYSTEM=/dev/null, NOSYSTEM, NO_REPLACE_OBJECTS and OPTIONAL_LOCKS controls plus per-command hook/fsmonitor disabling. No machine/repository config edit occurs. Non-Git launches and other variables pass unchanged; the existing outer token-pop observer asserts before this delegate and cannot be masked by Git sanitization.
Source inspection has a separate bounded read-only Git envelope. Context fixtures use independent owned repositories/object-store copies; no linked worktree/common directory or alternate objects. Sentinel metadata remains unchanged in adverse-context regressions. Original412 outside these scoped new tests needs externally sanitized launch.
Same22 cumulative paths/eight corrected files; runtime/adoption blobs unchanged. Strict130 and unique542 require actual fixed IDs/execution with no skipped/xfail/xpass. Global3966/runtime640 remain independent hard gates; manual HIGH/dynamic UNKNOWN and independent frozen review remain.

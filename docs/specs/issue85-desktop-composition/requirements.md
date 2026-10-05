# 需求文档：issue85-desktop-composition

## 功能概述
Add engineering/issue85-desktop-composition-v1 as a separate test-only profile. It validates the reviewed desktop additions and finite integration shapes while preserving the historical ownership profile. It does not grant release eligibility or transfer native evidence between source identities.

## 历史经验与坑
At immutable S=932c48d07ccfc49c312f6ee9b7ffc0ea19c65fe8, the desktop native proof passed but the old composition gate rejected the new branch as nonpure_chain. After restoring missing fixture objects,146 of147 old composition cases passed and only the current-tree profile failed. A valid tree never repairs malformed parents; a validator cannot embed its own final cryptographic hash.

## 术语定义
X=44ff88373d76b54a22d72eba17c0c7989e0be805 is the reviewed PR89 baseline; R=e2e011f7f2a3a1df838bbd588106205b999db610 is the fixed release comparison anchor. S is the immutable desktop proof source; P is one finalized amendment child of S; F=[X,P] is a feature merge; L=[R,F] is a release-overlay test object. These are engineering identities, not publishable release designations.

## 范围边界
Exactly six amendment paths: one composition-test adapter, one new profile, one new20-test module and three specifications. Keep the13 desktop files, ownership profile/tests, workflows, runtime, dependency/version inputs and release/security policy unchanged. No generic ancestor acceptance, gate skip, AppImage work, installed acceptance, live FINAL action, tag or Release publication.

## 需求列表
### FR-1: Preserve historical contracts
Priority: Must. WHEN the legacy topology classifier accepts THEN the unchanged legacy content validator SHALL decide; IF legacy content fails THEN the failure SHALL be terminal. Existing147 test IDs and all bodies except the explicitly reviewed current-tree assertion SHALL remain unchanged. Validate X through ownership.selected_profile with historical=_feature_profile, never by invoking _feature_profile directly on X.

### FR-2: Classify only closed parent shapes
Priority: Must. WHEN selecting THEN resolve the input ref once to an exact commit before either route. The desktop route SHALL accept only exact S with its fixed sole-parent prefix to X, one P=[S], F=[X,S or P], and L=[R,F]. IF parents are missing, reversed, duplicate, extra, foreign, tree-equal impostors, nested, rebased, squashed or postmerge descendants THEN topology SHALL fail before content reads. No recursive release dispatch.

### FR-3: Bind exact content and modes
Priority: Must. WHEN validating S THEN all1632 X entries SHALL stay exact and exactly13 fixed blob/hash/size/line/mode additions SHALL appear. Only the fixed collector may be100755; other additions/amendments SHALL be100644. P SHALL change only the six bounded amendment paths, with five acyclic full-file pins. F SHALL equal its validated second-parent tree; L SHALL add only the existing four pinned release documents.

### FR-4: Require an external trust anchor
Priority: Must. WHEN accepting amended profile code THEN independent review SHALL freeze its exact bytes plus every amendment identity and actual P/F/L source/tree/parents in an external review lock. Its own bounds SHALL NOT be described as cryptographic authentication. IF that lock or exact candidate changes THEN affected review/tests SHALL repeat. No self-hash, copied candidate allowlist or automatic approval from an earlier lock.

### FR-5: Execute exact adversarial inventories
Priority: Must. WHEN running pretag tests THEN preserve147 original unique IDs and add exactly20 named tests, yielding167 actual loaded/executed IDs with Counter equality and zero skip/xfail/xpass. Parent negatives SHALL independently validate correct content before proving topology failure. Valid-parent content/mode/path/pin/budget mutations SHALL fail. Actual P/F/L SHALL run all hermetic commands before publication and merge.

### FR-6: Preserve source-specific native evidence
Priority: Must. WHEN publishing approved P on the existing PR113 ci branch THEN a fresh native workflow SHALL be expected and its results authenticated independently. S's successful run37265448784 SHALL remain historical. P/F/L SHALL never inherit that native receipt. Installed/security/release/publish/raw-zero and native-linker/retained-code claims remain false. Root approval gates exact implementation, publication and merge separately.

## 非功能需求
Profile≤360lines, new tests≤400, composition adapter≤500total/40delta, each spec≤80, total amendment≤1100added+deleted lines. Keep existing M-relative caps. Owned independent Git object stores only, no alternates; sanitize inherited GIT_* and disable hooks/fsmonitor/automatic maintenance in fixtures. Missing fixture objects block rather than skip.

## 依赖关系
Reuse read-only Git/entry callbacks, unchanged ownership profile and owned fixture constructors, exact S desktop pins, the existing four RELEASE_DOCS and checksum-pinned official GLib test data. No new package, network permission or persistent credential.

## 验收标准
All FR-1..FR-6 conditions have measured evidence; old red preserved; actual P/F/L full hermetic checks and malformed-parent/valid-content cases pass; exact external review lock accepted; fresh P-native CI and artifacts authenticated; source-specific flags stay honest. This profile alone cannot close Issue85 or authorize PR89 into release/main.

# 设计文档：issue85-desktop-composition

## 概述
Covers FR-1..FR-6 with an explicit union of unchanged historical composition and a versioned desktop engineering profile. Root selected reuse of PR113; publishing new P on its ci branch intentionally starts a fresh native run. This design does not authorize a merge or publication by itself.

## 技术方案
### Identity and topology (FR-1,FR-2)
Freeze X44ff/tree032a07be2622e4d2cf475180de650dcb2d819ac4, S932c48d/tree40d8139e7b265d7c7c9b3c12bf1bdaf5fa96d19f and Re2e/treec0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3. Verify the exact prefix X→69e325c3793ebb0747673c59096848540254a5f8→8d1cebf82951e14b197083d39c13257c17755e27→S, each sole-parent edge.
Resolve candidate ref once. Try unchanged legacy topology; on its TopologyError only, attempt the closed desktop grammar. Legacy content failure never falls back. Validate X with ownership.selected_profile(..., historical=_feature_profile), preserving its original M/C/H guarantees.
Accept exact S; one finalized P with parents[S]; feature F with parents[X,S or P]; or release overlay L with parents[R,F]. No generic ancestry search, arbitrary descendants, amendment chains, wrong first parents, nested F/L, squash/rebase or recursive release parsing. Bind every tree read to the resolved object after parent acceptance.

### Content and trust bootstrap (FR-3,FR-4)
DESKTOP_PINS are fixed reviewed literals for all13 S additions: modes, Git blobs, SHA256, sizes and line counts. Validate exact X through its old profile, then entries(S)=entries(X)+those13 and exact S tree. Preserve every historical entry. Only scripts/desktop_glib_build_evidence.py is100755; all other desktop additions are100644.
For P require exactly one modified composition adapter and five added100644 amendment files. Finalize adapter/tests/specs first, then pin those five complete byte identities in the profile. This is an acyclic hash dependency. The profile cannot pin its own final bytes or commit; a separate independently accepted external review manifest binds its exact blob/hash, all six amendment paths, actual P/F/L identities and test evidence. Its internal line/path budget is only a scope guard, never self-authentication.
Require the adapter's exact inverse reconstruct the frozen X composition file, retaining all old test bodies except the approved current-tree assertion and retaining147 old IDs. The new profile's trust derives from exact external review, not a candidate-derived success flag. Unknown amendment paths, mode drift, stale pins, caps exceeded or changed desktop bytes reject.
F's complete entry map must equal its validated second parent's map. L reuses ownership.release_content with fixed R and exactly the four existing RELEASE_DOCS; no fifth document or merge-resolution mutation. The current-tree test checks full stage0 index, regular files, blob bytes and executable bits against the validated per-path mode.

## 数据模型
PROFILE_ID=engineering/issue85-desktop-composition-v1. Immutable X/S/R identities, exact prefix, DESKTOP_PINS, five AMENDMENT_PINS, explicit AMENDMENT_CAPS and named EXPECTED_GROUPS are data-only constants. Profile output is a validated Git entry map, not native/security/release approval. The external exact review lock is outside candidate source and is mandatory before merge.

## API 设计
New helper functions desktop_topology, desktop_content, amendment_content and selected_profile consume read-only Git/entries callbacks. No network, filesystem writes, process launch, ambient-ref trust or import-time work. Legacy ownership functions stay byte-identical. The composition adapter imports the explicit union selector, checks per-path modes and extends the exact named inventory without overlapping groups.

## 文件结构
- Modify scripts/rc_pretag_composition_tests.py only at the reviewed selector/mode/inventory adapter,≤500total/40delta
- Add scripts/rc_pretag_desktop_profile.py≤360 and scripts/rc_pretag_desktop_tests.py≤400
- Add docs/specs/issue85-desktop-composition/requirements.md,design.md,tasks.md, each≤80
Exactly six amendment paths; total delta≤1100. All13 desktop files, historical ownership code/tests and all workflows remain unchanged.

## 设计决策
Do not append desktop files to old CAPS, weaken old mode checks globally or catch a legacy content failure. The old profile remains independently useful. V1 allows one finalized amendment commit; later correction chains require another reviewed profile rather than silent broadening. Finalize specifications before acyclic pin creation; record completion evidence externally instead of changing pinned documents after review.

## 验证矩阵 (FR-5)
Preserve the authentic old red at S/F0. Build actual local Git objects for P, F=[X,P], L=[R,F], clearly label local versus GitHub-created identities, and run every hermetic command in each clean context. Re-read actual published/merge objects; any changed parent/base/tree invalidates affected evidence. Do not equate a projected L with a later GitHub synthetic commit.
Retain147 IDs and add20 exact DesktopCompositionTests IDs; both discovery and run_inventory must execute167, with no skip/xfail/xpass/duplicate or inventory mismatch. Parent-negative fixtures must first pass independent content-only checks, then prove topology rejects before content access. Cover same-tree impostors, wrong/reversed/duplicate/extra parents, roots, nesting and descendants.
With valid parents, mutate each of13 desktop blobs, every path/type/mode, the collector's execute bit, historical entries, four release documents, five amendment pins, individual and total budgets. Verify inverse adapter reconstruction, old inventory identity, Git-context isolation and false claim boundaries.
Run the existing consumer244 inventory, every release/dependency/package suite from the three hermetic workflows, release-version regressions, all four immutable desktop suites and official GLib source tests. Record exact commands/exits/IDs/counts/log hashes; overlapping invocations are not additional unique tests. Compile bytecode externally; check applicable syntax, index, source status and external review lock.

## CI 与合并边界 (FR-6)
The six-path rc_pretag* amendment triggers the three existing hermetic PR workflows. Existing PR113 ci branch also triggers the unchanged native proof workflow, with no paths filter. Expect and authenticate the new P-native run, both immutable artifact IDs/upload digests/job-attempts/raw ZIPs, independent data-only replay and actual-byte negatives. Never replace it with S's receipt.
Keep PR113's target fixed at X until final root approval; do not merge PR89 into R/main. Verify actual P/F/L contexts before publication, review the exact candidate, and preserve a mandatory final merge gate. Postmerge PR89 R-synthetic checks must be observed before any later PR89 action. No workflow dispatch, FINAL, tag, Release, permissions or production credential change.

## 风险评估
HIGH trust boundary despite test-only code. External exact source review authenticates the new validator; it cannot certify itself. Unexpected files, topology, test failures or native-output disagreement stop for review. All installed/native-linker/retained-code/security/release/publish/raw-zero exclusions remain unchanged. AppImage/system libraries and Issue86 remain separate open work.

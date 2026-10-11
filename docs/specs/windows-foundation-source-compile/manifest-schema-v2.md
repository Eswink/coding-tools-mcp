# windows_foundation_source_manifest.json — schema 2

## Decision: exact73 / frozen chain stays FIXED
Consumers (guard load_manifest/restore_source/verify_materialized, union_overlay and inference_overlay via
`baseline['whole_source']`, source_compile.ps1, manager_observation, workflow) use exact73 as the immutable
recovery lease: 73 `<path>.source` blobs from 47adc2a1 overlaid on c60f9667 = d4bd2d98/1913, then FULL43
(155eafad) = frozen SUT 19bb2920/1953. FULL43 is defined relative to exact73, so tracking the layer commit would
break the chain. v1 field names keep their v1 meaning (renaming would churn 5 consumers); the layer commit is
described by new fields.

## Fields
| field | v | meaning |
|---|---|---|
| schema | 2 | int 2. 1 admitted only on frozen historical commits (see No-downgrade) |
| repository, base_commit, base_tree_files | 1 | Eswink/coding-tools-mcp, c60f9667, 1849 (fixed) |
| exact73_backup_commit, exact73_prefix | 1 | 47adc2a1, recovered-exact73 prefix; payload stored as `<path>.source` (fixed) |
| exact73 | 1 | 73 rows {path, mode, blob, bytes, sha256}, UTF-8 byte-sorted, suffix stripped (fixed) |
| exact73_tree, exact73_tree_files | 1 | d4bd2d98 / 1913 = base tree + exact73 overlay (fixed, derived) |
| full43_backup_commit, full43_patch_path, full43_patch_sha256, full43_patch_bytes | 1 | 155eafad, FULL43 patch, 3d3e83dc…, 167168 (fixed) |
| target_tree, target_tree_files | 1 | **frozen SUT** 19bb2920 / 1953 (name kept for consumers; commit 47659171 on backup/rc070-frozen-19bb2920-20261011) |
| whole_source | 1 | rows of the frozen SUT tree (used to verify the restored SUT) |
| protected_positive_path, protected_positive_sha256 | 1 | wss_workspace_io_tests.rs in the frozen SUT |
| qualification | 1 | status string |
| excluded_paths | 2 | `["scripts/windows_foundation_source_manifest.json"]` = guard.LAYER_EXCLUDED |
| target_tree_excluding_manifest | 2 | tree of the layer commit with excluded_paths removed |
| target_tree_excluding_manifest_files | 2 | len(layer_source) |
| layer_source | 2 | rows {path, mode, blob, bytes, sha256} of that tree, UTF-8 byte-sorted |

## target_tree_excluding_manifest algorithm (guard.tree_excluding; generator and guard both call it)
1. fresh temp `GIT_INDEX_FILE`, all other `GIT_*` env stripped, `LC_ALL=C`;
2. `git read-tree <commit>^{tree}`;
3. for each excluded path: `git update-index --force-remove -- <path>` (index-only; `git rm --cached` was rejected because it consults the worktree and refuses when worktree/index/HEAD differ, making the result worktree-dependent);
4. `git write-tree`.
Rows: `ls-tree -rz` of that tree, regular blobs only (100644/100755), byte-sorted, bytes/sha256 from `cat-file blob`.

## Self-reference
No tracked file pins the manifest's sha256 or blob (searched full sha256, 16-char prefix, blob id and 12-char
prefix at the layer commit). verify_manager hashes the manifest dynamically from HEAD (not a pin). The only
cycle is the manifest itself, removed via excluded_paths. Fixed point: generate -> commit -> generate is identical.

## No-downgrade
load_manifest(path, repo, commit): schema must be int 1 or 2. Schema 1 only if `commit` is an ancestor-or-equal
of 313c3a16 (V1_FROZEN_LAST) AND `commit:scripts/windows_foundation_source_manifest.json` is blob 424a9b17
(V1_MANIFEST_BLOB). Otherwise (this layer and later, or no commit): reject "schema 2 required".

## CI
Go job: fetch c60f9667, 47adc2a1, 155eafad, 47659171 by SHA; regenerate with `--target-tree $GITHUB_SHA`;
`diff -u` against committed; `guard verify-layer`; run windows_foundation_manifest_v2_tests.py.

## Size breakdown (layer 138a51e3 successor; ~27,400 lines, approx. per top-level field)
| field | lines |
|---|---|
| 19 scalar v1 fields (schema … qualification) | 1 each, 19 |
| exact73 (73 rows × 7) | ~513 |
| whole_source — frozen SUT 19bb2920 (1953 rows × 7) | ~13,673 |
| excluded_paths | 3 |
| target_tree_excluding_manifest, _files | 2 |
| layer_source — layer tree excl. manifest (1885 rows × 7) | ~13,197 |
v1 was 14,205 lines (everything except the last three rows). Growth ≈ layer_source, i.e. two tree
descriptions coexisting: whole_source pins the frozen SUT (19bb2920) that restore/compile verifies;
layer_source pins this commit. No tree is pinned twice: each list is checked against a different tree hash.
Content overlap: 1836 rows are byte-identical in both lists (files unchanged between the frozen SUT and the
layer); that is the same blob appearing in two distinct trees, not a second pin of the same tree.

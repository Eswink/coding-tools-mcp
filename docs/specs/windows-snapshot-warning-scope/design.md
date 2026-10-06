# Design: Windows snapshot warning scope (#105)

## 概述

对应需求: FR-1, FR-2, FR-3, FR-4, FR-5.

## 架构设计

The filesystem module has distinct Linux and non-Linux Dir implementations. Only the Linux implementation uses Read/Write, stores or reads a File field, synchronizes directories, or constructs Busy. Non-Linux open always refuses; no successful constructor, ABI/repr contract, numeric enum cast or serialization of SnapshotError is present. SnapshotError is effectively crate-only through private module boundaries and pub(crate) reexports; Display formats derived Debug and the command adapter formats the error string.

## 数据模型

Dir retains its current File field on Linux. Non-Linux Dir becomes an internal empty struct, but receives no new constructor or Default. SnapshotError retains every reachable non-Linux error variant and its display spelling. Busy and its implicit discriminant are Linux-only; no persisted or IPC numeric discriminant exists. This representation review is required because the change is not purely cosmetic.

## 技术方案

1. Move io::{Read, Write} to the existing cfg(target_os = "linux") std import block. Keep collections::BTreeMap, fs::File and path::Path unconditional; rustfmt may collapse this touched unconditional declaration.
2. Apply cfg(target_os = "linux") only to Dir.file.
3. Delete only the three-line Unsupported sync stub from the non-Linux impl. Preserve the entire Linux impl byte-for-byte.
4. Apply cfg(target_os = "linux") only to SnapshotError::Busy.

Do not change any Linux body, remaining non-Linux body, model algorithm, test, adapter, authority or workflow warning severity.

## 影响面与风险

Historical donor GitNexus1.6.9 on exact c3 recorded 20,812 nodes,47,464 edges,922 communities,294 flows. Read/Write, Busy and the distinct non-Linux sync symbol are unresolved UNKNOWN. Dir.file and SnapshotError report zero despite real accesses/consumers, so completeness is UNKNOWN. Linux sync resolves only materialize/apply_directory_modes; manual mapping adds mkdir,write_new,move_new (eight call sites in five Linux methods). FTS is unavailable. No zero-blast-radius claim is valid.

Historical manual HIGH review covered shared capture/list/plan/restore paths, field representation, enum discriminants and cfg callers. Read is used only by Linux read; Write only by Linux write_new. All file accesses/initializers are in the Linux impl. Busy's only production construction is Linux lock and its test is already Linux-gated. The exact current candidate still requires focused independent review. Fresh6edd index and file-qualified impact confirm incomplete Rust cfg coverage; zero indexed callers is not no-impact proof. Current source selector has35 upstream symbols/6direct callers/2flows; manual HIGH admission review is accepted under terminal-failure, exact-inverse and immutable-pin conditions.

## 测试策略

Baseline native Windows strict compilation must show the four exact source diagnostics. Candidate Windows/Linux strict compilation, format and all-target checks are separate from runtime acceptance. Full existing native regressions and their inventories must run. The exact positive restore test is independently exercised and remains visibly failed on Windows Unsupported. Test success from unsupported_platform_has_no_filesystem_write_fallback proves refusal only.

## 回滚与边界

Revert only the isolated warning patch if needed; never move held integration refs or rewrite their jobs. Issue #86, Windows sandbox/snapshot functionality, Windows completion and release acceptance remain open. Historical donor native evidence remains source-scoped; fresh6edd baseline/current candidate runs are pending. Static preservation checks are not a compile claim.

## 文件结构

Exactly two production paths: src-tauri/src/workspace_snapshots/{filesystem,model}.rs. Three specification paths under docs/specs/windows-snapshot-warning-scope, the existing donor workflow, three existing guard files and one new case module complete the exact ten-path cap in requirements. Product test bytes are unchanged.

## Current adoption and finite composition (FR-5)

Base B=6edd4e6137a6947319183b3ac8801bfa608ac722, tree35cfad529c2427bac17c344089686b2cf3d46823; ordered parents[9c5c031d24aadc5d704160bb5a5a65bff126c10c,02ea77dda8d65ea15dd6b0ffbfce13aae800fc3f]. Exact donor Rust blobs are f3de379c5f107ddfe558fcdc885a344c71cf7054 and c639b79bf3d852e30d532a2a3e647d6dcd88b0ee. No donor ancestry is imported.

Append one warning block/dispatch to the existing publication profile. Admit D=[B], I=[B,D], J=[R,I] only; authenticate B through the existing historical selector and all original pins. Catch topology selection failures only; selected content errors, including TopologyError, are terminal. Bind nine non-self files and review the profile's full bytes externally.

The existing adapter helper restores complete B profile/helper/join-once-test bytes before invoking older inverses. Only finite explicitly normalized historical fixture/pin/inverse reads change; all20 old join-once IDs and assertions survive. No ROOT redirection, reader patching or historical test-body duplication. The497-line join-once file cannot grow; profile/helper caps500/300 and aggregate1500 are hard bounds.

Existing303 discovery and452 cases remain unchanged, with SHA256 digests0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125 andd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372. New20 canonical module-qualified IDs have digest94cd89ce8d62e001f8ec0e256dd031462cdbf8c34ed8edb06dd7189b52c42e75, serialized sorted with newline and no final newline.

The new filename does not match old discovery. One delimited Ubuntu step invokes python -B scripts/rc_pretag_snapshot_warning_cases.py, records command/output/exit and uses the unchanged InventoryResult; the script imports its canonical module-qualified class. The native workflow keeps existing permissions/events/jobs/timeouts/parsers. Only the push branch becomes fix/windows-snapshot-warning-scope-m6edd4e6, source binding becomes B/tree plus ten exact paths, and this step is added. Reversing those four groups must recover donor workflow blob a80db5b7f0848d071461bd507aba3efc84a58d49, SHA2564efaa35cfe031b8c793b92a8c51671e23f65fc7f5be29842e787320c2b144214,22443bytes/362lines without requiring that donor object.

All six later native gates retain always-after-preparation conditions. Known Windows five SANDBOX_REQUIRED failures and positive restore Unsupported (including independent positive invocation) remain genuine failures. Historical680/686 and746 counts are not frozen expectations for current source. Warning-only acceptance is separate from those unresolved feature and final-release gates.

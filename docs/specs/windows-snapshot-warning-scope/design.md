# Design: Windows snapshot warning scope (#105)

## 概述

对应需求: FR-1, FR-2, FR-3, FR-4.

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

Fresh forced GitNexus1.6.9 on exact c3 records 20,812 nodes,47,464 edges,922 communities,294 flows. Read/Write, Busy and the distinct non-Linux sync symbol are unresolved UNKNOWN. Dir.file and SnapshotError report zero despite real accesses/consumers, so completeness is UNKNOWN. Linux sync resolves only materialize/apply_directory_modes; manual mapping adds mkdir,write_new,move_new (eight call sites in five Linux methods). FTS is unavailable. No zero-blast-radius claim is valid.

Manual HIGH review covers shared capture/list/plan/restore paths, field representation, enum discriminants and cfg callers. Read is used only by Linux read; Write only by Linux write_new. All file accesses/initializers are in the Linux impl. Busy's only production construction is Linux lock and its test is already Linux-gated. Independent review remains required against the exact final candidate.

## 测试策略

Baseline native Windows strict compilation must show the four exact source diagnostics. Candidate Windows/Linux strict compilation, format and all-target checks are separate from runtime acceptance. Full existing native regressions and their inventories must run. The exact positive restore test is independently exercised and remains visibly failed on Windows Unsupported. Test success from unsupported_platform_has_no_filesystem_write_fallback proves refusal only.

## 回滚与边界

Revert only the isolated warning patch if needed; never move held integration refs or rewrite their jobs. Issue #86, Windows sandbox/snapshot functionality, Windows completion and release acceptance remain open. Native evidence is pending until actual runs; static preservation checks are not a compile claim.

## 文件结构

Exactly two production paths: src-tauri/src/workspace_snapshots/{filesystem,model}.rs. Three specification paths under docs/specs/windows-snapshot-warning-scope and the separately approved .github/workflows/windows-snapshot-warning-scope.yml complete the six-path cap. No test file edits.

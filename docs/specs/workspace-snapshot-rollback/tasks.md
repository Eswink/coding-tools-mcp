# Tasks: explicit snapshots

## 交付物清单
Snapshot store and adapter (5 files, each below 500 lines), native command and UI (2 files), regression tests and exact-source evidence. Scope implements FR-1 through FR-5 and keeps native/platform gaps visible.

## 任务列表

- [ ] 1.1 Implement bounded complete snapshots and safe filesystem handling
  - 证据块: existing src-tauri/src/harness/state.rs no-copy regression; worktree manager only registered detached roots, no execution lease; snapshot feature absent from delivery inventory
  - Files: src-tauri/src/workspace_snapshots/model.rs, filesystem.rs, mod.rs; under 500 lines each
  - _Requirements: FR-1, FR-2_; Design: Architecture and Bounds
- [ ] 1.2 Implement exact restore plans and retained transactional backups
  - 证据块: existing patch_transaction.rs is operation-local and cannot serve persistent rollback; outside writers cannot be excluded by manager Mutex
  - Files: src-tauri/src/workspace_snapshots/restore.rs, tests.rs; under 500 lines each
  - _Requirements: FR-3, FR-4_; Design: Data model and Architecture
- [ ] 1.3 Wire native approved managed roots and owner UI, test boundaries
  - 证据块: native lifecycle integration worker owns stopped/drained admission; no existing opaque managed execution lease
  - Files: src-tauri/src/commands/snapshots.rs, src/lib/components/WorkspaceSnapshots.svelte plus module mounts
  - _Requirements: FR-5_; Design: Native integration and Test strategy

## 需求覆盖矩阵
| Requirement | Task | State |
|---|---|---|
| FR-1 | 1.1 | Open |
| FR-2 | 1.1 | Open |
| FR-3 | 1.2 | Open |
| FR-4 | 1.2 | Open |
| FR-5 | 1.3 | Open |

## Completion gates
All synthetic filesystem and existing no-copy regressions pass; native integration proven; per-platform native CI clear; no incomplete restore hidden as success. Parent full RC scope remains unchanged.

## 文件变更清单
Snapshot module, native command, UI and test paths are listed with budgets in each task above.

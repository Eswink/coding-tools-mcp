# Design: explicit managed-worktree snapshots

## 概述

Native-only snapshots and retained rollback transactions.

## 技术方案
FR-1/FR-2: src-tauri/src/workspace_snapshots holds an independently testable bounded store, immutable manifests and path-safe filesystem adapters. Inputs are host-resolved targets, never arbitrary cloud paths. Capture stages content and publishes complete manifest last; reopening verifies all blobs, manifest constraints, root binding and content digest. Dot-prefixed control/credential directories and sensitive filename patterns fail closed except the top-level Git control file, explicitly excluded.

FR-3: Native commands obtain registered root and HEAD from the managed-worktree manager; dry-run returns only opaque identifiers, relative paths and hashes. A short-lived native-only non-deserializable lease binds the plan and workspace generation. Native approval is performed at operation time. Missing lease integration yields an explicit unavailable error before destructive writes.

FR-4: Restore stages a complete desired tree outside execution root. A durable prepared transaction precedes all moves. Top-level originals are moved without replacement into retained transaction backups; contents are revalidated after displacement before staged replacements are moved without replacement into the pinned root. Conflicting recreated paths are not overwritten. Any failure keeps the durable transaction and backup; restart detects it and refuses new mutations. Recovery never clears authority or journals and does not automatically overwrite files. Application execution is excluded by host lease; external edits are checked and preserved, not assumed excluded.

FR-5: Native commands and UI expose explicit capture, list, dry-run and confirm steps. Runtime integration uses native stopped/drained evidence. Native and browser tests are synthetic; library, native, Windows, Linux and actual host proof remain separate.

## Data model
SnapshotManifest schema=1: opaque id, workspace/worktree IDs, head, root identity, entries path/kind/size/hash/mode, total bytes, content digest. RestorePlan: opaque plan id and snapshot id, bound identities and current/snapshot digests, expiry, ordered changes. Transaction: complete preimage manifest, plan and prepared/completed markers, staged content and retained displaced originals.

## Bounds and platform decisions
256 entries, 1 MiB/file, 16 MiB/snapshot and 16 store objects per target. Refuse unsupported types and oversized snapshots. Linux uses no-follow directory/file handles and atomic non-replacing moves. Other platform adapters must prove equivalent traversal/link/concurrency safety before enabling writes. A missing adapter is a typed release-blocking unsupported result.

## 文件结构
src-tauri/src/workspace_snapshots/mod.rs, model.rs, filesystem.rs, restore.rs, tests.rs; src-tauri/src/commands/snapshots.rs; src/lib/components/WorkspaceSnapshots.svelte. Native module registration and managed-root/restore lease integration are coordinated with their owning worker.

## Test strategy
FR-1: roundtrip/empty/binary/mode/size/count/partial/corruption. FR-2: symlink/hardlink/protected/special/path traversal/root replacement. FR-3: expired/tampered/foreign plan and absent/invalid native lease. FR-4: add/update/delete, conflict after plan, injected mid-apply failure, restart refusal and backups retained. FR-5: native DTO/control route, UI cancellation and late response tests, no-copy existing test unchanged.

## Risks
Destructive restore is CRITICAL. OS lock is only operation serialization; native drain lease excludes application execution; outside editors can still change data, so retain displaced bytes and refuse conflicts. Do not mark unsupported Windows adapters or blocked native integration complete.

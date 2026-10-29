# Requirements: explicit managed-worktree snapshots

## 功能概述
Deliver parent cloud-execution-bridge snapshot gate snapshot/rollback gate. Explicit operations only; ordinary start_task must not create workspace copies.

## Scope
In scope: registered detached managed worktree identity, bounded local capture, complete hash manifests, corruption rejection, owner-approved dry-run-bound transactional restore, retained failure backups and native controls. Out of scope: original workspace rollback, cloud-driven approval, git reset/clean, credential/authority/journal changes, automatic recovery/retry, production/user-files testing.

## 需求列表
### FR-1 — Bounded capture (Must)
WHEN the native owner explicitly captures a registered managed worktree THEN the system SHALL produce an opaque snapshot ID and complete manifest binding workspace/worktree/root identity/HEAD to each file hash, size and mode, with a 256-entry, 16 MiB total and 1 MiB per-file limit. WHEN a capture is partial or changes during capture THEN it SHALL remain unusable.
### FR-2 — Safe paths (Must)
WHEN capturing or restoring THEN the system SHALL reject symlinks, reparse points, hardlinks, special files, unsafe path components and protected credential/control paths. The Git worktree control file is explicitly excluded and never restored; unsupported user content causes a whole-operation refusal rather than silent omission.
### FR-3 — Exact owner approval (Must)
WHEN rollback is requested THEN the system SHALL first return a dry-run list of add/update/delete paths bound to target identity, snapshot content, current content digest and a 120-second expiry. Destructive execution SHALL require native local approval and a real managed execution drain lease; IPC/model parameters cannot manufacture the lease.
### FR-4 — Transaction and recovery (Must)
WHEN an approved rollback executes THEN the system SHALL revalidate the complete plan under its host lease, durably stage contents and retain every displaced entry in a journaled backup. Concurrent mismatches, incomplete transactions and restart SHALL block further mutation until explicitly resolved; no automatic retry or destructive cleanup is allowed.
### FR-5 — Integration and proof (Must)
WHEN delivering the feature THEN native capture/list/plan/restore paths SHALL use registered managed roots and local confirmation, preserve start_task no-copy behavior, and have real synthetic filesystem tests for integrity, bounds, failure, restart, conflicts and native integration. Linux and Windows acceptance remain distinct; unsupported platforms must reject before writes and cannot count as full release completion.

## 非功能需求
NFR-1: Errors contain no file content, credentials or absolute paths. Local snapshot storage stays outside execution roots and uses private permissions. Operations serialize by an OS lock; that lock is not proof of external-editor quiescence.
NFR-2: Preserve bytes displaced during rollback, including conflicts, rather than replacing a concurrent editor's data. Never claim global filesystem exclusion.

## 依赖关系
ManagedWorktreeManager approved target resolution; native restore admission lease; SHA-256, UUID and existing filesystem locking dependencies. Native CI and package gates remain required.

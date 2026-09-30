# Requirements: managed worktree reconciliation (#70)

## 功能概述
Reconcile the existing ee37b271 implementation rather than replacing it. The manager remains a native backend building block; UI is outside this increment; native tool dispatch and local scope checks are included. Repository paths and arbitrary Git arguments are not accepted by lifecycle APIs. Harness state remains outside the approved workspace.

## 需求列表
### FR-1: Discover only the approved repository
Given an existing approved workspace root and external harness root, discover the repository with Git and refuse repository roots outside the workspace. Reject non-repositories, invalid workspace IDs, and overlapping state roots before creating managed directories. Accept only lowercase 32-digit hexadecimal IDs.
### FR-2: Preserve managed filesystem containment
Create worktrees only beneath the deterministic harness/worktrees-v1/workspace-ID root. Revalidate this boundary before every lifecycle operation; reject symlinks, Windows reparse points, path replacement, nested registrations and malformed metadata. A replaced managed root must never cause creation or deletion outside the original boundary.
### FR-3: Preserve all local changes
Removal refuses tracked, staged, untracked and ignored files; no force removal, reset or deletion fallback is permitted. Oversized or invalid Git output fails closed. Files outside the managed root and unrelated worktrees remain untouched.
### FR-4: Provide retry-safe bounded lifecycle
Create detached worktrees with opaque generated IDs, return only redacted display paths, list deterministically and enforce the existing limit of eight. Reconstructing the manager discovers existing worktrees. Repeating removal of an absent valid ID succeeds only when no orphan path or matching registry record remains; a nonregistered occupied path is refused. Repeating create deliberately creates a distinct worktree because it has no request idempotency key.
### FR-5: Validate supported platforms honestly
Run native Ubuntu behavior tests and preserve Windows path normalization coverage. Windows-only tests require Windows CI and must not be reported as locally passed. Full application compilation and graph tooling failures remain explicit blockers.

## 非功能需求
Bounded output is preserved; subprocesses are removed and replaced with explicit object/file/count limits. No hard filesystem-I/O deadline is claimed. Errors and Debug must not expose absolute host paths. Existing tests must retain their assertions except the intentionally changed repeat-removal contract. Mandatory GitNexus upstream impact precedes source edits; HIGH/CRITICAL risk is reported and reviewed, and detect_changes plus gencommit precede any approved commit.

## Acceptance criteria
When any unsafe boundary is observed, the system SHALL refuse lifecycle mutation. When removal is retried for an absent valid ID without an orphan path, the system SHALL return success.
- Adversarial root replacement, ignored-file removal, orphan deletion, repeated removal and reconstructed-manager lifecycle tests pass with the existing security regression tests
- A real repository with a path containing spaces supports create/list/remove
- Source changes remain within the existing worktree manager and its tests unless a verified prerequisite requires expanding scope

## Out of scope
No arbitrary Git subcommands, branch manipulation, force deletion, session orchestration, automatic issue publication or external repository writes.

## 依赖关系
Existing Git executable, Rust serde/uuid/tempfile dependencies and GitNexus tooling. Windows CI and Ubuntu native libraries are needed for release verification.

### FR-6: Never execute untrusted Git helpers or configuration
The system SHALL use a pinned in-process object-database engine, never an external Git process. Source HEAD/refs, object database and worktree metadata SHALL be bounded and reject path escapes, symlinks, reparse points and hardlinked metadata. No config includes, GIT environment override, hook, filter, fsmonitor or external helper may be executed/read as authority. Trees exceeding entry/blob/aggregate limits are refused.

# Design: managed worktree reconciliation (#70)

## 概述
Reconcile the ee37b271 manager contract into cumulative tree 22c8c5e. Preserve opaque IDs, deterministic external storage, capacity and redacted errors. Replace its unsafe subprocess runner with a pinned, config-free in-process Git object engine. Public native dispatch has three exact tools and retains existing local-owner approval.

## Requirements mapping
FR-1 maps to primary repository discovery; FR-2 to identity/metadata containment; FR-3 to dirty and detached-commit preservation; FR-4 to bounded lifecycle/public APIs; FR-5 to native/platform tests; FR-6 to isolated ODB, native pins and approval boundaries.

## 技术方案
- Source authority is a canonical approved primary repository with a real, contained .git directory. Linked/bare sources, external common directories, object alternates and link/reparse/hardlink metadata are refused
- git2=0.21.0 (libgit2 1.9.7), default network features disabled. Only Odb::new/add_disk_alternate on verified source objects, Repository::from_odb, Config::new, explicit owned index/workdir and filter-disabled checkout are used. Never Repository::open/worktree and never a subprocess
- Bounded in-root HEAD/ref/packed-ref resolution selects the detached commit. Standard worktree HEAD, commondir, gitdir and .git metadata use exclusive file creation; ordinary Git recognizes the result. No user branch is created or changed
- A retained root identity plus canonical/link/reparse validation runs before lifecycle operations. Object and metadata paths are checked before use and identities checked afterward
- Removal honors explicit Git worktree locks, rechecks tracked/index/untracked/ignored content and rejects detached commits differing from the recorded creation head. Only an existing validated managed directory and its exact metadata are removed. Unknown occupied paths are never adopted or deleted
- Absence is idempotent for a valid ID only if no orphan path exists. Create intentionally allocates a distinct ID each time; no request idempotency key exists

## Data model and interfaces
ManagedWorktree retains id, display_path, head and detached. Public worktree_create/list accept empty objects; worktree_remove accepts only an exact lowercase 32-hex id. Local scopes: workspace.read for list; files.write for create/remove. Mutation is serialized within this process. Existing authorization, execution-gate and policy intercepts precede dispatch. Worktree errors avoid ambient Harness Git diagnostics.

## Exclusive source-root admission
The public handler first obtains root_work::exclusive_context from the actual admitted native request chain and holds it across manager construction and the complete operation. Another active source-root or overlapping-root writer causes NATIVE_ROOT_UNAVAILABLE before metadata access. An unscoped helper cannot mint this authority from a trusted policy. Root identity, durable outstanding-work accounting and fixed host-owned storage are supplied by the separately reviewed native-root dependency; this worktree patch cannot be deployed without it. Native selection/snapshot commands must likewise hold their source-root lease. The broker mutex alone is insufficient.

## Resource limits
Eight managed worktrees per manager namespace; 256 source registry entries; 4,096 checkout entries; 16 MiB per blob; 64 MiB checkout content; 256 MiB/50,000 entries for source object storage; 1 MiB packed refs/root tree objects; 8 MiB index; 64 KiB returned status/registry data. Limits fail closed. There is no subprocess timeout because no subprocess exists; synchronous filesystem I/O has no hard wall-clock deadline.

## 文件结构
Eight worktree Rust modules under src-tauri/src/harness/ cover manager, private adapter, objects, boundary guards, read target and tests. Two tools/worktree_tools modules cover native dispatch and approval tests. Minimal harness/tools module registration, three registry entries/schemas, three additive local scope mappings and pinned Cargo manifest/lock changes complete integration. Every new Rust file remains under 500 lines.

## Managed selection and snapshot boundary
SnapshotTarget is a crate-private validated read target with verify(), not an execution/quiescence lease. Registration as a native workspace must be a separate explicit owner action, with independent profile, configuration, authentication and journal; never silently replace the original workspace or copy its grants. Managed .git/common objects reside outside the managed execution root. Do not widen an execution sandbox to the source repository or common ancestor. The metadata broker has only its validated operations. Destructive rollback requires a separate native owner lease proving stopped/drained execution.

## Native registration pin
Native owner registration persists a validated id-to-profile marker under the private harness managed-root parent, outside both the source repository and each selected execution root. Source Git metadata is untrusted and never owns registration authority. The broker refuses removal with WORKTREE_PINNED while the marker exists. Repeating the same native pin is idempotent; replacing it with another profile is refused. There is no remote pin reset. A failed subsequent native profile save leaves a conservative persistent pin. The broker mutex serializes this host process's create/remove/pin and snapshot transaction; it does not prove execution drainage or exclude external writers. Metadata mutation uses no inherited approval.

## Test strategy
Retain dirty/staged/untracked/overflow/capacity/path-redaction regressions. Add repeated removal, ignored content, ordinary Git interoperability, malicious configuration/helpers/environment, alternates, hardlinks, source/managed substitution, object size, unique detached commits and public authorization/revocation tests. Run real native application tests, not only a extracted module harness. Windows path normalization/junction/identity code still requires Windows CI.

## Risks and failure behavior
Path/identity preflight is not a complete defense against an attacker concurrently modifying private directories with the same OS identity. No such guarantee is claimed. Partial creation can retain fail-closed state for inspection rather than destroy unknown data. Source symlink/submodule trees and unsupported large repositories fail closed. Windows runtime and cumulative release integration remain release gates; baseline native sandbox failures are reported separately.

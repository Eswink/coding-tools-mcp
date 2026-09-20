# Round 5 Rollback Record

Date: 2026-09-20  
Project branch: `plan/offline-safe-connector-lifecycle`  
Round 5 branch: `acceptance/offline-safe-round5`

## Rollback boundary

The reconnect/offline feature itself entered the plan branch in Round 3 via merge commit:

```text
5e16fbae3287aaf40e49fa2af59a28e5d2d0169e
Merge Round 3 offline-safe execution gate
```

Round 4 merge:

```text
815d48d56d435b21be7bef303f19ddcb268c235c
Merge Round 4 non-disclosing privacy hardening
```

Round 4 contains privacy tests/docs/workflows only and does not alter production auth/runtime behavior.

## Round 5 production-source changes

Packaged acceptance exposed cross-platform strict-compile warnings. Round 5 contains four narrow production-source cleanups:

- `src-tauri/src/commands/app_info.rs`
  - Linux-gates the Secret Service default-collection helper/import/test.
- `src-tauri/src/error.rs`
  - Allows dead-code for three Linux-only startup failure variants on non-Linux targets.
- `src-tauri/src/runtime/supervisor.rs`
  - Removes one unnecessary `mut` in a test-only Round 3 regression.
- `src-tauri/src/tools/policy.rs`
  - Rewrites Linux-only configured-command filtering without a cross-platform conditional `mut`.

These changes were introduced only to make Windows non-test `-D warnings` clean and do not change the Level A pause/resume contract.

## Safe rollback options

### Roll back only Round 5 acceptance cleanups

Revert the Round 5 merge once created.

Expected effect:

- offline-safe Level A behavior remains present from Round 3;
- Round 4 privacy regressions remain present;
- Windows strict non-test compile warnings may return;
- no workspace/user data migration is required.

### Roll back the offline-safe execution feature

Revert the Round 3 merge commit `5e16fbae3287aaf40e49fa2af59a28e5d2d0169e`.

Also revert Round 4/Round 5 tests/docs that depend on the execution gate.

Expected behavior returns to the previous hard-coupled lifecycle:

```text
Stop MCP runtime
 -> listener stops
 -> tunnel stops
 -> connector becomes unreachable
```

No OAuth refresh-family deletion, history deletion, workspace data migration, or credential reset is required.

## Data compatibility

The feature adds no destructive persistent schema migration.

The runtime additions are ephemeral/additive:

- execution Online/Offline gate;
- runtime generation;
- additive status DTO fields.

OAuth/chat storage formats are unchanged by the pause/resume feature.

## Release rollback

No Round 5 acceptance artifact was published as a release:

- no tag;
- no GitHub Release;
- no production signing;
- no installer publication.

Therefore rollback does not require a public release withdrawal.

## Verification after rollback

For a Round 5-only rollback:

```text
npm run check
npm run build
cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml
cargo test --locked --manifest-path src-tauri/Cargo.toml
```

For a Round 3 feature rollback, additionally verify:

- existing hard stop still stops listener+tunnel;
- OAuth/chat authorization pre-feature tests remain green;
- no `pause_mcp_execution` / `resume_mcp_execution` IPC remains exposed;
- frontend no longer renders the execution availability panel.

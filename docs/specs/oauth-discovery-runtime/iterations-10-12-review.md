# Iterations 10–12: credential recovery and reproducible reviewer tools

Baseline commit: `977bb26e4b316d66f2bd2c431bba5000c62d6163`.
Baseline tree: `9194bf3dc34d16b3785ddf643e7880c65778c3cf`.

The source and compiler artifacts were downloaded from run `34681525876` and their outer SHA-256 digests verified against the Actions artifact metadata. The source archive's own digest was verified. Reconstructing tracked paths and executable modes produced the exact baseline tree above. No unrelated tracked files, dependencies, package versions, security checks, or release gates are changed.

## Plan and impact

Continue the existing PR, preserve prior fixes, characterize failures before editing, repair only the demonstrated state transitions, rerun related tests, review the diff, then submit the exact candidate to the existing Windows/Linux CI. Native installed acceptance and a final main-sourced release remain separate mandatory gates.

MCP Probe Kit `4.0.1` bootstrap and GitNexus availability were attempted. The container has no matching cache and npm DNS resolution fails (`EAI_AGAIN`); neither tool nor a usable live graph is available. The repository's documented degraded route is used. This is not a claim that `resume_plan`, `impact`, `detect_changes`, or `converge` succeeded. Manual upstream/downstream inspection covers:

- MCP and Actions form save/rotate handlers -> secret IPC wrappers -> `configuration::write_secret` -> `apply` -> persistence followed by checked service restart.
- Workspace route callbacks -> canonical profile refresh -> credential form readback.
- Shared-key save/rotate handlers -> the same backend transaction -> affected shared-service consumers.
- Offline reviewer artifact export -> lockfile dependency resolution -> compiler and dependency regressions.

Risk is HIGH for credential presentation and mutation recovery. Production issuer/audience, redirect matching, PKCE, token validation, authorization grants, and backend lifecycle semantics are not modified. Diff review confirms changes are limited to these three frontend forms, new tests/reviewer tooling, one archive-export step, and this record.

## Iteration 10: workspace authentication forms

Cause: backend `apply` can persist a credential before returning a restart failure. The forms refreshed only after successful IPC; failures left obsolete credentials displayed. Pending rotations also retained the old value. Separately, `loadSecrets` assigned into `draft.oauth_client_id`, discarding private edits or substituting a shared identity into that private draft.

Fix: reuse `applyAndRefresh` for both save and regeneration; perform guarded canonical readback on success and error, clear credentials during rotation, fail closed on read errors, and retain the original mutation error. Readback cannot run for a changed/disposed workspace. Shared client identity is a separate read-only display and never mutates the private draft.

Evidence: 12 new production-function behavioral tests produced 11 failures and one pass on the baseline. After repair all 12 pass, and the combined related suite passes 36/36. Both changed forms compile with zero Svelte warnings.

Scoped self-review: **94/100**, candidate only. The tests execute real TypeScript function bodies with controlled IPC promises; they are not DOM or native evidence.

## Iteration 11: shared credentials

Cause: the shared-key page had the same persist-then-restart failure ambiguity. Save acknowledgements also read the mutable draft after awaiting IPC rather than the submitted snapshot.

Fix: hide the rotating value, recover only the affected key after an error, lock that field if readback fails, preserve unrelated unsaved drafts, and stop later writes after a partial failure. Capture the complete save batch before the first await, and acknowledge only submitted values. Disposal and operation tickets fence readback and publication.

Evidence: six additional behavioral tests produced five failures and one pass before this fix. All 18 new credential tests then pass; combined related tests pass 42/42. All three changed forms compile with zero warnings.

Scoped self-review: **94/100**, candidate only. Failed readback preserves the primary backend error and cannot silently become a successful save. No claim of an atomic multi-key transaction is made: the existing backend API remains one key per call.

## Iteration 12: offline reviewer dependency closure

Cause: the existing artifact exported only `typescript` and `svelte`. The actual ESM compiler requires transitive dependencies such as `zimmerframe`; the existing security regression also imports `cookie`. The unmodified archive therefore cannot reproduce the full frontend suite offline (65 passed, five test-file initialization failures in the first local run).

Fix: derive the bounded package closure from the committed lockfile, resolve hoisted/nested dependencies, terminate cycles, reject missing required dependencies, verify installed package versions, and export that closure instead of two directories. No install, lockfile, dependency version, or production bundle is changed.

Evidence: four closure tests passed and one workflow wiring assertion failed before the workflow change. All five pass afterward. The combined targeted suite passes **47/47**. `git diff --check` passes.

Scoped self-review: **93/100**, candidate only. Initial local compiler checks used an untracked ESM adapter to the official bundled Svelte compiler from the verified artifact; that adapter is not committed. Full default-ESM tests and the new archive itself must be checked using CI's installed dependency closure.

## Remaining acceptance gates at submission

- Run the exact candidate's complete Windows/Linux frontend checks/build/regressions, Rust baseline, repeated lifecycle tests, and production warning gate.
- Download and verify the new reviewer artifact, then rerun the complete frontend suite without the temporary compiler adapter.
- Run the mandatory five installed native combinations and bump every application version source before package construction.
- Merge only a verified head, publish from the resulting exact main source, and verify release assets. Actual ChatGPT account/public deployment checks remain distinct from fixtures.

No merge, release, native acceptance, memory convergence, or overall project-complete claim is made in this record. Scores do not override failed or pending gates.

# ISSUE-023A — Unified Bounded Non-PTY Process Runtime

Status: **ENGINEERING_VERIFIED / REAL_CHILD_PROCESS_TESTS / NO_TAURI_WIRING / HOST_DEFERRED**

Published source: `4f237bed96af1a327d9c286255a06407974da2a9`.

## Delivered

- shared `ProcessManager` / `ProcessSession` model for bounded synchronous/future task execution;
- structured absolute program + argv only; no shell string or implicit shell;
- bounded argv/env/stdin/timeout/output retention/active-process count;
- environment cleared by default; only explicit validated entries are inherited;
- existing working directory is canonicalized, without claiming filesystem confinement;
- concurrent stdout/stderr capture with total-byte accounting and fixed memory retention;
- bounded initial stdin followed by EOF;
- Linux owned process group lifecycle;
- Windows Job Object with `KILL_ON_JOB_CLOSE`, child created suspended, assigned before primary-thread resume;
- timeout, explicit cancel, output overflow and dropped-session cleanup;
- explicit `TerminationUncertain`, `StdinError`, `OutputLimit`, and `OutputError` classifications;
- successful zero exit is not considered command-ok unless output capture completed without truncation;
- successful parent exit still cleans owned surviving descendants.

No cloud dispatch, Tauri integration, shell executor, PTY, sandbox, network policy, or public command tool is wired.

## Security review fixes retained

The first green candidate was not published immediately. Additional review identified two gaps:

1. child stdout/stderr read errors could terminate the reader task without proving output completeness;
2. explicit cancel had only exercised a root process, not a descendant tree.

The final candidate makes stream readers return explicit completion state, classifies incomplete capture as `OutputError`, and adds real descendant cleanup checks for cancel and normal parent exit.

Earlier failure-first iterations also fixed:
- strict Clippy findings;
- supervisor signal-channel closure handling;
- Windows Job Object security feature selection;
- zero-exit overflow/incomplete-output success handling;
- dropped-session cleanup regression;
- Windows active-process exit-code test semantics.

## Verification

- Final exact-source run `35756590646`: Ubuntu 24.04 + Windows 2025 PASS.
- Final one-shot Ubuntu artifact `10708837052`, SHA-256 `d1bd269f66b537a5c3588dc9398afb6503af21848be31ed4fc2a6a4702474f27`.
- Final one-shot Windows artifact `10708162642`, SHA-256 `1e63fe80e1ea830b93bb23258ec9ff9f59e916d99bfd872656829fef8dbafce3`.
- Exact verified local-agent tree in that run: `ada35d7ee57be2828b957d888cedb4289b9b8870` (includes the one-shot verification workflow in the CI branch; only the hash-verified local-agent blobs were promoted).
- Permanent feature run `35756923101`: Ubuntu 24.04 + Windows 2025 PASS.
- Feature artifacts:
  - Ubuntu `10707967514`, SHA-256 `325a76d28abdaa779e13ce5ad22f99b0689fa746faa02929d4612b24b72a56b1`;
  - Windows `10708947058`, SHA-256 `4ad6abc7e3e097123db32f8650eaf8717bab917334f3244966572578c73ccdb4`.
- Test count per platform at final one-shot source: 24 unit + 12 real process integration tests.

## Boundary

This is lifecycle containment, not a security sandbox. A downstream integration must re-check the real local authority ticket and execution policy immediately before spawn. PTY, sandboxing and desktop/cloud wiring remain separate tasks.

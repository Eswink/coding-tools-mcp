# Issue #59 — Native PTY tasks

## 1. Pre-edit evidence

- Resume delegated Plan and keep checkpoints current.
- Run pinned GitNexus context/impact on:
  - `services/local-agent/src/process_tree.rs::spawn`
  - Windows process-tree startup/Job Object symbols that need an internal seam
  - `services/local-agent/src/lib.rs` export surface
  - any existing policy/manager symbol proposed for modification.
- Treat HIGH/CRITICAL as a production-edit stop requiring explicit review.
- Record source line counts and exact baseline revision.

## 2. Add bounded PTY model

Create English-named files:

- `services/local-agent/src/pty.rs`
- `services/local-agent/src/pty_io.rs`

Implement bounded `PtySpec`, size validation, outcome/session types, capacity, terminal stream accounting and lifecycle supervisor. Keep each source file <500 lines.

Do not register a public Tool.

## 3. Add Ubuntu/Linux PTY backend

Create:

- `services/local-agent/src/pty_unix.rs`

Use native PTY allocation, controlling-terminal/session setup, explicit env/cwd/argv, process-group ownership and resize. Add only the minimal internal process-tree constructor required for the already-created process group.

## 4. Add Windows ConPTY backend

Create:

- `services/local-agent/src/pty_windows.rs`

Add only required `windows 0.61` feature flags. Implement ConPTY pipes, HPCON lifecycle, STARTUPINFOEX pseudoconsole attribute, explicit UTF-16 argv/env/cwd, CREATE_SUSPENDED, pre-resume Job Object assignment and exact thread resume.

Do not spawn first and attach later.

## 5. Add fixtures and focused regressions

Create:

- `services/local-agent/src/bin/pty_fixture.rs`
- `services/local-agent/tests/pty_runtime.rs`

Cover:

- real PTY/ConPTY presence;
- Unicode/byte terminal stream;
- resize;
- timeout;
- cancel/close;
- output overflow;
- capacity;
- dropped-session cleanup;
- grandchild/process-tree cleanup;
- Windows argv quoting edge cases;
- no raw secrets/paths in Debug.

## 6. Candidate verification

Before commit:

- rustfmt only scoped PTY/local-Agent files;
- candidate-file Clippy has zero errors while unrelated repository baseline debt is recorded, not silently fixed;
- local-Agent focused PTY tests on Windows 2025 and Ubuntu 24.04;
- complete local-Agent test suite on both;
- staged GitNexus `detect-changes` sees intended files/symbols and is not false-clean;
- all changed/new source files <500 lines;
- exact SHA-256 recorded.

## 7. Review and delivery

- Heartbeat implement/test evidence into Plan.
- Run Plan-aware code review; resolve HIGH/CRITICAL findings.
- Converge Plan.
- Re-read remote feature ref; publish only exact reviewed production files by fast-forward/no-force-push.
- Require official published Windows/Ubuntu CI.
- Update delivery manifest only from real published evidence.
- Close #59 only after published native evidence; keep installed-host/real-ChatGPT gates deferred.

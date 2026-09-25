# Issue #59 — Native PTY design

## Current architecture

The verified local Agent runtime already has:

- `process.rs`: bounded ordinary pipe execution, session/cancel/timeout/output accounting. It is a legacy 700+ line file and is not expanded in this issue.
- `process_tree.rs`: Unix owned process-group termination and platform dispatch.
- `process_tree_windows.rs`: race-free Windows startup using CREATE_SUSPENDED, kill-on-close Job Object assignment, then resume.
- `process_fixture.rs` and `tests/process_runtime.rs`: cross-platform lifecycle/cancel/tree regression coverage.

The PTY increment must preserve those ownership properties without pretending that a pipe-backed child is a terminal.

## Decision: direct native platform backends

Do not add a cross-platform PTY wrapper whose Windows API returns an already-running child. Such a shape cannot preserve the current invariant that the child belongs to the Job Object before any child code executes.

Use the existing `windows` crate and `libc` dependency instead:

- Windows: direct ConPTY/CreateProcessW startup.
- Unix: direct PTY allocation plus audited pre-exec session/controlling-terminal setup.

No new remotely exposed tool is added.

## Modules

### `src/pty.rs`

Common internal API and lifecycle:

- `PtySize`
- `PtySpec`
- `PtyError` / error kind
- `PtyTermination`
- `PtyOutcome`
- `PtyManager`
- `PtySession`

Responsibilities:

- validate bounds;
- capacity semaphore;
- opaque session IDs;
- timeout/cancel/drop lifecycle;
- bounded output accounting;
- async facade around platform blocking handles;
- no raw arguments/env/paths/output in Debug.

Target: <500 lines.

### `src/pty_io.rs`

Bounded terminal master IO utilities:

- bounded blocking reader;
- single-owner writer guarded for interactive writes;
- output overflow signal;
- bounded join/cleanup.

Target: <500 lines.

### `src/pty_unix.rs`

Linux/Unix PTY backend:

1. allocate PTY pair;
2. set initial winsize;
3. configure slave terminal mode appropriate for byte-stable tests;
4. create command with explicit argv/cwd/env and no inherited environment;
5. in audited pre-exec syscall block: establish session and controlling terminal;
6. spawn child;
7. treat child PID as session/process-group ownership identity;
8. expose master reader/writer and resize;
9. hand the process group to existing `ProcessTree` termination semantics.

No shell command-string construction.

Target: <500 lines.

### `src/pty_windows.rs`

Windows ConPTY backend:

1. create ConPTY input/output pipes;
2. create `HPCON`;
3. allocate/update STARTUPINFOEX attribute list;
4. build UTF-16 application path, argv command line, cwd and explicit environment block;
5. create kill-on-close Job Object before process creation;
6. `CreateProcessW` suspended with pseudo-console attribute;
7. assign the exact process handle to the Job Object;
8. resume the exact `PROCESS_INFORMATION.hThread`;
9. return owned process/PTY/pipe handles;
10. resize through `ResizePseudoConsole`.

Windows argv quoting is implemented as a bounded private helper with direct regression coverage for spaces, quotes and trailing backslashes.

On failure before resume, the child is terminated/closed and no unmanaged execution is allowed.

Target: <500 lines.

### `process_tree.rs` / `process_tree_windows.rs`

Minimal internal seams only:

- Unix constructor for an already-established owned process group.
- Windows ability to create an unassigned kill-on-close Job Object and attach+resume an exact suspended process/thread pair.

The existing ordinary `spawn(Command)` path keeps its current behavior.

### `src/bin/pty_fixture.rs`

Test-only executable with bounded modes:

- report terminal/console presence;
- byte/Unicode echo;
- report observed terminal size;
- spawn grandchild and report PID;
- sleep/flood/exit.

It does not add production authority.

### `tests/pty_runtime.rs`

Cross-platform public-library PTY regressions.

## Windows dependency features

Extend the existing target-specific `windows = 0.61` feature set only as needed for:

- Console/ConPTY;
- anonymous pipes/handle management;
- process creation and startup attribute lists.

No second Windows binding crate is introduced.

## Outcome model

PTY output is one terminal stream:

- retained bytes;
- total bytes;
- truncated flag;
- output_complete flag;
- exit code;
- `PtyTermination` using the same conceptual terminal causes as ordinary execution: exited, timed out, cancelled, output limit, IO error, termination uncertain.

Do not map PTY output into separate stdout/stderr fields.

## Cancellation and process-tree ownership

The PTY platform backend returns an owned tree token plus child-wait handle.

Common supervisor sequence:

1. hold capacity permit;
2. start bounded reader;
3. wait on child completion / timeout / cancel / output overflow;
4. if forced termination is needed, terminate the owned tree;
5. confirm the child exits within bounded termination wait;
6. close terminal handles;
7. bound reader shutdown;
8. publish final outcome;
9. release capacity.

Natural child exit still terminates/cleans the owned tree to prevent surviving descendants, matching current ProcessManager behavior.

## Compatibility and non-goals

- Existing `ProcessManager`, `ExecSpec`, ToolRegistry and exec-policy public contracts are unchanged.
- PTY is not automatically selected for existing commands.
- No shell parser, sandbox, worktree, snapshot, Hook or package changes.
- No persisted PTY state or restart replay.
- No physical-host/real-ChatGPT PASS claim.

## Rollback

The functional PTY commit must be independently revertible. Reverting it removes PTY modules, test fixture/tests, Windows feature additions and the small process-tree seams while leaving existing ordinary execution unchanged.

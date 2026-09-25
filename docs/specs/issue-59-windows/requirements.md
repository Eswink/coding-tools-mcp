# Issue #59 — Native PTY requirements

## Goal

Add the first bounded native pseudo-terminal execution primitive to the local Agent runtime:

- Windows uses the Windows Pseudo Console (ConPTY) API.
- Ubuntu/Linux uses a real Unix PTY.
- The increment remains an internal execution primitive. It does **not** register a new public MCP/tool-registry entry and does not expand local authorization.
- Existing command policy, local admission, no-replay, sandbox, snapshot, Hook, cloud-authority, UI and packaging contracts remain unchanged.

## Security and ownership invariants

1. PTY execution must never bypass the existing local authority boundary. This issue adds no new remotely invocable tool.
2. Process-tree containment is mandatory:
   - Windows child code must not run before the process is owned by the existing kill-on-close Job Object.
   - Linux child must enter an owned session/process group before exec so cancellation can terminate the full tree.
   - A “spawn first, attach to a Job Object later” design is out of scope because it introduces an unmanaged-child race.
3. Windows behavior must use native ConPTY rather than an emulated pipe-only terminal.
4. Linux behavior must use a real PTY and controlling-terminal semantics rather than ordinary stdin/stdout pipes.
5. Debug/error surfaces must not expose raw argv, environment values, workspace paths or terminal input/output.
6. PTY handles, pipe/file descriptors, pseudo-console handles and process handles are RAII-owned and must fail closed on partial startup.
7. No detached background child is permitted after timeout, cancel, close, output-limit termination or session drop.

## Bounded input

The PTY request must validate before spawn:

- absolute executable path;
- existing canonical working directory;
- argv count <= 128;
- token bytes <= 4 KiB and total argv bytes <= 64 KiB;
- explicit environment only: <= 64 entries, <= 16 KiB per value and <= 64 KiB total;
- no ambient environment inheritance;
- timeout > 0 and <= 1 hour;
- retained terminal output > 0 and <= 1 MiB;
- initial terminal rows/columns are non-zero and bounded to an implementation-defined safe maximum no greater than 1000;
- each interactive write is bounded to <= 64 KiB.

The constants should reuse existing local-Agent execution limits where that can be done without modifying the already oversized legacy `process.rs`. New or modified source files in this issue must remain below 500 lines after rustfmt.

## Session API

The internal API must expose a bounded session with:

- opaque session ID;
- write bytes to the terminal;
- resize rows/columns;
- read/snapshot retained terminal output and total byte count;
- wait for completion;
- cancel/close the owned PTY process tree;
- terminal status/exit code/duration;
- explicit output truncation and completion metadata.

The first increment does not promise an EOF-only half-close primitive. `close` is an explicit owned-session termination path and must not detach the child.

Terminal output is a single PTY byte stream. Do not fabricate separate stdout/stderr because PTY semantics merge them.

## Platform requirements

### Windows

- Create input/output pipes for ConPTY.
- Create the pseudo console with `CreatePseudoConsole`.
- Build a `STARTUPINFOEXW` attribute list containing `PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE`.
- Spawn with `CreateProcessW`, `EXTENDED_STARTUPINFO_PRESENT`, `CREATE_UNICODE_ENVIRONMENT`, `CREATE_SUSPENDED` and the existing process-group semantics.
- Create the kill-on-close Job Object before process startup.
- Assign the suspended child process to the Job Object using the exact process handle from `PROCESS_INFORMATION`, then resume the exact primary thread handle. Child code must not execute before assignment succeeds.
- Resize with `ResizePseudoConsole`.
- On every partial failure, terminate/close process, thread, Job Object, pseudo console and pipes deterministically.

### Ubuntu/Linux

- Allocate master/slave PTY descriptors with the platform PTY syscall/API.
- Configure the initial window size before exec.
- Child pre-exec performs only audited syscall-level setup required for a new session/controlling terminal; no allocation or non-async-signal-safe application logic.
- The executed child becomes the owned session/process-group leader so the existing negative-PGID termination model remains valid.
- Resize with `TIOCSWINSZ`.
- Parent closes the slave copies after spawn and owns bounded master reader/writer handles.

## Lifecycle semantics

- Capacity exhaustion fails before spawn.
- Timeout/cancel/close/output overflow terminate the full owned process tree and confirm child termination.
- Natural parent exit still performs owned-tree cleanup before reporting terminal completion, preserving current non-detach behavior.
- Dropping the public PTY session must trigger cleanup rather than detach work.
- Reader/writer tasks/threads are bounded and must not block shutdown indefinitely.
- Output overflow terminates the session and retains at most the configured byte limit while reporting the true total seen.
- Resize after terminal completion returns a stable closed-session error.

## Acceptance criteria

- Real Windows Server 2025 ConPTY test proves the fixture has terminal semantics, Unicode output/input, resize, cancel and process-tree cleanup.
- Real Ubuntu 24.04 PTY test proves controlling-terminal semantics, Unicode, resize, cancel and process-tree cleanup.
- Capacity, timeout, output-limit and dropped-session tests fail closed.
- Windows tests prove Job Object ownership is established before resuming the child.
- Full existing local-Agent tests remain green on Windows and Ubuntu.
- GitNexus pre-edit context/impact is recorded for every existing production symbol modified; HIGH/CRITICAL stops production edits for review.
- Staged GitNexus detect sees the candidate and is not false-clean.
- All touched source files satisfy the repository source-length rule.
- Exact SHA-256 and rollback information are recorded.
- Runner tests do not count as physical installed-host or real ChatGPT acceptance.

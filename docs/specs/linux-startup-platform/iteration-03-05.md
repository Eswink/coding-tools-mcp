# Iterations 03–05 — fail-safe Linux bootstrap candidate

Status: candidate implementation prepared; CI pending. This is not a release claim.

## Confirmed failure-first evidence

Run `34869284911` exercised the immutable public v0.5.0 DEB and AppImage on Ubuntu 22.04 and 24.04 under disposable ordinary-user homes. For both package formats and both OS releases:

- an intentionally unusable session-bus/Secret-Service path reproduced a main-thread panic at `src/lib.rs` while evaluating `AppState::new().expect(...)`, exit code 101, after the window had appeared;
- an isolated, explicitly unlocked fixture Secret Service kept the same original package alive for 60 seconds with the main window visible and an encrypted configuration created;
- therefore “configuration/credential backend errors are promoted to process-fatal startup errors” is a confirmed product defect; this controlled result does not prove that the operator machine has the same D-Bus/keyring condition;
- Xvfb is X11 evidence only and is not called Wayland validation.

The original v0.5.0 bytes and tag remain unchanged.

## Candidate design applied

1. `AppState` owns `Option<DataStore>` plus a sanitized startup state. `DataStore`/keyring/config failures enter `locked` recovery rather than exposing the underlying error or panicking.
2. Locked state refuses every existing DataStore-backed command. It does not create a replacement encryption key, fabricate an empty workspace list, start MCP/Actions/tunnels, or downgrade ciphertext to plaintext.
3. A local `retry_startup` command retries only the encrypted configuration boundary. A successful locked→ready transition starts deferred background services exactly once.
4. Tray construction is optional. Failure is recorded as degraded and no longer aborts Tauri setup. `hide_to_tray` refuses to hide if no tray exists, avoiding an unrecoverable invisible window.
5. Linux bootstrap writes fixed phase identifiers only to `$XDG_STATE_HOME/coding-tools-mcp/bootstrap.log` (fallback `~/.local/state/...`). Runtime errors, environment values, workspace paths, command text and credentials are never passed to the logger. A panic marker records only the fixed word `panic` before the normal hook.
6. The root UI queries startup state before loading workspaces. Locked state replaces normal page content with a recovery panel and suppresses the chat-approval host until storage is ready.

## Candidate test contract

The branch workflow now retains the original four-package failure-first matrix and separately builds the current source without publishing packages. Ubuntu 22.04 and 24.04 each run:

- frontend type/Svelte check and production build;
- full Rust tests and release binary build;
- missing-bus startup: process/window must remain alive, no configuration may be created, phases must include `app-state-locked`, `background-deferred`, `setup-complete`, and exclude `panic`/`background-ready`;
- unlocked-keyring control: process/window must remain alive, encrypted configuration must exist, phases must include `app-state-ready`, `background-ready`, `setup-complete`.

No GPU/sandbox override is introduced. The raw release binary is used only for source-runtime validation; packaged candidate testing remains blocked on the planned unique v0.6.0 candidate version.

## Engineering-tool degradation

The approved plan requires Probe/GitNexus before symbol changes. The current execution environment still has no native Probe/GitNexus tool, the pinned launcher was previously unavailable/timed out, and this iteration therefore used explicit manual caller/lock/source review. This is a recorded degradation, not a claim that graph impact analysis succeeded.

## Remaining gates

- CI must compile and run this candidate on both Ubuntu releases.
- Optional notification failure and true no-tray environment remain separate tests.
- AppImage mounted/FUSE mode, runtime-library isolation and real Wayland remain unresolved.
- Platform/capability context and Linux-aware MCP environment contracts are not yet implemented.
- Windows full regression is required before any release candidate.
- Final Ubuntu acceptance still requires the operator's real desktop machine.

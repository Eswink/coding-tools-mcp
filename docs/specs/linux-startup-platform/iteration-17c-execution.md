# Iteration 17C — Split session-bus recovery

Status: IMPLEMENTING / `0.6.0-rc.3`. Stable remains blocked.

## Real Ubuntu root cause

The affected Ubuntu 24.04 Wayland session has two different user-session D-Bus domains:

- the shell/application environment has `DBUS_SESSION_BUS_ADDRESS` set, but it is not the `$XDG_RUNTIME_DIR/bus` user bus;
- the systemd user manager and the active `gnome-keyring-daemon` share a different bus;
- the inherited shell bus reports `org.freedesktop.secrets` as activatable but never obtains an owner; explicit activation and `ReadAlias` both time out;
- restarting `gnome-keyring-daemon` does not change the outcome because the daemon restarts on the systemd user-manager bus, not the inherited shell bus;
- attempting `dbus-update-activation-environment --systemd` from the inherited shell bus cannot reach the real systemd user manager.

This confirms a **split session D-Bus environment**. It supersedes the earlier provisional hypothesis that GNOME Keyring itself was stale or simply needed a daemon restart. The operator evidence proves the shell/application bus differs from the systemd/GNOME-Keyring bus; it does not, by itself, prove that the latter address is exactly `$XDG_RUNTIME_DIR/bus`. RC3 therefore verifies the runtime-user socket and Secret Service availability before selecting it.

The RC2 configuration did not yet exist and its directory was writable, so this evidence does not indicate ciphertext damage, key loss, or a filesystem-permission failure.

## Minimal production change

On Linux, before Tauri creates plugins or background threads:

1. probe the inherited `DBUS_SESSION_BUS_ADDRESS` without logging or serializing it;
2. derive `$XDG_RUNTIME_DIR/bus` only when the runtime directory and socket are real filesystem objects owned by the effective user;
3. probe that explicit runtime bus without activating or restarting any daemon;
4. keep the inherited bus if it already owns `org.freedesktop.secrets`;
5. otherwise select the runtime user bus only if that bus is reachable and Secret Service is already owned or listed as activatable there;
6. if those checks fail, leave the existing route unchanged and preserve fail-closed recovery behavior.

The selector changes only this process environment and runs synchronously before Tauri startup. It does **not** start, stop or restart `gnome-keyring-daemon`, does not invoke `sudo`, does not create a replacement key, and does not alter encrypted configuration semantics.

## Diagnostics

Bounded diagnostics add only categorical/boolean facts:

- whether a bus was originally configured;
- selected route (`inherited`, `runtime_user_bus`, or `unavailable`);
- whether a split route was detected;
- whether the selected bus is reachable;
- whether the runtime user bus is reachable;
- whether Secret Service is owned/activatable on the runtime user bus.

No D-Bus address, path, keyring error payload, credential bytes, or configuration contents are exported.

## Regression change

The Linux source-built startup gate gains an explicit `split-session-bus` fixture. The fixture creates two isolated D-Bus sessions, attaches GNOME Keyring/Secret Service only to the canonical `$XDG_RUNTIME_DIR/bus`, launches the candidate with the other bus inherited, and requires the candidate to reach `app-state-ready`, create encrypted configuration, and start ready-only background services.

Existing missing-bus, healthy-keyring, Safe Mode, DEB/AppImage installed-package, and Windows acceptance gates remain mandatory.

## Impact review and degraded project tooling

The repository-required native MCP Probe/GitNexus path is unavailable in this execution environment. Previous installation/resume attempts could not obtain the native tooling, so no GitNexus result is claimed. The manual impact review covers the direct callers and boundaries instead:

- process entry (`src-tauri/src/lib.rs`);
- keyring error classification (`src-tauri/src/error.rs`);
- bounded diagnostics (`src-tauri/src/commands/app_info.rs` and TypeScript API type);
- Linux startup fixture/workflow;
- Linux/Windows candidate identity.

Risk is **medium** because selecting `DBUS_SESSION_BUS_ADDRESS` is process-wide. The mitigation is intentionally narrow: Linux only, before Tauri threads/plugins, current-user-owned runtime socket only, inherited Secret Service ownership wins, and canonical routing occurs only after the runtime bus proves Secret Service availability. Windows behavior is untouched.

`gencommit` is also unavailable through the degraded tool path; the resulting commit is created through the repository connector with the same bounded change set rather than fabricating tool output.

## Candidate identity

RC2 product bytes have already been handed to the affected operator and failed. Any product-byte change is therefore a new candidate: `0.6.0-rc.3`. RC2 is not overwritten.

Release remains blocked until exact-source RC3 automated gates pass and the affected Ubuntu machine accepts the exact RC3 package bytes through launch, secure-storage ready state, close/reopen, normal workspace/authorization flow, and encrypted-storage persistence.

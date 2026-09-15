# Iteration 17C — Split session-bus recovery

Status: **AUTOMATED PASS / REAL OPERATOR GATE** for `0.6.0-rc.3`. Stable remains blocked.

## Real Ubuntu root cause

The affected Ubuntu 24.04 Wayland session has two different user-session D-Bus domains:

- the shell/application environment has `DBUS_SESSION_BUS_ADDRESS` set, but it is not the `$XDG_RUNTIME_DIR/bus` user bus;
- the systemd user manager and the active `gnome-keyring-daemon` share a different bus;
- the inherited shell bus reports `org.freedesktop.secrets` as activatable but never obtains an owner; explicit activation and `ReadAlias` both time out;
- restarting `gnome-keyring-daemon` changes the daemon PID but not the failing bus route;
- attempting `dbus-update-activation-environment --systemd` from the inherited shell bus cannot reach the real systemd user manager.

This confirms a **split session D-Bus environment** and supersedes the earlier provisional stale-daemon hypothesis. The operator evidence proves the shell/application bus differs from the systemd/GNOME-Keyring bus; it does not by itself prove that the latter address is exactly `$XDG_RUNTIME_DIR/bus`. RC3 therefore verifies the runtime-user socket and Secret Service availability before selecting it.

The failed RC2 configuration did not yet exist and its directory was writable, so the evidence does not indicate ciphertext damage, key loss, or a filesystem-permission failure.

## Minimal production change

Candidate source: `c63cce341bc9505b7e134e8f87b85f4d52ee98d1`  
Source tree: `714ed30336f00a4afe1ce44d251458ebab791e30`

On Linux, before Tauri creates plugins or background threads, RC3:

1. probes the inherited `DBUS_SESSION_BUS_ADDRESS` without logging or serializing it;
2. derives `$XDG_RUNTIME_DIR/bus` only when the runtime directory and socket are real filesystem objects owned by the effective user;
3. probes that explicit runtime bus without activating or restarting any daemon;
4. keeps the inherited bus if it already owns `org.freedesktop.secrets`;
5. otherwise selects the runtime user bus only when that bus is reachable and Secret Service is already owned or listed as activatable there;
6. otherwise preserves the inherited route and existing fail-closed recovery behavior.

The selector changes only this process environment. It does **not** start, stop or restart `gnome-keyring-daemon`, does not invoke `sudo`, does not create a replacement key, and does not alter encrypted configuration semantics.

Bounded diagnostics add only categorical/boolean session-bus facts. No D-Bus address, path, keyring backend payload, credential bytes, or configuration contents are exported.

## Failure-first regression

The Linux startup fixture contains an explicit `split-session-bus` case. It creates two isolated D-Bus sessions, attaches GNOME Keyring/Secret Service only to `$XDG_RUNTIME_DIR/bus`, launches the candidate with the other bus inherited, and requires the candidate to remain alive, create encrypted configuration, reach `app-state-ready`, and start ready-only background services.

The exact-source source-built gate passed on Ubuntu 22.04 and 24.04, including the split-session fixture, missing-bus fail-closed case, healthy keyring, Safe Mode and diagnostics. Run: `34960266758`.

The exact installed-package gate passed on Ubuntu 22.04 and 24.04 for both DEB and AppImage. All four installed matrices passed the raw startup scenarios (including split-session-bus) and the native OAuth/exclusive-owner/refresh/drain acceptance. Run: `34960268326`.

Windows source/regression/NSIS behavior remained unchanged. Windows run `34960269930` had a first-attempt test-infrastructure timeout while PowerShell was collecting a pre-acceptance `Win32_Process`/TCP snapshot; zero native acceptance stages had run. Re-running the failed job against the same exact source SHA passed the full standard-user native acceptance, including real WebView2, OAuth HTTP, local IPC, ownership, refresh rotation, cancellation/drain, restart and secret-export scans. No product change was made for that rerun.

Therefore the RC3 automated gates are **passed**.

## Candidate bytes

Exact Linux package artifact was produced by run `34960268326` from source `c63cce341bc9505b7e134e8f87b85f4d52ee98d1`:

- DEB `MCP_0.6.0-rc.3_amd64.deb`: `2da8f433d7ea0807f8be8f15f0e3bc0d7e42b17b8289e7687d40cb9b9f5d840a`
- AppImage `MCP_0.6.0-rc.3_amd64.AppImage`: `5bec385f6f2c16a0bf464f4510b165f6ea267304d7512104f42aada89b6cf4a8`
- GitHub Actions Linux package artifact ZIP digest: `sha256:ef91df63d5f0e1ad2b77fea3503c4db5e6ae0e0980267a3dc786e76c031764e9`

RC2 is not overwritten. Any further product-byte change must advance to `0.6.0-rc.4` or later.

## Impact review and degraded project tooling

The repository-required native MCP Probe/GitNexus path is unavailable in this execution environment. Previous installation/resume attempts could not obtain the native tooling, so no GitNexus result is claimed. Manual impact review covered process entry, keyring error classification, bounded diagnostics, Linux startup fixtures/workflows, installed DEB/AppImage acceptance, Windows regression and candidate identity.

`gencommit` was likewise unavailable through the degraded tool path; the bounded product commit was created through the repository connector rather than fabricating tool output.

## Remaining gate

Release remains blocked. The affected Ubuntu 24.04 Wayland machine must now test **both exact RC3 package bytes** in the same affected user/session environment.

A pass requires secure storage to reach `ready`, encrypted configuration to persist across close/reopen, normal workspace and ChatGPT authorization/tool flow to work, no plaintext replacement configuration to appear, and both package digests to match the candidate evidence.

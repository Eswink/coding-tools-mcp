# Iteration 13 — Safe Mode and startup diagnostics

Status: COMPLETE FOR AUTOMATED CODE GATE. Product release is not approved.

## Final candidate and evidence

- Exact candidate: `22fdebc7cf238ed4082a0ee363a6460940ecb01b`.
- GitHub Actions workflow: `Linux released startup failure-first`.
- Final run: `34926207880` (run 25), conclusion `success`.
- Candidate Ubuntu 22.04 and Ubuntu 24.04 jobs both completed the frontend/Rust regression and startup-control steps successfully.
- The immutable published v0.5.0 baseline remained green for Ubuntu 22.04/24.04 × DEB/AppImage. No v0.5.0 tag, asset or release-channel mutation was made.

## Delivered recovery contracts

- `--safe-mode` keeps the local GUI available for inspection while skipping tray, notification plugin and automatic background services.
- Safe Mode rejects backend MCP, Actions and tunnel start/restart/test requests; stop/cleanup and status paths remain available.
- `--diagnose-startup` returns before Tauri/WebView construction and before `AppState`/`DataStore` loading.
- Headless diagnostics report `configurationState=not_loaded`; they do not create, decrypt, migrate or rewrite the production configuration.
- Credential-store availability is probed only through the isolated `coding-tools-mcp.startup-diagnostics.v1` namespace. No credential value, application secret or environment value is emitted.
- The diagnostic matrix includes both an isolated healthy session bus/keyring case and a case with `DBUS_SESSION_BUS_ADDRESS` removed entirely.
- Missing Secret Service/session bus remains a recoverable locked GUI state rather than a startup panic, and healthy keyring startup still reaches ready state.
- Linux tunnel dependency guidance is platform-neutral rather than suggesting a Windows-only installer command.

## Verification performed in run 34926207880

Both Ubuntu candidate jobs passed:

- `npm ci`, Svelte check and production frontend build;
- complete locked Rust tests and release build;
- missing-bus GUI recovery with no replacement configuration;
- healthy unlocked-keyring GUI startup;
- Safe Mode GUI startup with no tray/background activation;
- headless diagnostics with a healthy isolated bus/keyring and no production-config side effect;
- headless diagnostics with no session bus and no production-config side effect.

The baseline jobs independently re-downloaded and verified the immutable v0.5.0 packages before exercising their recorded missing-bus/unlocked-keyring controls.

## Engineering-tool degradation

The approved workflow requires MCP Probe/GitNexus impact analysis before symbol changes. The exact source artifact did not contain the Probe launcher; the pinned `mcp-probe-kit@4.0.1` repair attempt timed out, and GitNexus is unavailable in this execution environment. Impact review therefore used explicit caller/source inspection plus exact-source CI. This is a recorded degradation, not a claim that graph analysis succeeded.

## Outstanding gates

- Xvfb evidence is X11-only. It is not real Wayland/operator-desktop acceptance.
- Round 14 must build exact-source candidate DEB/AppImage bytes under a unique `0.6.0-rc.1` version and run Ubuntu installed/MCP/security regressions.
- Round 15 must run the Windows build and installed NSIS regression.
- Round 16 requires the user's real Ubuntu machine to validate both candidate formats before any Stable/Latest release.
- Stable `v0.5.0` remains immutable, and `release_allowed` remains false.

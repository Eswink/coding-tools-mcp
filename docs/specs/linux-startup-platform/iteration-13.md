# Iteration 13 — Safe Mode and startup diagnostics

Status: final hardening prepared; exact-source CI pending. This is not a release claim.

## Intermediate evidence

Commit `a7383956e71abb761a0ad5433d9c641c1c7f4940` was exercised by GitHub Actions run `34924912126`. The immutable v0.5.0 baseline matrix remained green on Ubuntu 22.04/24.04 for both DEB and AppImage, and the source candidate passed frontend build/check, the full Rust suite, release build, recoverable locked startup, healthy unlocked-keyring startup, Safe Mode GUI startup, and the first headless diagnostic path on both Ubuntu releases.

That run is intermediate evidence only. Review after it completed found two contracts that still required hardening before Round 13 could be closed:

1. the diagnostic path must not load, create, decrypt, migrate, or rewrite the production configuration merely to report environment capability;
2. Safe Mode must reject explicit MCP, Actions and tunnel start/restart/test requests in the backend, not merely skip automatic background startup and suppress the normal UI host.

## Final hardening in this candidate

- `--diagnose-startup` returns before Tauri/WebView construction and before `AppState`/`DataStore` loading. It reports `configurationState=not_loaded` and never creates the application configuration as a side effect.
- Credential-store availability is probed through a fixed, isolated diagnostic keyring namespace. Only a state label is returned; credential values, environment values and application secrets are not emitted.
- A second headless contract removes `DBUS_SESSION_BUS_ADDRESS` entirely. Diagnostics must still exit successfully, report `displayBackend=headless`, report the session bus as unavailable, preserve the absent production configuration, and avoid Tauri setup.
- Safe Mode still keeps the main GUI usable for local inspection, but the backend now refuses MCP, Actions and tunnel start/restart/test operations. Stop/cleanup paths remain available.
- Tray, notification plugin, chat approval host and automatic background services remain disabled in Safe Mode.
- Linux tunnel dependency guidance is platform-neutral rather than suggesting a Windows-only installer command.

## Verification contract

The final Round 13 source must pass on both Ubuntu 22.04 and 24.04:

- frontend check and production build;
- full locked Rust tests and release build;
- missing Secret Service/session-bus GUI recovery with no config creation;
- healthy unlocked-keyring GUI startup;
- Safe Mode GUI startup with no tray/background service activation;
- headless diagnostics with an isolated healthy session bus/keyring and no production-config side effect;
- headless diagnostics with no session bus at all and no production-config side effect.

The immutable v0.5.0 DEB/AppImage baseline matrix remains part of the same workflow and must not be modified.

## Engineering-tool degradation

The approved workflow requires MCP Probe/GitNexus impact analysis before symbol changes. The exact source artifact did not contain the Probe launcher; the pinned `mcp-probe-kit@4.0.1` repair attempt timed out, and GitNexus is unavailable in this execution environment. Impact review therefore used explicit caller/source inspection plus exact-source CI. This is a recorded degradation, not a claim that graph analysis succeeded.

## Remaining gates

- Round 13 is not complete until the final hardening commit passes the complete Ubuntu 22.04/24.04 matrix above.
- Xvfb remains X11 evidence only; real Wayland/operator-desktop acceptance is still outstanding.
- Round 14 must build and test exact-source candidate DEB/AppImage artifacts and run the security/conversation regressions.
- Round 15 must run the Windows build/installed NSIS regression.
- A unique `0.6.0-rc.1` candidate must not replace or mutate stable `v0.5.0`.
- Stable release remains blocked on real operator acceptance.

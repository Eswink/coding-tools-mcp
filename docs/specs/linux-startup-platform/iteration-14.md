# Iteration 14 — Exact Linux RC packages and installed acceptance

Status: COMPLETE FOR AUTOMATED LINUX PACKAGE GATE. Stable release is not approved.

## Exact candidate and workflow

- Candidate commit: `a188f6d6fd09c7693786273f800353bb8d344b26`.
- Candidate version: `0.6.0-rc.1` in package.json, package-lock root, Cargo.toml, Cargo.lock project record and tauri.conf.json.
- Workflow: `Linux RC package acceptance`.
- Successful run: `34936756310`.
- Build runner: Ubuntu 22.04.
- Installed matrix: Ubuntu 22.04 and Ubuntu 24.04 × DEB and AppImage.

## Failure-first findings closed in this round

The first exact-package run exposed two independent Linux defects/verification issues rather than hiding them behind WebDriver dependencies:

1. DEB startup itself was healthy, but the startup fixture reused one cumulative `bootstrap.log` across multiple launches. A Safe Mode launch therefore observed `tray-ready` / `background-ready` phases from an earlier healthy launch and falsely failed. The fixture now isolates `XDG_STATE_HOME` per startup scenario; assertions remain strict.
2. AppImage had a real loader failure before Rust bootstrap. Ubuntu 22.04 reported `libEGL.so.1` missing with exit code 127, consistent with the operator report that the published v0.5.0 AppImage could also miss `libGLESv2.so.2`.

## AppImage runtime closure fix

The RC AppImage now stages and verifies these generic GLVND ABI libraries as real Linux amd64 ELF bytes:

- `libEGL.so.1`
- `libGLESv2.so.2`
- `libGL.so.1`
- `libGLX.so.0`
- `libGLdispatch.so.0`

They are copied into `/usr/lib/x86_64-linux-gnu` through Tauri `bundle.linux.appimage.files`. The final AppImage verifier requires all five files, the reviewed AppRun launcher, WebKit helper executables and the GIO TLS module. Generated staging bytes are ignored by git.

The installed AppImage test runners deliberately do **not** install `libegl1`, `libgles2` or `libgl1` before the raw-startup gate. Build runners may install them only as source bytes used to construct the portable package.

## Verification performed in run 34936756310

The build job passed:

- exact RC source/version identity gate;
- frontend dependency install, Svelte/type check and production build;
- complete locked Rust regression;
- Tauri DEB/AppImage production bundle;
- final AppImage launcher/WebKit/GIO/GLVND byte validation;
- exact package manifest and digest generation.

All four installed jobs passed:

- package byte and installed-payload identity checks;
- raw GUI startup **before** WebDriver installation;
- missing-session-bus locked recovery without replacement plaintext configuration;
- healthy unlocked Secret Service startup;
- Safe Mode startup with tray/background services disabled;
- the complete twelve-stage native OAuth / local fingerprint approval / exclusive-owner / refresh rotation / background-task draining / restart / refresh-replay suite;
- RC-specific evidence identity gates.

This includes successful AppImage startup on both Ubuntu 22.04 and Ubuntu 24.04 after the v0.5.0 loader defect was reproduced and corrected.

## Boundaries still not claimed

- Xvfb is X11 automation evidence, not real Wayland/operator-desktop acceptance.
- The real ChatGPT account provenance and OS toast visibility remain outside this synthetic conversation-metadata acceptance.
- The user's real Ubuntu machine must still run both RC package formats before Stable/Latest can move.
- Stable `v0.5.0` remains immutable.

## Next gate

Round 15 must build the same RC source line on Windows, run the complete Windows Rust/frontend regression, install the NSIS package as a genuine standard user, and pass the same twelve native authorization/security stages with an RC-specific version/evidence gate. After Linux and Windows pass on one final source commit, Round 16 may publish `v0.6.0-rc.1` as a prerelease for the operator's real Ubuntu test. Stable release remains blocked until that explicit acceptance.

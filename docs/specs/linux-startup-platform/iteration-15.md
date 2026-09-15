# Iteration 15 — Exact Windows RC installed regression

Status: COMPLETE FOR AUTOMATED WINDOWS REGRESSION. Stable release is not approved.

## Exact candidate and cross-platform identity

- Candidate commit: `c6ac974b0bfd1ec62a33e0e52f48a94f9d0f919f`.
- Candidate tree: `e4687c59aadf4fee72506e86cd7ea37b15d079e4`.
- Candidate version: `0.6.0-rc.1`.
- Windows workflow: `Windows RC package acceptance`.
- Successful Windows run: `34942305580`.
- Final same-source Linux confirmation run: `34942305647`.
- Linux confirmation passed Ubuntu 22.04 and Ubuntu 24.04 × DEB and AppImage, including raw startup before WebDriver and the complete twelve-stage native suite.

The three operator-facing candidate packages produced from this exact source are:

| Package | SHA-256 |
| --- | --- |
| `MCP_0.6.0-rc.1_amd64.deb` | `0d06a283b56f55d823322f6b3ca2a45f59cf79d9a7a31cbdb543205078052d03` |
| `MCP_0.6.0-rc.1_amd64.AppImage` | `3678d6489b89b168c8e1e731036b2444e52e1e29d2714afc18771951adbdedcb` |
| `MCP_0.6.0-rc.1_x64-setup.exe` | `5f0e04661a187c215556d6a8aecd8deaf9392741f85eb633e0fa30655e7de442` |

## Failure-first Windows finding and correction

The first Windows RC attempt (`34939811379`) completed the exact-source checks, frontend/Rust regression, NSIS production build and WebView2 driver preparation, then failed before application acceptance because `rc_windows_install.ps1` rejected an application configuration directory under the hosted build account's `%APPDATA%`.

That was a fixture ownership error rather than a product failure. The application acceptance already creates an ephemeral standard Windows account and loads a fresh profile with `CreateProcessWithLogonW`. The runner administrator profile is not the acceptance identity.

The RC-only installer harness was therefore corrected to:

- never inspect, delete, migrate or overwrite runneradmin application state;
- retain the medium-integrity USER32 desktop smoke, which does not launch the application;
- launch the installed application only through `Windows标准用户验收v22.py`;
- let that fixture own creation and deletion of the temporary standard account/profile;
- preserve the Stable installation/release scripts unchanged;
- add `rc_windows_install_contract_tests.py` so this isolation boundary fails before the expensive NSIS build if reintroduced.

## Windows evidence from run 34942305580

The exact installed NSIS payload passed byte verification:

- installer size: `5,705,960` bytes;
- installed executable SHA-256: `7ae63781f74b269b25707ea33ee226761df054873d42f6a1aa56df1d1ad53e8a`;
- installed payload matched the expected NSIS-transformed production executable;
- numeric PE version matched the `0.6.0` core of the RC version;
- `release_candidate=true` and `publish_approved=false`.

The standard-user isolation evidence recorded:

- `genuine_standard_account=true`;
- actual child token `elevated=false`, integrity RID `8192` (medium);
- launch API `CreateProcessWithLogonW`;
- no manual desktop ACL;
- `native_exit_code=0`;
- account deleted, profile deleted and owned processes closed;
- credential canary scan completed with `credentials_found=false`.

The installed native evidence passed all twelve required stages:

1. installed native application and default exclusive policy;
2. configurable durations persist and render;
3. real discovery / PKCE / offline consent / code exchange;
4. missing context and forged tool arguments rejected;
5. global native modal requires fingerprint and scoped approval;
6. one hundred foreign requests cannot acquire or replace ownership;
7. rotating access credentials preserve owner and deadline;
8. a live child blocks a successor until local cancellation drains;
9. explicit release, readonly successor and native denial;
10. background inbox plus a real ninety-second pending expiry;
11. restart preserves refresh credentials but not chat approval;
12. spent refresh token revokes its family and linked access token.

Additional hard observations:

- native approval source: `native-webdriver-clicks`;
- real WebView2, OAuth HTTP and local IPC were exercised;
- foreign request count: `100`;
- pending expiry elapsed: `90.547` seconds;
- export secret scan completed and found no secret;
- sandbox disabling remained false;
- the unsigned RC installer is explicitly recorded as `signed=false`, not misrepresented as a signed release.

## Boundaries still not claimed

- Conversation metadata in automated native acceptance is synthetic; `real_chatgpt_verified=false`.
- Windows OS toast visibility is not claimed.
- The user's real Ubuntu desktop has not yet validated this exact DEB and AppImage.
- Automated X11/Xvfb evidence is not real operator Wayland/desktop evidence.
- Stable `v0.5.0`, Stable/Latest aliases and production release channels remain untouched.

## Next gate

Round 16 may distribute **this exact commit** (`c6ac974b0bfd1ec62a33e0e52f48a94f9d0f919f`) as `v0.6.0-rc.1` for operator acceptance. Candidate distribution must not retarget Stable/Latest and must use the exact three package digests above. The operator must validate both Ubuntu formats on the real affected machine. Stable `v0.6.0` remains blocked until that explicit real-machine acceptance is recorded.

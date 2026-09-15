# Iteration 16 — Private RC candidate and operator acceptance

Status: BLOCKED ONLY ON REAL AFFECTED-UBUNTU OPERATOR ACCEPTANCE. Stable release is not approved.

## Frozen candidate

Round 16 does not rebuild or repack the application. The operator candidate is the exact source and package bytes already accepted by both automated platform gates:

- source commit: `c6ac974b0bfd1ec62a33e0e52f48a94f9d0f919f`;
- source tree: `e4687c59aadf4fee72506e86cd7ea37b15d079e4`;
- version: `0.6.0-rc.1`;
- Linux confirmation run: `34942305647`;
- Windows installed run: `34942305580`.

Required package digests:

- DEB `MCP_0.6.0-rc.1_amd64.deb`: `0d06a283b56f55d823322f6b3ca2a45f59cf79d9a7a31cbdb543205078052d03`;
- AppImage `MCP_0.6.0-rc.1_amd64.AppImage`: `3678d6489b89b168c8e1e731036b2444e52e1e29d2714afc18771951adbdedcb`;
- Windows NSIS `MCP_0.6.0-rc.1_x64-setup.exe`: `5f0e04661a187c215556d6a8aecd8deaf9392741f85eb633e0fa30655e7de442`.

No public GitHub prerelease, Stable/Latest move, v0.5.0 mutation or rebuild is required before the real-machine check. Private CI bytes are the first operator candidate.

## Operator acceptance order

On the affected x86_64 Ubuntu machine:

1. preserve an offline backup of the current application configuration before launching the RC;
2. verify the candidate SHA-256 before execution;
3. run the AppImage directly without installing host `libegl1`, `libgles2` or `libgl1` merely to make the candidate start;
4. confirm the window remains alive, then close and reopen it;
5. verify the existing encrypted configuration can be opened/recovered as expected and that no plaintext replacement configuration appears;
6. exercise the normal local authorization/tool flow used on that machine;
7. install the exact DEB and repeat start, close/reopen and normal authorization/tool use;
8. if either format fails, capture Ubuntu version, architecture, desktop/session type, launch method, exit code and bounded sanitized stderr/bootstrap diagnostics. Do not include tokens, secrets, private keys or plaintext configuration.

A pass requires both exact Linux formats to start on the real affected environment without the original immediate-exit loader/startup failure.

## Automated evidence already complete

The same source commit has passed:

- Ubuntu 22.04 and 24.04 × DEB/AppImage raw startup before WebDriver installation;
- missing/locked Secret Service recovery and Safe Mode startup;
- full frontend and locked Rust regression;
- complete twelve-stage installed native OAuth/exclusive/refresh/drain suite on all four Linux package jobs;
- Windows production NSIS build and exact installed-payload byte validation;
- genuine temporary Windows standard-user/profile acceptance with cleanup;
- the same twelve-stage Windows native suite;
- export/credential scans with no discovered secret.

## Release boundary

`release_allowed=false` remains mandatory until the operator explicitly reports the result for **both** the DEB and AppImage from this candidate. A public prerelease may be created later from these same bytes if useful, but it must not be substituted for real-machine acceptance and must not retarget Stable/Latest.

If the operator reports a failure, use Round 17 only for that newly evidenced failure with a named hypothesis and bounded patch. If both formats pass, record operator acceptance and proceed to the Stable v0.6.0 release decision without silently changing candidate bytes.

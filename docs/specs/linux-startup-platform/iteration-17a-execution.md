# Iteration 17A — bounded startup failure classification

Status: COMPILE CORRECTION PUSHED / EXACT-SOURCE RERUN REQUIRED. Stable release remains blocked.

Parent source: `a3efbfbd84f2c70608179fd3f3a7317bb17945f9`.

## Execution boundary

This round implements the approved failure-first classification before changing storage semantics. It does not add a fallback credential backend, does not generate replacement keys for existing ciphertext, and does not publish or replace any `0.6.0-rc.1` release asset. The active private candidate identity is `0.6.0-rc.2`.

## Tooling/degraded-path note

The execution environment exposes the repository through the GitHub connector but does not expose the project's native mcp-probe/GitNexus tools or a usable local checkout. An exact-source archive was obtained later, but the GitNexus CLI could not initialize in the execution environment. Per the approved plan, no GitNexus result is fabricated. Manual source impact review was performed before editing:

- `AppError` is shared crate-wide, so the change is additive only: one typed startup-storage variant; existing `Io`, `Json`, and `Message` behavior remains.
- `NativeKeyStore` is the secure-storage boundary; the change alters only safe error classification, not successful get/set semantics or key creation rules.
- `AppState` remains fail-closed and continues to defer all ready-only services until encrypted configuration loads successfully.
- environment diagnostics remain categorical/boolean and never serialize raw keyring errors, credential bytes, D-Bus addresses, configuration paths, or configuration contents.
- recovery UI consumes only the bounded reason code and bounded diagnostics.

No HIGH/CRITICAL blast radius was identified by this manual review; automated Rust/frontend/startup gates are required before proceeding to an installable package candidate.

## Implemented 17A reason taxonomy

- `session_bus_missing`
- `secret_service_unavailable`
- `secret_service_locked_or_denied`
- `key_entry_missing`
- `encrypted_config_key_missing`
- `config_invalid_or_unsupported`
- `config_permission_or_io`
- `unknown_secure_storage_failure`

Linux `keyring` errors are mapped only by the platform-independent error variant. The underlying platform error object is never formatted or serialized.

## Added bounded diagnostics

The diagnostic payload now includes only safe facts needed by the operator gate: application version, known package kind, normalized display/session type, D-Bus presence, classified credential-store state, startup failure reason, configuration existence/envelope state, ownership/permission booleans, and existing executable capability booleans.

The recovery card now shows the stable reason code, fixed remediation guidance, `重试安全存储`, and `复制启动诊断`. Clipboard export serializes only the bounded diagnostic object.

## First exact-source RC2 gate result

Exact source `6da10fdbc0e5e497acc4af1548238d67adcfa4ea` entered both package workflows:

- Linux RC run `34950307647` passed RC2 source identity, npm dependency audit, Svelte check, and production frontend build, then stopped at Rust compilation.
- Windows RC run `34950307544` passed RC2 source identity, Windows/native contract tests and Svelte check, then stopped at the same Rust compilation point.
- The compiler proved that `keyring = 3.6.3` has no `keyring::Error::NoDefaultStore` variant. This was an implementation mistake in the new classifier, not evidence about the operator's Ubuntu root cause.
- Both workflows failed before package-build steps. No DEB, AppImage or NSIS candidate bytes were produced from this source, so the `0.6.0-rc.2` distributable identity remains unused and is retained for the corrected exact-source rerun.

The correction removes only the unsupported enum arm and cross-platform imports/re-export introduced by 17A. It does not relax the failure-first contract or change secure-storage success semantics.

## Next gate

Run all gates from the corrected exact source: Ubuntu 22.04/24.04 startup failure-first, Linux RC build+installed DEB/AppImage matrix, and Windows exact-source RC regression. Any compile, secret-redaction, failure-first or installed-package regression blocks further repair work and release promotion.

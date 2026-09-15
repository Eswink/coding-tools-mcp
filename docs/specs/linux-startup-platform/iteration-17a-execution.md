# Iteration 17A — bounded startup failure classification

Status: IMPLEMENTATION STARTED / CI PENDING. Stable release remains blocked.

Parent source: `a3efbfbd84f2c70608179fd3f3a7317bb17945f9`.

## Execution boundary

This round implements the approved failure-first classification before changing storage semantics. It does not add a fallback credential backend, does not generate replacement keys for existing ciphertext, and does not publish or replace any `0.6.0-rc.1` release asset. A distributable product candidate must be versioned `0.6.0-rc.2` or later.

## Tooling/degraded-path note

The execution environment exposes the repository through the GitHub connector but does not expose the project's native mcp-probe/GitNexus tools or a usable local checkout. Per the approved plan, no GitNexus result is fabricated. Manual source impact review was performed before editing:

- `AppError` is shared crate-wide, so the change is additive only: one typed startup-storage variant; existing `Io`, `Json`, and `Message` behavior remains.
- `NativeKeyStore` is the secure-storage boundary; the change alters only safe error classification, not successful get/set semantics or key creation rules.
- `AppState` remains fail-closed and continues to defer all ready-only services until encrypted configuration loads successfully.
- environment diagnostics remain categorical/boolean and never serialize raw keyring errors, credential bytes, D-Bus addresses, configuration paths, or configuration contents.
- recovery UI consumes only the bounded reason code and bounded diagnostics.

No HIGH/CRITICAL blast radius was identified by this manual review; automated Rust/frontend/startup gates are required before proceeding to a package candidate.

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

## Next gate

Run the exact-source Ubuntu 22.04/24.04 startup workflow. The existing missing-bus diagnostic assertion is intentionally tightened from `locked_or_unavailable` to `session_bus_missing`. Any compile, frontend, secret-redaction, or failure-first regression blocks further repair work.

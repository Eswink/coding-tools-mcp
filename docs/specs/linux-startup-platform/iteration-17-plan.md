# Iteration 17 — Real Ubuntu secure-storage recovery

Status: APPROVED / EXECUTION HANDOFF. Stable release remains blocked.

## New operator evidence

The exact `0.6.0-rc.1` candidate now installs and opens on the affected Ubuntu machine, so the earlier AppImage loader/startup problem is no longer the active blocker. The real operator UI reaches the recovery shell and reports:

- `配置存储暂不可用`
- the application is in restricted recovery mode;
- original configuration is not reset and is not downgraded to plaintext;
- normal workspace/service operation is unavailable.

This is a **real affected-machine failure** and supersedes Round 16's pending operator acceptance. It does not yet prove whether the underlying cause is a missing D-Bus session bus, unavailable Secret Service implementation, locked collection, missing application key entry, configuration/path mismatch, or another credential-backend condition.

## Frozen source and release boundary

- Implementation branch: `fix/linux-startup-platform`.
- Current branch head before this plan: `8f3d005b8a15ff585bef87ab58dda7d9250f0915` (documentation-only after the product candidate).
- Failed operator candidate product source: `c6ac974b0bfd1ec62a33e0e52f48a94f9d0f919f`.
- Candidate version: `0.6.0-rc.1`.
- Candidate digests remain:
  - DEB: `0d06a283b56f55d823322f6b3ca2a45f59cf79d9a7a31cbdb543205078052d03`
  - AppImage: `3678d6489b89b168c8e1e731036b2444e52e1e29d2714afc18771951adbdedcb`
  - NSIS: `5f0e04661a187c215556d6a8aecd8deaf9392741f85eb633e0fa30655e7de442`
- `v0.5.0` remains immutable.
- `release_allowed=false` remains mandatory.
- Any product-byte change after this failure must use a **new candidate version** (normally `0.6.0-rc.2`); do not overwrite or silently reuse `0.6.0-rc.1` bytes.

## Existing implementation facts that must be preserved

Current startup recovery intentionally fails closed:

- `AppState::load_store()` calls `DataStore::load()` and `init_shared_secrets()`; failure leaves `AppState` locked instead of panicking.
- `NativeKeyStore` uses the `keyring` crate with `sync-secret-service` on Linux.
- keyring errors are currently collapsed to the same user-facing unavailable/locked message to avoid leaking credential material.
- existing encrypted envelopes must never cause creation of a replacement key when the original key is missing.
- first creation may generate an AES-256 key only when the secure key backend is actually available and confirms persistence.
- plaintext, environment-variable, in-memory or silent-file fallback remains prohibited.

## Round 17 goal

Make supported Ubuntu systems able to reach a normal ready state without weakening encrypted-storage guarantees, while producing enough non-secret diagnostics to distinguish recoverable Linux credential-backend states on real desktops.

The fix must address the **real operator environment**, not merely make Xvfb/CI green.

## Execution plan

### 17A — Failure-first classification on the real Linux path

Before changing storage semantics, replace the current single opaque failure class with bounded internal reason codes that never include backend error text or secret bytes.

Required classes at minimum:

- `session_bus_missing`
- `secret_service_unavailable`
- `secret_service_locked_or_denied`
- `key_entry_missing`
- `encrypted_config_key_missing`
- `config_invalid_or_unsupported`
- `config_permission_or_io`
- `unknown_secure_storage_failure`

Expose only safe reason codes plus boolean/categorical facts. Never serialize raw keyring errors.

Add diagnostics for:

- package/application version and package kind when known;
- Linux distribution/architecture, desktop session and display backend;
- presence of `DBUS_SESSION_BUS_ADDRESS` without logging its value;
- whether `org.freedesktop.secrets` can be activated/reached;
- whether a default Secret Service collection can be queried and whether access is locked/denied;
- configuration file existence, encrypted-envelope presence and permissions — never plaintext contents;
- key-entry state as `present`, `absent`, `backend_unavailable`, or `locked_or_denied` — never key bytes or account payload;
- config directory writability/ownership as safe booleans.

`--diagnose-startup` and the recovery UI must expose/export this bounded report.

### 17B — Determine the exact supported-Linux recovery path

Use the new classification to split behavior correctly:

1. **Existing encrypted configuration + original key available**: open normally.
2. **Existing encrypted configuration + key backend temporarily locked/unavailable**: remain locked, offer retry after the user/session backend is restored, and never generate a replacement key.
3. **Existing encrypted configuration + key entry genuinely missing**: remain locked with explicit recovery guidance; never overwrite ciphertext.
4. **Fresh install / no managed configuration yet + Secret Service available**: create and read back the new key, then create the encrypted configuration.
5. **Fresh install + Secret Service unavailable on an otherwise supported Ubuntu desktop**: do not silently create plaintext or a raw key file. First test whether supported Ubuntu packaging/session integration can make Secret Service reliably available. Only if that cannot cover supported environments, move to the explicit fallback design gate below.

### 17C — Linux Secret Service integration and packaging

Verify actual Ubuntu 22.04/24.04 desktop behavior rather than assuming the service exists because CI installed packages.

Investigate and test:

- D-Bus user-session activation;
- `org.freedesktop.secrets` ownership/activation;
- GNOME Keyring / compatible Secret Service availability;
- locked-login-keyring behavior;
- DEB runtime dependencies needed for a normal Ubuntu desktop session;
- AppImage behavior when the desktop provides no Secret Service implementation.

For DEB, add only justified runtime dependencies/recommendations. Do not start privileged daemons or use `sudo` from the app.

For AppImage, do not claim portability by hiding a required external user-session service. If Secret Service cannot be relied on across the supported Ubuntu target, proceed to 17D rather than requiring undocumented manual package installation.

### 17D — Conditional secure fallback design gate

This step is **conditional**, not pre-authorized as the first fix.

If evidence proves Secret Service cannot be made reliably available on the supported Ubuntu matrix, implement an explicit user-selected Linux fallback that preserves encryption. Preferred direction:

- passphrase-derived application vault key using a memory-hard KDF (Argon2id or equivalent reviewed dependency);
- AES-256-GCM authenticated encryption remains the data-at-rest primitive;
- no plaintext master key, passphrase, OAuth secret or decrypted configuration is persisted;
- fallback is explicit in UI and diagnostics, never silent;
- existing Secret-Service-encrypted configuration is not automatically re-keyed unless the user successfully unlocks it first and explicitly confirms migration;
- migration is atomic and rollback-safe;
- Windows behavior and Windows Credential Manager remain unchanged.

Do **not** implement a raw `0600` key file as a substitute for a credential store.

### 17E — Recovery UI

Replace the generic recovery card with state-specific but non-secret guidance:

- reason category;
- `重试安全存储` action;
- `导出启动诊断` action;
- supported remediation guidance for session bus / keyring lock / missing key;
- fallback setup/migration action only if 17D is reached and implemented.

The UI must never claim data corruption merely because the Secret Service backend is unavailable.

### 17F — Regression matrix

Automated Linux matrix for both DEB and AppImage:

- Ubuntu 22.04 and 24.04;
- healthy Secret Service;
- missing/unreachable Secret Service;
- locked/denied Secret Service;
- fresh install with no configuration;
- existing encrypted config with valid key;
- existing encrypted config with missing key;
- corrupt/future config;
- Safe Mode;
- close/reopen/restart;
- OAuth, exclusive conversation, refresh rotation, task cancel/drain and history-session regression;
- credential/log/export scans.

Windows must rerun its full Rust/frontend/NSIS/genuine-standard-user native acceptance and remain behaviorally unchanged.

### 17G — Real operator gate

Build `0.6.0-rc.2` only after automated gates pass. The affected Ubuntu machine must test **both** the exact DEB and AppImage bytes.

A pass requires:

- application opens and remains alive;
- secure configuration reaches `ready` state rather than the recovery card;
- close/reopen still succeeds;
- normal workspace and ChatGPT authorization/tool flow works;
- no plaintext replacement configuration appears;
- both package digests match the candidate evidence.

Stable `v0.6.0` remains blocked until this explicit real-machine pass.

## Engineering constraints

- Follow `AGENTS.md`, the existing MCP Probe/GitNexus requirements and their documented degraded path when the native tools are unavailable.
- Before editing production symbols, perform impact analysis when the required project tooling is available; never fabricate GitNexus results.
- Do not revive old PRs or create multiple implementation PRs.
- Preserve one implementation branch and one eventual feature PR.
- Do not move `v0.5.0`, overwrite existing release assets, or publish Stable/Latest during Round 17.
- Do not weaken OAuth, exclusive-owner, refresh-token, draining, key-loss, ciphertext or secret-redaction boundaries.

## Next action for the new window

Resume from this plan and immediately perform 17A against the current branch/product source. First collect/derive a bounded failure classification from the real Linux startup path and existing diagnostics; then patch only the smallest proven cause. Do not ask for another approval: the user has already authorized execution of this saved plan.

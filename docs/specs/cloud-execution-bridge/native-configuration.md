# Native cloud connection configuration — Issue #81

Parent: Epic #32. This is an additive application-configuration increment, not completion of the cloud-to-desktop bridge or permission to publish a reduced-scope package.

## Continuation identity

The accumulated native host/drain implementation is preserved in the owner's complete `229a1a41ab2215ede18588d13cc2110c2c5b3bb6` recovery bundle. The execution container failed during tool restoration. This independent branch starts from the published `2c5d133eaa75d7fc084b8122350d7768ce5b2382` and implements a compatible new module; it does not replace, delete or claim to have published that accumulated source. The original full-plan checkpoint remains `feature-cloud-execution-bridge-steady-9c2e7dee8a`.

Remote pre-edit run `36671115379` used pinned mcp-probe-kit 4.0.1 / GitNexus 1.6.9. Its disposable checkout had no ignored local Plan. The application entry and encrypted-document accessors were inspected before edits. Existing authorization, execution, secure-store and listener implementations are not modified by this increment.

## Requirements and acceptance

1. **Local control only.** Import/status are native desktop IPC commands for an existing locally selected workspace. They are not registered as MCP/Actions tools or exposed by the cloud gateway. Imported JSON cannot select a workspace, grant, scopes, environment, journal path, custom trust root or sandbox bypass.
2. **Strict public identity.** Require schema 1, canonical HTTPS origin with no userinfo/path/query/fragment, a bounded canonical route prefix, non-nil connector/device UUIDs, positive signed-64-bit device/authority epochs, canonical unpadded Base64URL Ed25519 public key, and a bounded session duration.
3. **Verify before writes.** Bounded public JSON and private PKCS8 JSON must parse strictly and match the public key before a namespace is created. The private input crosses only the local native IPC trust boundary; never put it in a chat, URL, error, log, public summary or project file.
4. **Create once.** Namespace initialization is an exclusive directory creation, not exists-then-create or create_dir_all. Exactly one concurrent initializer may succeed. A pre-existing empty, partial, damaged or populated namespace is never overwritten, repaired or force-imported. A failed write preserves partial state for explicit recovery; it is not permission to retry initialization.
5. **Authenticated storage.** Reuse AuthDocument and the existing native encrypted key provider. Bind the encrypted record to local profile, canonical workspace and fixed cloud identity. Generate a separate local random binding key. Do not modify existing grant/projection/execution ledgers. Symlinks/reparse paths are rejected. Local administrators and hostile same-user processes that can alter the entire application store are outside this API's threat boundary.
6. **Read without recreating state.** An absent namespace returns no configuration. An existing namespace without a valid encrypted document fails closed; key loss, swapped ciphertext, identity mismatch or unknown schema cannot regenerate credentials. Status returns only an allowlisted configuration summary, never an online/execution/approval claim.
7. **Native application registration.** Import is blocked by the existing safe-mode check and serialized with the existing restart/configuration gate. The workspace path is read from the local profile, not the imported document. This adds no network connection or automatic Agent startup.
8. **Evidence.** Windows 2025 and Ubuntu 24.04 must run the same focused tests, all-target compilation and complete unchanged native regression. Real OS credential service and UI-click acceptance are separate from cfg(test)'s existing memory-key provider. Record exact source/tree, failures and artifacts; no swallowed test failure, disabled sandbox or fake zero-test pass.

## Planned files

- `src-tauri/src/cloud_connection/`: public identity validation and immutable encrypted storage.
- `src-tauri/src/commands/cloud_connection.rs`: local IPC adapters.
- `src-tauri/src/commands/mod.rs`, `src-tauri/src/lib.rs`: additive registration only.
- `.github/workflows/issue81-native-configuration.yml`: exact-source dual-platform regression.

## Remaining full-plan work

After cumulative-source integration, the application Agent manager must consume this immutable record, initialize its journals exclusively, reuse the live listener ToolContext/ChatAuthorizer, retain occupied/unknown state through stop/restart, and expose actual lifecycle state in the UI. Tool-catalog integration, Windows sandbox, Hooks, managed worktrees, snapshots, deployment preparation and full-package gates remain required. Physical workstation/VPS/real ChatGPT observations stay deferred, not PASS.

## Rollback

Remove the new IPC registration/code with an ordinary revert; preserve encrypted connection namespaces and every existing authorization/projection/execution record. Do not delete a namespace, recover an old authorization backup or reset the manager to make work appear idle. No main, stable release, production infrastructure or credential migration is changed by these development commits.

## Task state

- [x] Scope, preserved continuation and pre-edit source review.
- [ ] Strict import/storage implementation and negative tests.
- [ ] Native IPC registration and dual-platform exact-source regressions.
- [ ] Cumulative-source integration and application lifecycle/UI validation.
- [ ] Full Issue #81 and Epic #32 engineering/release acceptance.

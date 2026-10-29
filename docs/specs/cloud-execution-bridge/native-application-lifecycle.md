# Native application lifecycle integration

## Preserved source and trust boundary

This increment is applied to verified cumulative native-drain tree `22c8c5e79a737989a42188318994032c603ce556`, retaining its production authorizer, opaque admission, durable execution claims and real native WorkDrain. It reconciles immutable configuration `f855ff75518303be1e7b87e6cd7d557dcce5855d` and the reviewed assembled listener-lifetime increment `7fa7054`. It does not claim recovery or equivalence of unrecovered `229a1a41ab2215ede18588d13cc2110c2c5b3bb6`.

`AppState` owns one `ApplicationAgents` for its whole lifetime. Native IPC selects an existing workspace and obtains the live `RuntimeSupervisor::mcp_context_lease`; no remote tool can construct a manager, choose a workspace/path/key/CA, initialize a ledger, approve a request or clear uncertain occupancy. The production start command requires the existing OAuth listener configuration. `NativeToolHost` receives the exact listener context Arc and the existing `chat::service()`.

## Registration, storage and drainage

The listener lease serializes short manager registration against closure. No journal I/O or await occurs while its mutex is held. Only the admitted AgentLifecycle task initializes/opens native projection and execution journals and runs the production HostAgent. A stopped queued task performs no initialization or callbacks.

Locally imported configuration is immutable and encrypted by the existing AuthDocument provider. Runtime material is native-only and not serializable. Initial journal setup is an explicit native action using a create-once `runtime-v1` directory; missing/partial/corrupt restart records are never reinitialized or removed. Imported configuration cannot provide journal paths, TLS trust overrides or native authority. Native file-picker import bounds reads and rejects unsuitable files; Unix verifies inode/device/link count, and Windows verifies opened HANDLE volume/file IDs, link count and reparse attributes.

A listener close or native stop closes the cloud transport, requests cooperative cancellation and seals/waits the actual WorkDrain. The execution journal remains owned through native drain. UI host references are cleared only after proven drain so they cannot retain the projection lock across a safe restart. Panic/cancellation or unknown native completion leaves the lifecycle slot quarantined. The manager cannot be replaced to bypass this state.

Runtime stop/restart and workspace deletion wait for the cloud slot before continuing. Removal only releases a proven-drained in-memory view; persisted configuration and journals remain. View retention is bounded to 32 entries; capacity pruning can remove successful completed views, never uncertain or failed ones. Application exit permanently closes the manager and waits up to eight seconds. On timeout/uncertainty the app remains alive and emits the payload-free `cloud-drain-incomplete` event. It never labels a timeout as drainage or offers force-replay recovery.

## Native controls and status

Native IPC adds `import_cloud_connection_files`, `start_cloud_connection`, `stop_cloud_connection`, and `get_cloud_connection_status`. Existing raw immutable import/status remains native-only. Status distinguishes unconfigured/configured/starting/connected/pending approval/approved/paused/draining/recovery. Approval state is read from the registered cloud conversations' actual native authority, never from OAuth identity or a retained receipt. The existing native approval/revoke and pause/resume controls remain the only authority controls.

## Verification and explicit remaining gates

Focused native tests exercise the actual listener, exact Arc/gate sharing, stop-before-first-poll, duplicate registration, partial setup refusal, worker cancellation, retained execution-journal ownership and safe removal. The integration test uses the actual application manager, immutable imported config, real OAuth listener, production WSS HostAgent and dedicated PostgreSQL fixture. It exercises pending request, native approval, real native tool dispatch, pause/resume, revoke, stop and existing-journal restart without grant resurrection. Its private local CA is test-only; the production import has no CA override.

These tests do not claim a human GUI approval, platform keychain interaction, Windows native sandbox acceptance, production deployment, or complete Issue #81/Epic #32 release acceptance. Windows process cloud execution remains fail-closed under the existing sandbox gate. Exact commands and source-bound receipts accompany the implementation review; all broader release and deployment gates remain separate.

# ISSUE-020A — Local authority bridge and execution-gate hand-off

Tracking: GitHub #50; parent Epic #32 / Draft PR #36. Source baseline for existing desktop symbols: `50fc0caa1be959adff3640b4d75b47ff778d2045`; the five edited existing `src-tauri` blobs were verified byte-identical to the reviewed `7656644` baseline before editing.

Status: IMPLEMENTATION_CANDIDATE / HOST_DEFERRED.

## Security boundary

Cloud OAuth, WebSocket authentication, cloud projection and request-admission eligibility are not local execution authority. This increment exposes only a read-only, locally derived snapshot and a non-serializable five-second hand-off ticket. The snapshot can be minted only from an already-active local Chat grant and contains no project path, workspace metadata, raw ChatGPT session value or cloud-supplied grant fields.

The local ticket captures the exact conversation binding, grant id, scope subset, durable local authority boot epoch, authorization revision and workspace-execution generation. The final commit point rechecks all of them while preserving the existing authorization -> execution-gate lock order. Pause/Resume ABA, revoke, drain, recovery, process reattach or grant/revision change invalidates an uncommitted ticket. A successfully committed permit becomes ordinary in-flight work and preserves the established rule that Pause/revoke does not kill work that already crossed the local admission boundary.

No tool dispatch, filesystem access, shell command, remote approval API, cloud-selected scopes or owner transfer is added here.

## Durable epoch

A separate encrypted `local-authority-v1` authorization document advances monotonically on each process attachment. It is opened together with the existing execution fence before either handle is published to `ChatAuthorizer`. Missing/corrupt/inconsistent state fails closed. The existing execution-fence document format is unchanged.

## Workspace gate generation

`WorkspaceExecutionGate` gains a monotonic in-memory generation. It changes only on actual Online <-> Offline transitions. Existing `try_admit()` behavior is unchanged. New `try_admit_generation()` exists only for the local hand-off and rejects a stale generation before incrementing in-flight work.

## Explicit non-goals / remaining work

- No outbound Agent consumes this snapshot yet.
- No actual tool is launched through `LocalAdmissionPermit` yet.
- No cloud request can construct a local ticket.
- Whole-machine rollback and compromised same-user processes are not solved by the boot epoch.
- Physical Windows/Ubuntu, VPS and real ChatGPT observations remain deferred and are not PASS.

# Cloud Agent runtime

Database-free, outbound-only authenticated Agent shared by the native desktop
and gateway integration tests. It owns no workspace, public approval API, or
local execution grant. Native `LocalHost` provides authoritative state and an
opaque execution permit; the Agent performs fixed-identity WSS, device proof,
bound result validation, and signed append-only no-replay journaling.

The original recovery-only CLI remains separate for compatibility. Only this
crate owns the live client implementation. Server protocol declarations remain
independent server assertions; byte/validation parity and real WSS tests guard
the boundary. PostgreSQL and public MCP/OAuth server code are not dependencies
of the desktop through this crate.

Full native integration, OS sandbox support, CI, and whole-product release
gates remain required. The crate's unit tests alone are not prerelease approval.


## Managed application lifecycle

`AgentLifecycle` serializes registration, actual start admission, stop, and
permanent application shutdown. A stopped queued task never invokes its factory.
One opaque workspace slot is retained until a confirmed drained completion;
stop timeout or cancellation does not abort the worker or free capacity. A panic,
runtime cancellation after start, or unknown termination quarantines the slot.
Handles bind manager, workspace, and generation; a stale handle cannot stop a
replacement. This is process-local ownership, not persistent authorization.

`managed::AgentStart` connects that lifecycle to the real `HostAgent`. It retains
the exclusive signed-journal lock until `ManagedLocalHost::wait_for_drain` proves
host work drained. There is deliberately no default drain receipt: native
implementations must account for blocking tasks and subprocesses, not just the
WSS connection. The native application's production manager and GUI integration
remain downstream work; a test FileHost does not satisfy that integration gate.

See `docs/specs/cloud-execution-bridge/managed-lifecycle.md` for race ordering,
validation boundaries and safe integration requirements.

//! Device-signed projection of LOCAL authority. Eligibility is NOT an execution permit.
//!
//! No HTTP API or executor is installed by this module. The authenticated channel
//! must own these calls; device signing must read authoritative local state, never
//! sign cloud/model-supplied grants. `activate` is once per controller lifecycle.
mod claims;
mod store;

pub use claims::{
    projection_message, verify_snapshot, ExecutionState, LocalLease, ProjectionClaims,
    ProjectionPhase, VerifiedSnapshot, MAX_SNAPSHOT_SECONDS,
};
pub use store::{ApplyOutcome, ConversationBinding, ProjectionChallenge, ProjectionStore};

/// No owner/device/phase metadata in denial values. This is not a CallToolResult.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProjectionDecision {
    AuthorizationUnavailable,
    ScopeDenied,
    RecoveryRequired,
    WorkspaceOffline,
    /// The Agent MUST still authorize the actual request and acquire its own gate.
    Eligible,
}

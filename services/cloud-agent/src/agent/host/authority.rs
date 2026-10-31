//! Trusted host state, never a deserializable execution credential.
use super::super::AgentError;
use crate::{
    crypto::valid_digest,
    execution::{ExecutionRequest, PeerBinding},
    grant::LOCAL_SCOPES,
    projection::{
        valid_worker_id, ExecutionState, LocalLease, ProjectionPhase, WorkerClaim,
        MAX_PROJECTED_WORKERS,
    },
};
use serde_json::Value;
use std::{future::Future, pin::Pin};
use tokio::sync::watch;
use uuid::Uuid;

pub type HostFuture<T> = Pin<Box<dyn Future<Output = Result<T, AgentError>> + Send + 'static>>;

/// The implementation is installed by the local application, not selected by a
/// network request. Admission must mint an opaque, non-reusable local guard.
/// A cancelled future must not release an uncertain operation's recovery fence.
pub trait LocalHost: Send + Sync + 'static {
    type Permit: Send + 'static;
    /// Called only after exact authenticated peer binding is received.
    fn connected(&self, _peer: PeerBinding, _lease_seconds: u64) -> HostFuture<()> {
        Box::pin(async { Ok(()) })
    }
    fn heartbeat(&self, _peer: PeerBinding, _lease_seconds: u64) -> HostFuture<()> {
        Box::pin(async { Ok(()) })
    }
    /// Compare-by-peer cleanup must not close a replacement connection.
    fn disconnected(&self, _peer: &PeerBinding) {}
    /// Persistence may advance only after the gateway acknowledges this proof.
    fn projection_applied(&self, _view: HostAuthoritySnapshot) -> HostFuture<()> {
        Box::pin(async { Ok(()) })
    }
    /// Explicit online status/pending request only. Implementations must use
    /// their native authorizer; no protocol field is a local approval decision.
    fn authorization(&self, _request: crate::approval::ApprovalRequest) -> HostFuture<Value> {
        Box::pin(async { Err(AgentError::LocalAuthority) })
    }
    /// A1 C7-3 (SPEC v5.6 §3.3): a local change to the projected worker list. The
    /// runner sends a projection challenge on its next tick when this changed,
    /// skipping the periodic interval (still one challenge in flight).
    fn projection_dirty(&self) -> Option<watch::Receiver<u64>> {
        None
    }
    fn required_scope(&self, tool: &str, arguments: &Value) -> Option<&'static str>;
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot>;
    fn admit(
        &self,
        expected: HostAuthoritySnapshot,
        request: ExecutionRequest,
    ) -> HostFuture<Self::Permit>;
    fn execute(
        &self,
        permit: Self::Permit,
        request: ExecutionRequest,
        cancelled: watch::Receiver<bool>,
    ) -> HostFuture<Value>;
}

/// No Deserialize implementation: only trusted host code can supply this view.
/// Projection revision is separate from native revision and execution generation.
#[derive(Clone, PartialEq, Eq)]
pub struct HostAuthoritySnapshot {
    pub(in crate::agent) epoch: i64,
    pub(super) revision: u64,
    pub(super) generation: u64,
    pub(in crate::agent) phase: ProjectionPhase,
    pub(in crate::agent) execution: ExecutionState,
    pub(in crate::agent) grant: Option<LocalLease>,
    pub(in crate::agent) drained: Option<Uuid>,
    /// A1 C7: gateway pre-filter data only. Never part of execution authority equality.
    pub(in crate::agent) workers: Vec<WorkerClaim>,
}
impl std::fmt::Debug for HostAuthoritySnapshot {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("HostAuthoritySnapshot([REDACTED])")
    }
}
impl HostAuthoritySnapshot {
    pub fn epoch(&self) -> i64 {
        self.epoch
    }
    pub fn native_revision(&self) -> u64 {
        self.revision
    }
    pub fn execution_generation(&self) -> u64 {
        self.generation
    }
    pub fn phase(&self) -> ProjectionPhase {
        self.phase
    }
    pub fn execution(&self) -> ExecutionState {
        self.execution
    }
    pub fn grant(&self) -> Option<&LocalLease> {
        self.grant.as_ref()
    }
    pub fn drained_grant(&self) -> Option<Uuid> {
        self.drained
    }
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        epoch: i64,
        revision: u64,
        generation: u64,
        phase: ProjectionPhase,
        execution: ExecutionState,
        grant: Option<LocalLease>,
        drained: Option<Uuid>,
    ) -> Result<Self, AgentError> {
        let value = Self {
            epoch,
            revision,
            generation,
            phase,
            execution,
            grant,
            drained,
            workers: Vec::new(),
        };
        value.validate_shape()?;
        Ok(value)
    }
    pub fn workers(&self) -> &[WorkerClaim] {
        &self.workers
    }
    /// A1 C7 (SPEC §3.3): attach the grant conversation's live workers (≤8, 32-hex,
    /// unique, all in the grant conversation). An empty list is always accepted.
    pub fn with_workers(mut self, workers: Vec<WorkerClaim>) -> Result<Self, AgentError> {
        self.workers = workers;
        self.validate_shape()?;
        Ok(self)
    }
    /// Execution authority equality: every field except the pre-filter worker list, so a
    /// spawn/discard between projection and completion cannot invalidate a request.
    /// Public so native admission (src-tauri live host) uses the same rule.
    pub fn same_authority(&self, other: &Self) -> bool {
        self.epoch == other.epoch
            && self.revision == other.revision
            && self.generation == other.generation
            && self.phase == other.phase
            && self.execution == other.execution
            && self.grant == other.grant
            && self.drained == other.drained
    }
    fn validate_shape(&self) -> Result<(), AgentError> {
        if self.epoch <= 0
            || self.revision == 0
            || self.generation == 0
            || (self.phase != ProjectionPhase::Active && self.execution != ExecutionState::Offline)
            || (self.phase == ProjectionPhase::Free && self.grant.is_some())
            || (matches!(
                self.phase,
                ProjectionPhase::Active | ProjectionPhase::Draining
            ) && self.grant.is_none())
            || self
                .drained
                .is_some_and(|id| id.is_nil() || self.phase != ProjectionPhase::Free)
        {
            return Err(AgentError::LocalAuthority);
        }
        if let Some(g) = &self.grant {
            if g.id.is_nil()
                || !valid_digest(&g.conversation)
                || g.issued_at < 0
                || !g
                    .expires_at
                    .checked_sub(g.issued_at)
                    .is_some_and(|n| (1..=30 * 86400).contains(&n))
                || g.scopes.is_empty()
                || g.scopes.len() > LOCAL_SCOPES.len()
                || g.scopes.iter().any(|s| !LOCAL_SCOPES.contains(&s.as_str()))
                || g.scopes
                    .iter()
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != g.scopes.len()
            {
                return Err(AgentError::LocalAuthority);
            }
        }
        if !self.workers.is_empty() {
            let Some(g) = &self.grant else {
                return Err(AgentError::LocalAuthority);
            };
            if self.workers.len() > MAX_PROJECTED_WORKERS
                || self
                    .workers
                    .iter()
                    .any(|w| !valid_worker_id(&w.id) || w.conversation != g.conversation)
                || self
                    .workers
                    .iter()
                    .map(|w| w.id.as_str())
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != self.workers.len()
            {
                return Err(AgentError::LocalAuthority);
            }
        }
        Ok(())
    }
    pub(in crate::agent) fn validate_at(&self, now: i64) -> Result<(), AgentError> {
        self.validate_shape()?;
        if now < 0
            || (self.phase == ProjectionPhase::Active
                && self
                    .grant
                    .as_ref()
                    .is_none_or(|g| g.issued_at > now || g.expires_at <= now))
        {
            return Err(AgentError::LocalAuthority);
        }
        Ok(())
    }
    pub(super) fn validate_request(
        &self,
        projected: &ProjectedHost,
        request: &ExecutionRequest,
        peer: &PeerBinding,
        required_scope: Option<&str>,
        now: i64,
    ) -> Result<(), AgentError> {
        self.validate_at(now)?;
        request
            .validate_at(peer, now)
            .map_err(|_| AgentError::Protocol)?;
        let Some(grant) = self.grant.as_ref() else {
            return Err(AgentError::LocalAuthority);
        };
        if !self.same_authority(&projected.snapshot)
            || projected.until <= now
            || self.phase != ProjectionPhase::Active
            || self.execution != ExecutionState::Online
            || request.binding.authority_epoch != self.epoch
            || request.binding.grant_id != grant.id
            || request.binding.grant_revision != projected.revision
            || request.binding.conversation != grant.conversation
            || required_scope != Some(request.binding.scope.as_str())
            || !grant.scopes.contains(&request.binding.scope)
            || request.binding.deadline > grant.expires_at
        {
            return Err(AgentError::LocalAuthority);
        }
        Ok(())
    }
}
#[derive(Clone)]
pub(super) struct ProjectedHost {
    pub snapshot: HostAuthoritySnapshot,
    pub revision: i64,
    pub until: i64,
}

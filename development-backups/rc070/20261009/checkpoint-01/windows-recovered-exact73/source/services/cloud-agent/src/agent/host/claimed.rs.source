//! Actual durable-claim provenance. This is not a local permission or VM seal.
use super::{journal::HostJournal, AgentError, LocalHost};
use crate::execution::{ExecutionBinding, ExecutionRequest};
use std::{
    any::Any,
    sync::{Arc, Mutex},
};

/// Constructed only by the trusted HostAgent after its signed, locked journal
/// has durably claimed this exact request. No Clone, Deserialize or public mint.
/// Keeping this value keeps the actual host and exclusive journal file alive.
///
/// ```compile_fail
/// use coding_tools_cloud_agent::agent::host::ClaimedDispatch;
/// fn duplicate(value: &ClaimedDispatch) -> ClaimedDispatch { value.clone() }
/// ```
/// ```compile_fail
/// use coding_tools_cloud_agent::agent::host::ClaimedDispatch;
/// let _: ClaimedDispatch = serde_json::from_str("{}").unwrap();
/// ```
pub struct ClaimedDispatch {
    request: ExecutionRequest,
    host: Arc<dyn Any + Send + Sync>,
    journal: Arc<Mutex<HostJournal>>,
}
impl ClaimedDispatch {
    pub(super) fn new<H: LocalHost>(
        host: Arc<H>,
        journal: Arc<Mutex<HostJournal>>,
        request: ExecutionRequest,
    ) -> Self {
        Self {
            request,
            host,
            journal,
        }
    }
    pub fn binding(&self) -> &ExecutionBinding {
        &self.request.binding
    }
    /// Verify against the actual installed instance, before cloning an adapter.
    /// A value with identical fields in a different allocation is not that host.
    pub fn verify_for<H: LocalHost>(
        &self,
        host: &H,
        request: &ExecutionRequest,
        now: i64,
    ) -> Result<(), AgentError> {
        if self
            .host
            .downcast_ref::<H>()
            .is_none_or(|h| !std::ptr::eq(h, host))
        {
            return Err(AgentError::LocalAuthority);
        }
        self.verify_request(request, now)
    }
    /// Recheck inside the already instance-bound owned native callback. This
    /// does not authorize a different host or replace a native admission permit.
    pub fn verify_request(&self, request: &ExecutionRequest, now: i64) -> Result<(), AgentError> {
        if self.request.binding != request.binding || self.request.arguments != request.arguments {
            return Err(AgentError::LocalAuthority);
        }
        request
            .validate_at(&self.request.binding.peer, now)
            .map_err(|_| AgentError::LocalAuthority)?;
        self.journal
            .lock()
            .map_err(|_| AgentError::Journal)?
            .pending(request)
    }
}
impl std::fmt::Debug for ClaimedDispatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ClaimedDispatch([REDACTED])")
    }
}

//! A native-only lifetime for the EXACT MCP listener context.
//!
//! This is a service-lifetime boundary, not an execution permit or local grant.
//! An Agent must still use the existing authorizer, execution gate and durable
//! ledger. Cloning a context does not extend this lease or create a new gate.
use std::{
    panic::{catch_unwind, resume_unwind, AssertUnwindSafe},
    sync::{Arc, Mutex},
};
use tokio::sync::watch;
use uuid::Uuid;

use super::ToolContext;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ListenerLeaseError {
    Closed,
    StateUnavailable,
}
impl std::fmt::Display for ListenerLeaseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Closed => "listener_context_closed",
            Self::StateUnavailable => "listener_context_unavailable",
        })
    }
}
impl std::error::Error for ListenerLeaseError {}

struct Inner {
    identity: Uuid,
    context: Arc<ToolContext>,
    closed: Mutex<bool>,
    stopped: watch::Sender<bool>,
}

/// Cannot be deserialized, fabricated from a request, or reopened after close.
/// Its constructor is restricted to this native crate's listener integration.
#[derive(Clone)]
pub struct ListenerContextLease(Arc<Inner>);
impl std::fmt::Debug for ListenerContextLease {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ListenerContextLease")
            .field("live", &self.is_live())
            .finish_non_exhaustive()
    }
}
impl ListenerContextLease {
    pub(crate) fn new(context: Arc<ToolContext>) -> Self {
        let (stopped, _) = watch::channel(false);
        Self(Arc::new(Inner {
            identity: Uuid::new_v4(),
            context,
            closed: Mutex::new(false),
            stopped,
        }))
    }

    /// Opaque native identity, independent of workspace and connection epochs.
    pub fn generation(&self) -> Uuid {
        self.0.identity
    }

    pub fn is_live(&self) -> bool {
        self.0.closed.lock().is_ok_and(|closed| !*closed)
    }

    /// Serialize short native start registration against listener close.
    /// The callback MUST NOT await, reenter this lease, or perform blocking I/O.
    /// A returned context is the original Arc, not new authorization. Work that
    /// wins registration must remain owned by the Agent lifecycle until drained.
    /// A panic seals the lease and wakes observers, then resumes unwinding.
    pub fn with_live<T>(
        &self,
        register: impl FnOnce(&Arc<ToolContext>) -> T,
    ) -> Result<T, ListenerLeaseError> {
        let mut closed = self
            .0
            .closed
            .lock()
            .map_err(|_| ListenerLeaseError::StateUnavailable)?;
        if *closed {
            return Err(ListenerLeaseError::Closed);
        }
        match catch_unwind(AssertUnwindSafe(|| register(&self.0.context))) {
            Ok(value) => Ok(value),
            Err(panic) => {
                *closed = true;
                self.0.stopped.send_replace(true);
                drop(closed);
                resume_unwind(panic)
            }
        }
    }

    /// Closing is idempotent and does not mutate the legacy execution gate:
    /// existing admitted local jobs retain their established drain semantics.
    /// Cloud supervisors must observe closure and invalidate their own transport.
    pub(crate) fn close(&self) {
        let mut closed = self
            .0
            .closed
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        *closed = true;
        self.0.stopped.send_replace(true);
    }

    /// Cancel-safe observation. Dropping one waiter cannot reopen the lease,
    /// consume another waiter's signal, or imply Agent/process termination.
    pub async fn wait_closed(&self) {
        let mut stopped = self.0.stopped.subscribe();
        loop {
            let done = *stopped.borrow_and_update();
            if done || !self.is_live() {
                return;
            }
            if stopped.changed().await.is_err() {
                return;
            }
        }
    }

    /// Create BEFORE spawning the listener task so a never-polled cancelled
    /// future also closes its lease. Do not create independent replacement guards.
    pub(crate) fn lifetime_guard(&self) -> ListenerLifetimeGuard {
        ListenerLifetimeGuard(self.clone())
    }
}

pub(crate) struct ListenerLifetimeGuard(ListenerContextLease);
impl Drop for ListenerLifetimeGuard {
    fn drop(&mut self) {
        self.0.close();
    }
}

#[cfg(test)]
mod tests;

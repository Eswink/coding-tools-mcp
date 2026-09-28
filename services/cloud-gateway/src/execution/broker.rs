//! Bounded, ephemeral rendezvous. Nothing is queued while an Agent is offline.
use super::{ExecutionReply, ExecutionRequest, PeerBinding};
use crate::{
    admission::{AdmissionRequest, AdmissionStore},
    channel::ChannelController,
    IdentityError,
};
use serde_json::Value;
use std::{
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::{mpsc, oneshot, OwnedSemaphorePermit, Semaphore};
use uuid::Uuid;

pub(crate) const CAPACITY: usize = 32;
#[derive(Clone)]
pub(crate) struct Broker {
    route: Arc<Mutex<Option<Route>>>,
    pub(super) capacity: Arc<Semaphore>,
}
#[derive(Clone)]
struct Route {
    id: Uuid,
    peer: PeerBinding,
    sender: mpsc::Sender<Delivery>,
}
pub(crate) struct Delivery {
    pub request: ExecutionRequest,
    pub reply: oneshot::Sender<ExecutionReply>,
    pub _permit: OwnedSemaphorePermit,
}
pub(crate) struct Registration {
    route: Arc<Mutex<Option<Route>>>,
    id: Uuid,
}
impl Drop for Registration {
    fn drop(&mut self) {
        if let Ok(mut route) = self.route.lock() {
            if route.as_ref().is_some_and(|r| r.id == self.id) {
                *route = None;
            }
        }
    }
}
impl Default for Broker {
    fn default() -> Self {
        Self {
            route: Arc::new(Mutex::new(None)),
            capacity: Arc::new(Semaphore::new(CAPACITY)),
        }
    }
}
impl Broker {
    pub(crate) fn register(
        &self,
        peer: PeerBinding,
    ) -> crate::Result<(Registration, mpsc::Receiver<Delivery>)> {
        peer.validate()?;
        let mut slot = self
            .route
            .lock()
            .map_err(|_| IdentityError::StoreUnavailable)?;
        if slot.as_ref().is_some_and(|r| {
            r.peer.gateway_boot != peer.gateway_boot
                || r.peer.channel_generation >= peer.channel_generation
        }) {
            return Err(IdentityError::InvalidProof);
        }
        let (sender, receiver) = mpsc::channel(CAPACITY);
        let id = Uuid::new_v4();
        *slot = Some(Route { id, peer, sender });
        Ok((
            Registration {
                route: self.route.clone(),
                id,
            },
            receiver,
        ))
    }
    fn route(&self) -> std::result::Result<Route, DispatchError> {
        self.route
            .lock()
            .map_err(|_| DispatchError::Unknown)?
            .as_ref()
            .cloned()
            .filter(|r| !r.sender.is_closed())
            .ok_or(DispatchError::NotConnected)
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DispatchError {
    NotConnected,
    Backpressure,
    Rejected,
    Unknown,
}
impl DispatchError {
    pub fn code(self) -> &'static str {
        match self {
            Self::NotConnected => "EXECUTION_NOT_CONNECTED",
            Self::Backpressure => "EXECUTION_BACKPRESSURE",
            Self::Rejected => "EXECUTION_ADMISSION_CHANGED",
            Self::Unknown => "EXECUTION_OUTCOME_UNKNOWN",
        }
    }
}
/// On HTTP cancellation or panic, preserve uncertainty. A process crash is fenced
/// transactionally by the next ChannelController activation instead.
struct Uncertain {
    store: AdmissionStore,
    id: Uuid,
    resolved: bool,
}
impl Drop for Uncertain {
    fn drop(&mut self) {
        if !self.resolved {
            if let Ok(runtime) = tokio::runtime::Handle::try_current() {
                let store = self.store.clone();
                let id = self.id;
                runtime.spawn(async move {
                    let _ = tokio::time::timeout(
                        Duration::from_secs(3),
                        store.mark_outcome_unknown(id),
                    )
                    .await;
                });
            }
        }
    }
}
impl ChannelController {
    /// This API accepts only an already-admitted request. Readiness and a ticket
    /// are routing assertions; a real Agent must still perform local admission.
    pub async fn dispatch_admitted(
        &self,
        input: AdmissionRequest<'_>,
    ) -> std::result::Result<Value, DispatchError> {
        let route = self.execution.route()?;
        let permit = self
            .execution
            .capacity
            .clone()
            .try_acquire_owned()
            .map_err(|_| DispatchError::Backpressure)?;
        let store = AdmissionStore::new(self.identity_store());
        let request = match store.claim_dispatch(input, &route.peer).await {
            Ok(value) => value,
            Err(_) => return Err(DispatchError::Rejected),
        };
        // Cleanup belongs only to the caller that committed the dispatch claim.
        // A rejected duplicate must not change the winning caller's row. When
        // cancellation loses a claim's commit response, the durable Running
        // state already fences retries until explicit reconciliation.
        let mut guard = Uncertain {
            store: store.clone(),
            id: request.binding.request_id,
            resolved: false,
        };
        let expected = request.binding.clone();
        let remaining = expected
            .deadline
            .checked_sub(now().map_err(|_| DispatchError::Unknown)?)
            .filter(|n| *n > 0)
            .ok_or(DispatchError::Unknown)?;
        let (sender, receiver) = oneshot::channel();
        route
            .sender
            .try_send(Delivery {
                request,
                reply: sender,
                _permit: permit,
            })
            .map_err(|_| DispatchError::Unknown)?;
        let reply = tokio::time::timeout(Duration::from_secs(remaining as u64), receiver)
            .await
            .map_err(|_| DispatchError::Unknown)?
            .map_err(|_| DispatchError::Unknown)?;
        let digest = reply
            .validate_for(&expected, now().map_err(|_| DispatchError::Unknown)?)
            .map_err(|_| DispatchError::Unknown)?;
        store
            .complete_dispatch(&reply, digest)
            .await
            .map_err(|_| DispatchError::Unknown)?;
        guard.resolved = true;
        Ok(reply.result)
    }
}
pub(crate) fn now() -> crate::Result<i64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|d| i64::try_from(d.as_secs()).ok())
        .ok_or(IdentityError::InvalidRequest)
}

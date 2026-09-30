//! Ephemeral native pending/status requests. These never admit executable work.
use crate::{channel::ChannelController, projection::ConversationBinding, IdentityError, Result};
pub use coding_tools_cloud_agent::approval::{
    ApprovalBinding, ApprovalMethod, ApprovalReply, ApprovalRequest, APPROVAL_CAPACITY,
    MAX_APPROVAL_BYTES, MAX_APPROVAL_SECONDS,
};
use coding_tools_cloud_agent::execution::PeerBinding;
use serde_json::Value;
use sqlx::Row;
use std::{
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::sync::{mpsc, oneshot, OwnedSemaphorePermit, Semaphore};
use uuid::Uuid;

pub const APPROVAL_VERSION: u8 = 1;
#[derive(Clone)]
pub(crate) struct Broker {
    route: Arc<Mutex<Option<Route>>>,
    capacity: Arc<Semaphore>,
}
#[derive(Clone)]
struct Route {
    id: Uuid,
    peer: PeerBinding,
    sender: mpsc::Sender<Delivery>,
}
pub(crate) struct Delivery {
    pub request: ApprovalRequest,
    pub reply: oneshot::Sender<ApprovalReply>,
    _permit: OwnedSemaphorePermit,
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
            capacity: Arc::new(Semaphore::new(APPROVAL_CAPACITY)),
        }
    }
}
pub(crate) fn peer(value: crate::execution::PeerBinding) -> PeerBinding {
    PeerBinding {
        connector: value.connector,
        device: value.device,
        device_epoch: value.device_epoch,
        gateway_boot: value.gateway_boot,
        channel_session: value.channel_session,
        channel_generation: value.channel_generation,
    }
}
impl Broker {
    pub(crate) fn register(
        &self,
        peer: PeerBinding,
    ) -> Result<(Registration, mpsc::Receiver<Delivery>)> {
        peer.validate().map_err(|_| IdentityError::InvalidProof)?;
        let mut route = self
            .route
            .lock()
            .map_err(|_| IdentityError::StoreUnavailable)?;
        if route.as_ref().is_some_and(|r| {
            r.peer.gateway_boot != peer.gateway_boot
                || r.peer.channel_generation >= peer.channel_generation
        }) {
            return Err(IdentityError::InvalidProof);
        }
        let (tx, rx) = mpsc::channel(APPROVAL_CAPACITY);
        let id = Uuid::new_v4();
        *route = Some(Route {
            id,
            peer,
            sender: tx,
        });
        Ok((
            Registration {
                route: self.route.clone(),
                id,
            },
            rx,
        ))
    }
    fn current(&self) -> Result<Route> {
        self.route
            .lock()
            .map_err(|_| IdentityError::StoreUnavailable)?
            .as_ref()
            .filter(|r| !r.sender.is_closed())
            .cloned()
            .ok_or(IdentityError::InvalidProof)
    }
}
impl ChannelController {
    pub fn has_native_approval_route(&self) -> bool {
        self.approval.current().is_ok()
    }

    pub async fn authorization_roundtrip(
        &self,
        conversation: &ConversationBinding,
        method: ApprovalMethod,
        arguments: Value,
    ) -> Result<Value> {
        let route = self.approval.current()?;
        coding_tools_cloud_agent::approval::validate_arguments(method, &arguments)
            .map_err(|_| IdentityError::InvalidRequest)?;
        let permit = self
            .approval
            .capacity
            .clone()
            .try_acquire_owned()
            .map_err(|_| IdentityError::InvalidRequest)?;
        self.approval_eligible(&route.peer, conversation).await?;
        let request = ApprovalRequest::new(
            route.peer.clone(),
            conversation.as_str().into(),
            method,
            arguments,
            Uuid::new_v4(),
            crate::execution::now()? + MAX_APPROVAL_SECONDS,
        )
        .map_err(|_| IdentityError::InvalidRequest)?;
        let expected = request.binding.clone();
        let (tx, rx) = oneshot::channel();
        route
            .sender
            .try_send(Delivery {
                request,
                reply: tx,
                _permit: permit,
            })
            .map_err(|_| IdentityError::InvalidProof)?;
        let reply = tokio::time::timeout(Duration::from_secs(MAX_APPROVAL_SECONDS as u64), rx)
            .await
            .map_err(|_| IdentityError::InvalidProof)?
            .map_err(|_| IdentityError::InvalidProof)?;
        reply
            .validate_for(&expected, crate::execution::now()?)
            .map_err(|_| IdentityError::InvalidProof)?;
        self.approval_eligible(&route.peer, conversation).await?;
        Ok(reply.result)
    }

    async fn approval_eligible(
        &self,
        expected: &PeerBinding,
        conversation: &ConversationBinding,
    ) -> Result<()> {
        use crate::projection::{ExecutionState, LocalLease, ProjectionPhase};
        #[derive(serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        struct State {
            phase: ProjectionPhase,
            execution: ExecutionState,
            authority_epoch: i64,
            grant: Option<LocalLease>,
            #[serde(default, rename = "last_drained_grant")]
            _drained: Option<Uuid>,
        }
        expected
            .validate()
            .map_err(|_| IdentityError::InvalidProof)?;
        let identity = self.identity_store();
        if expected.connector != identity.identity.connector() {
            return Err(IdentityError::InvalidProof);
        }
        let mut tx = identity.pool.begin().await?;
        sqlx::query("SET LOCAL lock_timeout='2000ms'")
            .execute(&mut *tx)
            .await?;
        sqlx::query("SET LOCAL statement_timeout='3000ms'")
            .execute(&mut *tx)
            .await?;
        let device = sqlx::query(
            "SELECT epoch FROM ctm_devices WHERE id=$1 AND connector=$2 AND NOT revoked FOR SHARE",
        )
        .bind(expected.device)
        .bind(expected.connector)
        .fetch_optional(&mut *tx)
        .await?
        .ok_or(IdentityError::InvalidProof)?;
        let projected =
            sqlx::query("SELECT * FROM ctm_grant_projection WHERE connector=$1 FOR SHARE")
                .bind(expected.connector)
                .fetch_optional(&mut *tx)
                .await?
                .ok_or(IdentityError::InvalidProof)?;
        let channel = sqlx::query("SELECT * FROM ctm_agent_channel WHERE connector=$1 FOR SHARE")
            .bind(expected.connector)
            .fetch_optional(&mut *tx)
            .await?
            .ok_or(IdentityError::InvalidProof)?;
        let at: i64 =
            sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
                .fetch_one(&mut *tx)
                .await?;
        let raw = projected
            .try_get::<Option<String>, _>("state_text")?
            .ok_or(IdentityError::InvalidProof)?;
        if raw.len() > MAX_APPROVAL_BYTES {
            return Err(IdentityError::InvalidProof);
        }
        let state: State =
            serde_json::from_str(&raw).map_err(|_| IdentityError::StoreUnavailable)?;
        // A Free projection is merely absence of a committed execution owner.
        // The native application owns pending requests and still checks foreign
        // ownership, Pause, capacity and recovery before any notification.
        let allowed = match (state.phase, state.grant.as_ref()) {
            (ProjectionPhase::Free, None) => state.execution == ExecutionState::Offline,
            (ProjectionPhase::Active, Some(g)) => {
                g.conversation == conversation.as_str()
                    && g.expires_at > at
                    && g.issued_at <= at
                    && state.authority_epoch
                        > projected.try_get::<i64, _>("revoked_through_epoch")?
            }
            _ => false,
        };
        if !allowed
            || state.authority_epoch <= 0
            || device.try_get::<i64, _>("epoch")? != expected.device_epoch
            || projected.try_get::<Option<Uuid>, _>("device")? != Some(expected.device)
            || projected.try_get::<i64, _>("snapshot_device_epoch")? != expected.device_epoch
            || projected.try_get::<Uuid, _>("gateway_boot")? != expected.gateway_boot
            || !projected.try_get::<bool, _>("reconciled")?
            || projected.try_get::<i64, _>("snapshot_until")? <= at
            || channel.try_get::<Uuid, _>("gateway_boot")? != expected.gateway_boot
            || channel.try_get::<Option<Uuid>, _>("session")? != Some(expected.channel_session)
            || channel.try_get::<i64, _>("generation")? != expected.channel_generation
            || channel.try_get::<Option<Uuid>, _>("device")? != Some(expected.device)
            || channel.try_get::<i64, _>("device_epoch")? != expected.device_epoch
            || !channel.try_get::<bool, _>("connected")?
            || channel.try_get::<i64, _>("lease_until")? <= at
            || channel.try_get::<i64, _>("absolute_until")? <= at
        {
            return Err(IdentityError::InvalidProof);
        }
        tx.commit().await?;
        Ok(())
    }
}

//! Live outbound Agent. The injected native host is the only local authority.
//! Neither a cloud ticket nor this transport layer can construct a host permit.
mod authority;
mod connection;
mod journal;
mod runner;
use super::{signer::RecoverySigner, wire::unix_now, AgentConfig, AgentError};
use crate::execution::{ExecutionReply, ExecutionRequest, PeerBinding};
use authority::ProjectedHost;
pub use authority::{HostAuthoritySnapshot, HostFuture, LocalHost};
use journal::HostJournal;
use serde_json::{json, Value};
use std::{
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::sync::{watch, Semaphore};

pub const MAX_HOST_IN_FLIGHT: usize = 4;
pub struct HostAgent<H: LocalHost> {
    cfg: AgentConfig,
    worker: Arc<Worker<H>>,
}
impl<H: LocalHost> HostAgent<H> {
    /// Explicitly create a NEW state file or attach an existing one. Missing,
    /// incompatible, locked, truncated or corrupt state never auto-initializes.
    pub fn open(
        config_json: &[u8],
        key_json: &[u8],
        state_file: &Path,
        initialize: bool,
        host: Arc<H>,
    ) -> Result<Self, AgentError> {
        let cfg = AgentConfig::from_bytes(config_json)?;
        let signer = Arc::new(RecoverySigner::from_input(cfg.clone(), key_json)?);
        let journal = HostJournal::open(state_file, &signer, initialize)?;
        Ok(Self {
            cfg,
            worker: Arc::new(Worker {
                host,
                signer,
                journal: Mutex::new(journal),
                capacity: Arc::new(Semaphore::new(MAX_HOST_IN_FLIGHT)),
            }),
        })
    }
    /// One caller at a time; stopping/cancelling never replays uncertain work.
    pub async fn run(&mut self, mut stop: watch::Receiver<bool>) -> Result<(), AgentError> {
        let end = tokio::time::sleep(Duration::from_secs(self.cfg.run_seconds));
        tokio::pin!(end);
        let mut attempts = 0u32;
        loop {
            if *stop.borrow() {
                return Ok(());
            }
            let result = tokio::select! {
                biased;
                _=stop.changed()=>return Ok(()),
                _=&mut end=>return Ok(()),
                r=runner::session(&self.cfg,self.worker.clone())=>r,
            };
            if result != Err(AgentError::Transport) {
                return result;
            }
            attempts += 1;
            if attempts > 8 {
                return Err(AgentError::Exhausted);
            }
            let delay = Duration::from_secs((1u64 << attempts.saturating_sub(1).min(5)).min(30));
            tokio::select! {
                biased;
                _=stop.changed()=>return Ok(()),
                _=&mut end=>return Ok(()),
                _=tokio::time::sleep(delay)=>{},
            }
        }
    }
}
struct Worker<H: LocalHost> {
    host: Arc<H>,
    signer: Arc<RecoverySigner>,
    journal: Mutex<HostJournal>,
    capacity: Arc<Semaphore>,
}
impl<H: LocalHost> Worker<H> {
    fn revision(&self) -> Result<i64, AgentError> {
        self.journal
            .lock()
            .map_err(|_| AgentError::Journal)?
            .revision(&self.signer)
    }
    async fn snapshot(&self) -> Result<HostAuthoritySnapshot, AgentError> {
        tokio::time::timeout(Duration::from_secs(3), self.host.snapshot())
            .await
            .map_err(|_| AgentError::LocalAuthority)?
    }
    async fn execute(
        self: Arc<Self>,
        request: ExecutionRequest,
        peer: PeerBinding,
        projected: ProjectedHost,
    ) -> (ExecutionRequest, Value) {
        let result = self.execute_inner(&request, &peer, &projected).await;
        let value = result.unwrap_or_else(error_result);
        (request, value)
    }
    async fn execute_inner(
        &self,
        request: &ExecutionRequest,
        peer: &PeerBinding,
        projected: &ProjectedHost,
    ) -> Result<Value, AgentError> {
        let _capacity = self
            .capacity
            .clone()
            .try_acquire_owned()
            .map_err(|_| AgentError::Capacity)?;
        let current = self.snapshot().await?;
        current.validate_request(
            projected,
            request,
            peer,
            self.host
                .required_scope(&request.binding.tool, &request.arguments),
            now()?,
        )?;
        self.journal
            .lock()
            .map_err(|_| AgentError::Journal)?
            .claim(&self.signer, request)?;
        // A durable claim precedes the opaque host permit and any tool effects.
        let permit = match tokio::time::timeout(
            Duration::from_secs(3),
            self.host.admit(current.clone(), request.clone()),
        )
        .await
        {
            Ok(Ok(value)) => value,
            _ => {
                self.journal
                    .lock()
                    .map_err(|_| AgentError::Journal)?
                    .complete(&self.signer, request)?;
                return Err(AgentError::LocalAuthority);
            }
        };
        // Waiting for native admission must not turn a pre-lock time check into authority.
        let remaining = request
            .binding
            .deadline
            .checked_sub(now()?)
            .filter(|n| *n > 0)
            .ok_or(AgentError::ExecutionUnknown)?;
        let (cancel, rx) = watch::channel(false);
        let mut on_drop = CancelOnDrop(Some(cancel));
        let result = tokio::time::timeout(
            Duration::from_secs(remaining as u64),
            self.host.execute(permit, request.clone(), rx),
        )
        .await
        .map_err(|_| AgentError::ExecutionUnknown)?
        .map_err(|_| AgentError::ExecutionUnknown)?;
        let reply = ExecutionReply {
            binding: request.binding.clone(),
            result: result.clone(),
        };
        reply
            .validate_for(&request.binding, now()?)
            .map_err(|_| AgentError::ExecutionUnknown)?;
        self.journal
            .lock()
            .map_err(|_| AgentError::Journal)?
            .complete(&self.signer, request)?;
        on_drop.0.take();
        // A revoked/paused/changed owner does not receive a now-private result,
        // even if its final cloud projection has not crossed the wire yet.
        let latest = self.snapshot().await?;
        latest
            .validate_request(
                projected,
                request,
                peer,
                self.host
                    .required_scope(&request.binding.tool, &request.arguments),
                now()?,
            )
            .map_err(|_| AgentError::ExecutionUnknown)?;
        Ok(result)
    }
}
struct CancelOnDrop(Option<watch::Sender<bool>>);
impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        if let Some(stop) = self.0.take() {
            let _ = stop.send(true);
        }
    }
}
fn now() -> Result<i64, AgentError> {
    unix_now()
}
fn error_result(error: AgentError) -> Value {
    let (code, category, uncertain) = match error {
        AgentError::LocalAuthority => ("LOCAL_AUTHORITY_CHANGED", "permission", false),
        AgentError::Capacity => ("LOCAL_EXECUTION_CAPACITY", "availability", false),
        AgentError::Duplicate => ("LOCAL_REQUEST_ALREADY_CLAIMED", "recovery", true),
        _ => ("EXECUTION_OUTCOME_UNKNOWN", "recovery", true),
    };
    json!({"ok":false,"error":{"code":code,"category":category,
        "message":"Local execution was not completed for this request; do not automatically replay."},
        "outcome_unknown":uncertain})
}
#[cfg(test)]
mod tests;

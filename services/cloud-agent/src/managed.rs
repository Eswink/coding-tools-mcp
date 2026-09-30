//! Managed production HostAgent startup. Configuration and signing material are
//! supplied by the local application, never by an incoming tool request.
use crate::{
    lifecycle::{AgentLifecycle, LifecycleError, RunHandle, TaskExit},
    AgentConfig, AgentError, HostAgent, HostFuture, LocalHost,
};
use std::{path::PathBuf, sync::Arc};
use uuid::Uuid;
use zeroize::Zeroizing;

/// Native implementations must track detached/blocking work as well as async
/// workers. This deliberately has NO default "drained" implementation.
/// Connection loss or JoinHandle::abort alone is not a drain receipt.
pub trait ManagedLocalHost: LocalHost {
    fn wait_for_drain(&self) -> HostFuture<()>;
}

/// Validated, bounded startup inputs. Private material is cleared both after
/// loading and when a stopped/rejected queued factory is dropped uncalled.
pub struct AgentStart {
    config: Vec<u8>,
    key: Zeroizing<Vec<u8>>,
    state: PathBuf,
    initialize: bool,
}
impl std::fmt::Debug for AgentStart {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("AgentStart([REDACTED])")
    }
}
impl AgentStart {
    pub fn new(
        config: Vec<u8>,
        key: Vec<u8>,
        state: PathBuf,
        initialize: bool,
    ) -> Result<Self, AgentError> {
        let key = Zeroizing::new(key);
        AgentConfig::from_bytes(&config)?;
        if key.is_empty()
            || key.len() > 16_384
            || !state.is_absolute()
            || state.file_name().is_none()
        {
            return Err(AgentError::Configuration);
        }
        Ok(Self {
            config,
            key,
            state,
            initialize,
        })
    }
    pub fn launch<H: ManagedLocalHost>(
        self,
        manager: &AgentLifecycle,
        workspace: Uuid,
        host: Arc<H>,
    ) -> Result<RunHandle, LifecycleError> {
        manager.launch(workspace, move |stop| async move {
            // Neither the journal nor the key is opened before the lifecycle's
            // start admission. In particular, close-before-first-poll performs
            // no state initialization, no local callbacks and no connection.
            let opened = HostAgent::open(
                &self.config,
                &self.key,
                &self.state,
                self.initialize,
                host.clone(),
            );
            drop(self.key);
            let mut agent = match opened {
                Ok(agent) => agent,
                Err(_) => return TaskExit::FailedDrained, // No host work was started.
            };
            let result = agent.run(stop).await;
            // Keep the Agent (including its exclusive journal lock) alive while
            // native work drains. A cancelled/expired stop waiter does not drop
            // this future and cannot release that lock or its workspace slot.
            let drained = host.wait_for_drain().await;
            drop(agent);
            match (result, drained) {
                (_, Err(_)) => TaskExit::Unconfirmed,
                (Ok(()), Ok(())) => TaskExit::Drained,
                (Err(_), Ok(())) => TaskExit::FailedDrained,
            }
        })
    }
}

#[cfg(test)]
mod tests;

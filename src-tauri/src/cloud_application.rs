//! One application-owned manager. No IPC or remote input can replace its owner,
//! release uncertain occupancy, choose a journal path, or fabricate an approval.
use crate::{
    auth::cloud_context::CloudTransport,
    cloud_connection::RuntimeMaterial,
    error::{AppError, AppResult},
    tools::{
        cloud_host::{live::NativeLiveHost, NativeToolHost},
        listener_context::ListenerContextLease,
    },
};
use coding_tools_cloud_agent::{
    lifecycle::{AgentLifecycle, Phase, RunHandle, RunOutcome, TaskExit},
    managed::ManagedLocalHost,
    HostAgent,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Duration,
};
use uuid::Uuid;

pub(crate) const STOP_TIMEOUT: Duration = Duration::from_secs(8);
fn unavailable() -> AppError {
    AppError::Message("云连接不可用或仍在排空；已保留现有配置与恢复账本。".into())
}
fn workspace_identity(id: &str) -> Uuid {
    let digest = Sha256::digest(id.as_bytes());
    let mut bytes = [0; 16];
    bytes.copy_from_slice(&digest[..16]);
    Uuid::from_bytes(bytes)
}
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CloudConnectionStatus {
    pub configured: bool,
    pub phase: &'static str,
    pub connected: bool,
    pub generation: Option<u64>,
}
struct TransportLifetime(CloudTransport);
impl Drop for TransportLifetime {
    fn drop(&mut self) {
        self.0.close();
    }
}

struct View {
    handle: RunHandle,
    link: CloudTransport,
    host: Arc<Mutex<Option<Arc<NativeLiveHost>>>>,
}
pub(crate) struct ApplicationAgents {
    manager: AgentLifecycle,
    views: Mutex<HashMap<String, View>>,
}
impl Default for ApplicationAgents {
    fn default() -> Self {
        Self {
            manager: AgentLifecycle::new(32).expect("fixed native capacity"),
            views: Mutex::new(HashMap::new()),
        }
    }
}
impl ApplicationAgents {
    pub(crate) fn start(
        &self,
        id: &str,
        lease: ListenerContextLease,
        material: RuntimeMaterial,
        initialize: bool,
    ) -> AppResult<CloudConnectionStatus> {
        let mut views = self.views.lock().map_err(|_| unavailable())?;
        // Completed successful entries need no retained UI owner. Failed or
        // uncertain entries remain visible and cannot be evicted for capacity.
        if !views.contains_key(id) && views.len() >= 32 {
            views.retain(|_, view| {
                !matches!(
                    view.handle.outcome(),
                    Some(RunOutcome::Drained | RunOutcome::NotStarted)
                )
            });
            if views.len() >= 32 {
                return Err(unavailable());
            }
        }
        let host_view = Arc::new(Mutex::new(None));
        let observed_host = host_view.clone();
        let link = material.link.clone();
        let observed_link = link.clone();
        let profile = id.to_owned();
        let lifetime = lease.clone();
        // Only the short manager registration occurs under the listener lock.
        // Journal I/O and constructors execute inside the admitted task factory.
        let handle = lease
            .with_live(|context| {
                let context = context.clone();
                self.manager
                    .launch(workspace_identity(id), move |stop| async move {
                        let _transport_lifetime = TransportLifetime(observed_link.clone());
                        if !lifetime.is_live() || *stop.borrow() {
                            return TaskExit::Drained;
                        }
                        let opened = (|| {
                            material.prepare_journals(initialize).map_err(|_| ())?;
                            let tools = Arc::new(
                                NativeToolHost::new(
                                    &profile,
                                    context,
                                    material.link.clone(),
                                    crate::auth::chat::service(),
                                )
                                .map_err(|_| ())?,
                            );
                            let host = Arc::new(
                                NativeLiveHost::open(
                                    tools,
                                    &material.root.join("projection"),
                                    initialize,
                                    material.authority_epoch,
                                )
                                .map_err(|_| ())?,
                            );
                            let agent = HostAgent::open(
                                &material.config,
                                &material.key,
                                &material.root.join("executions.bin"),
                                initialize,
                                host.clone(),
                            )
                            .map_err(|_| ())?;
                            Ok::<_, ()>((host, agent))
                        })();
                        drop(material.key);
                        let (host, mut agent) = match opened {
                            Ok(value) => value,
                            Err(()) => {
                                observed_link.close();
                                return TaskExit::FailedDrained;
                            }
                        };
                        if let Ok(mut view) = observed_host.lock() {
                            *view = Some(host.clone());
                        }
                        let (cancel, cancelled) =
                            tokio::sync::watch::channel(*stop.borrow() || !lifetime.is_live());
                        let mut stop = stop;
                        let result = {
                            let run = agent.run(cancelled);
                            tokio::pin!(run);
                            tokio::select! {
                                biased;
                                _ = lifetime.wait_closed() => {
                                    observed_link.close(); cancel.send_replace(true); run.await
                                },
                                _ = stop.changed() => {
                                    observed_link.close(); cancel.send_replace(true); run.await
                                },
                                result = &mut run => result,
                            }
                        };
                        observed_link.close();
                        // Keep host AND exclusive execution journal alive until actual
                        // blocking/native descendants finish. Cancellation quarantines.
                        let drained = host.wait_for_drain().await;
                        // A read-only UI reference must not keep the projection journal
                        // locked after proven drain; uncertain hosts stay quarantined.
                        if drained.is_ok() {
                            if let Ok(mut view) = observed_host.lock() {
                                *view = None;
                            }
                        }
                        drop(agent);
                        match (result, drained) {
                            (_, Err(_)) => TaskExit::Unconfirmed,
                            (Ok(()), Ok(())) => TaskExit::Drained,
                            (Err(_), Ok(())) => TaskExit::FailedDrained,
                        }
                    })
            })
            .map_err(|_| unavailable())?
            .map_err(|_| unavailable())?;
        views.insert(
            id.to_owned(),
            View {
                handle,
                link,
                host: host_view,
            },
        );
        drop(views);
        self.status(id, true)
    }
    pub(crate) fn status(&self, id: &str, configured: bool) -> AppResult<CloudConnectionStatus> {
        let views = self.views.lock().map_err(|_| unavailable())?;
        let Some(view) = views.get(id) else {
            return Ok(CloudConnectionStatus {
                configured,
                phase: if configured {
                    "configured"
                } else {
                    "unconfigured"
                },
                connected: false,
                generation: None,
            });
        };
        let phase = match view.handle.phase().map_err(|_| unavailable())? {
            Some(Phase::Unconfirmed) => "recovery",
            Some(Phase::Stopping) => "draining",
            Some(Phase::Queued) => "starting",
            Some(Phase::Running) => view
                .host
                .lock()
                .map_err(|_| unavailable())?
                .as_ref()
                .map_or("starting", |host| host.application_phase()),
            None => match view.handle.outcome() {
                Some(RunOutcome::Drained | RunOutcome::NotStarted) => "configured",
                _ => "recovery",
            },
        };
        Ok(CloudConnectionStatus {
            configured,
            phase,
            connected: view.link.ensure_connected().is_ok(),
            generation: Some(view.handle.generation()),
        })
    }
    pub(crate) async fn stop(&self, id: &str) -> AppResult<()> {
        let handle = {
            let views = self.views.lock().map_err(|_| unavailable())?;
            views.get(id).map(|view| {
                view.link.close();
                view.handle.clone()
            })
        };
        if let Some(handle) = handle {
            if handle.outcome().is_none() {
                self.manager
                    .stop(&handle, STOP_TIMEOUT)
                    .await
                    .map_err(|_| unavailable())?;
            } else if handle.outcome() == Some(RunOutcome::Unconfirmed) {
                return Err(unavailable());
            }
        }
        Ok(())
    }
    /// Workspace deletion may release only a proven completed view. Persistent
    /// configuration and journals are deliberately not deleted by this operation.
    pub(crate) fn remove_drained_workspace(&self, id: &str) -> AppResult<()> {
        let mut views = self.views.lock().map_err(|_| unavailable())?;
        if let Some(view) = views.get(id) {
            if !matches!(
                view.handle.outcome(),
                Some(RunOutcome::Drained | RunOutcome::FailedDrained | RunOutcome::NotStarted)
            ) {
                return Err(unavailable());
            }
        }
        views.remove(id);
        Ok(())
    }
    pub(crate) fn request_shutdown(&self) {
        if let Ok(views) = self.views.lock() {
            for view in views.values() {
                view.link.close();
            }
        }
        self.manager.request_shutdown();
    }
    pub(crate) async fn shutdown(&self) -> AppResult<()> {
        self.request_shutdown();
        self.manager
            .shutdown(STOP_TIMEOUT)
            .await
            .map_err(|_| unavailable())
    }
}
#[cfg(test)]
mod tests;

#[cfg(all(test, feature = "cloud-agent-integration-tests"))]
#[path = "cloud_application/wss_tests.rs"]
mod wss_tests;

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
    backoff_delay, classify_retry,
    lifecycle::{AgentLifecycle, Phase, RunHandle, RunOutcome, TaskExit},
    managed::ManagedLocalHost,
    AgentError, HostAgent, Jitter, LinkState, RetryClass, SystemJitter,
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
/// What the application task does after `HostAgent::run` returns.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Supervision {
    /// Stay stopped: asked to stop, or an error retrying cannot fix. The failure
    /// stays visible as the existing `recovery` phase and is never retried.
    Finish,
    /// Run the same Agent (same journals, same host, same link) again after this delay.
    Restart(Duration),
}
/// A run at least this long counts as healthy and clears the restart counter.
const HEALTHY_RUN: Duration = Duration::from_secs(30);
/// Same classification and backoff as the Agent's own reconnect loop. `run()` is
/// already always-on, so this only catches an unexpected exit: a clean return or a
/// retryable error nobody asked for. A user stop, a closed listener and
/// NeedsOperator/Fatal errors (credentials, TLS, journal) are never restarted.
pub(crate) fn restart_decision(
    result: &Result<(), AgentError>,
    stopping: bool,
    restarts: &mut u32,
    ran_for: Duration,
    jitter: &dyn Jitter,
) -> Supervision {
    if stopping {
        return Supervision::Finish;
    }
    let class = match result {
        Ok(()) => RetryClass::Retryable,
        Err(error) => classify_retry(*error),
    };
    if class != RetryClass::Retryable {
        return Supervision::Finish;
    }
    if ran_for >= HEALTHY_RUN {
        *restarts = 0;
    }
    *restarts = restarts.saturating_add(1);
    Supervision::Restart(backoff_delay(*restarts, jitter.permille()))
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CloudConnectionStatus {
    pub configured: bool,
    pub phase: &'static str,
    pub connected: bool,
    pub generation: Option<u64>,
    /// Always-on Agent link: none | connecting | online | reconnecting |
    /// needs_operator | failed | stopped. Public metadata only; the phase set the
    /// UI already knows is unchanged.
    pub link: &'static str,
    pub link_attempt: Option<u32>,
    /// Stable public error code (for example `agent_tls_rejected`), never a message
    /// from the gateway or any local secret.
    pub link_error: Option<String>,
}
fn link_view(state: Option<LinkState>) -> (&'static str, Option<u32>, Option<String>) {
    match state {
        None => ("none", None, None),
        Some(LinkState::Connecting) => ("connecting", None, None),
        Some(LinkState::Online) => ("online", None, None),
        Some(LinkState::Reconnecting { attempt }) => ("reconnecting", Some(attempt), None),
        Some(LinkState::NeedsOperator(e)) => ("needs_operator", None, Some(e.to_string())),
        Some(LinkState::Failed(e)) => ("failed", None, Some(e.to_string())),
        Some(LinkState::Stopped) => ("stopped", None, None),
    }
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
    agent_link: Arc<Mutex<Option<tokio::sync::watch::Receiver<LinkState>>>>,
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
        let agent_link = Arc::new(Mutex::new(None));
        let observed_agent_link = agent_link.clone();
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
                            let journal_root =
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
                                    &journal_root.join("projection"),
                                    initialize,
                                    material.authority_epoch,
                                )
                                .map_err(|_| ())?,
                            );
                            let agent = HostAgent::open(
                                &material.config,
                                &material.key,
                                &journal_root.join("executions.bin"),
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
                        if let Ok(mut slot) = observed_agent_link.lock() {
                            *slot = Some(agent.link_state());
                        }
                        let (cancel, cancelled) =
                            tokio::sync::watch::channel(*stop.borrow() || !lifetime.is_live());
                        let mut stop = stop;
                        let mut restarts = 0u32;
                        let result = loop {
                            let started = tokio::time::Instant::now();
                            let result = {
                                let run = agent.run(cancelled.clone());
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
                            let stopping =
                                *cancel.borrow() || *stop.borrow() || !lifetime.is_live();
                            match restart_decision(
                                &result,
                                stopping,
                                &mut restarts,
                                started.elapsed(),
                                &SystemJitter,
                            ) {
                                Supervision::Finish => break result,
                                Supervision::Restart(delay) => {
                                    tokio::select! {
                                        biased;
                                        _ = lifetime.wait_closed() => break Ok(()),
                                        _ = stop.changed() => break Ok(()),
                                        _ = tokio::time::sleep(delay) => {}
                                    }
                                }
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
                agent_link,
            },
        );
        drop(views);
        self.status(id, true)
    }
    /// Startup/auto-connect policy. Starts the Agent only when the user already
    /// imported a cloud configuration (`material` is `Some`) and the workspace's
    /// local OAuth/listener context is live (`lease` is `Some`). It never
    /// initializes journals (`initialize = false`): creating durable state stays an
    /// explicit user action, so an unprepared workspace simply stays stopped. It
    /// grants nothing: the Agent still needs the local native approval for every
    /// execution, exactly as with the manual start button. An already visible
    /// run (including a failed or uncertain one) is left alone, never replaced.
    /// Finally, the user's persisted intent must be "started": a configuration that
    /// was never started, or that the user stopped, is not resumed.
    #[cfg_attr(not(test), allow(dead_code))] // called from the runtime start in a later commit
    pub(crate) fn auto_start(
        &self,
        id: &str,
        lease: Option<ListenerContextLease>,
        material: Option<RuntimeMaterial>,
        user_intent: bool,
    ) -> AppResult<Option<CloudConnectionStatus>> {
        // `user_intent` is the persisted "last explicit action was start": a manual
        // stop clears it, so launching the application never undoes that stop.
        let (true, Some(lease), Some(material)) = (user_intent, lease, material) else {
            return Ok(None);
        };
        let blocked = self
            .views
            .lock()
            .map_err(|_| unavailable())?
            .get(id)
            .is_some_and(|view| {
                !matches!(
                    view.handle.outcome(),
                    Some(RunOutcome::Drained | RunOutcome::NotStarted)
                )
            });
        if blocked {
            return Ok(None);
        }
        self.start(id, lease, material, false).map(Some)
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
                link: "none",
                link_attempt: None,
                link_error: None,
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
        let current = view
            .agent_link
            .lock()
            .map_err(|_| unavailable())?
            .as_ref()
            .map(|state| *state.borrow());
        let (link, link_attempt, link_error) = link_view(current);
        Ok(CloudConnectionStatus {
            configured,
            phase,
            connected: view.link.ensure_connected().is_ok(),
            generation: Some(view.handle.generation()),
            link,
            link_attempt,
            link_error,
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
    /// Read-only proof for native restore admission. A missing UI row cannot
    /// hide an occupied lifecycle slot; uncertain completion is never idle.
    pub(crate) fn ensure_quiescent(&self, id: &str) -> AppResult<()> {
        if self
            .manager
            .current(workspace_identity(id))
            .map_err(|_| unavailable())?
            .is_some()
        {
            return Err(unavailable());
        }
        if self
            .views
            .lock()
            .map_err(|_| unavailable())?
            .get(id)
            .is_some_and(|view| view.handle.outcome() == Some(RunOutcome::Unconfirmed))
        {
            return Err(unavailable());
        }
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
mod supervision_tests {
    use super::*;
    use crate::{
        auth::{cloud_context::CloudTransport, PublicOrigin},
        workspace::{AuthConfig, RuntimeConfig},
    };
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
    use ring::signature::{Ed25519KeyPair, KeyPair};
    use serde_json::json;
    use zeroize::Zeroizing;

    struct Fixed(u64);
    impl Jitter for Fixed {
        fn permille(&self) -> u64 {
            self.0
        }
    }
    fn decide(
        result: Result<(), AgentError>,
        stopping: bool,
        restarts: &mut u32,
        ran_secs: u64,
    ) -> Supervision {
        restart_decision(
            &result,
            stopping,
            restarts,
            Duration::from_secs(ran_secs),
            &Fixed(0),
        )
    }

    #[test]
    fn retryable_exits_restart_and_operator_or_fatal_exits_do_not() {
        use AgentError::*;
        for e in [
            Transport,
            LocalAuthority,
            Capacity,
            Protocol,
            ExecutionUnknown,
        ] {
            let mut n = 0;
            assert_eq!(
                decide(Err(e), false, &mut n, 1),
                Supervision::Restart(Duration::from_secs(1)),
                "{e:?}"
            );
        }
        for e in [
            Authentication,
            Tls,
            Credentials,
            Configuration,
            Journal,
            Duplicate,
            Arguments,
            Exhausted,
            Cancelled,
        ] {
            let mut n = 0;
            assert_eq!(
                decide(Err(e), false, &mut n, 1),
                Supervision::Finish,
                "{e:?}"
            );
            assert_eq!(n, 0, "a refused restart must not consume budget");
        }
    }
    #[test]
    fn an_unrequested_clean_exit_restarts_but_a_requested_stop_never_does() {
        let mut n = 0;
        assert_eq!(
            decide(Ok(()), false, &mut n, 1),
            Supervision::Restart(Duration::from_secs(1))
        );
        for result in [
            Ok(()),
            Err(AgentError::Transport),
            Err(AgentError::LocalAuthority),
        ] {
            let mut n = 0;
            assert_eq!(decide(result, true, &mut n, 1), Supervision::Finish);
        }
    }
    #[test]
    fn restart_backoff_grows_to_thirty_seconds_and_a_healthy_run_resets_it() {
        let mut n = 0;
        let delays: Vec<u64> = (0..7)
            .map(
                |_| match decide(Err(AgentError::Transport), false, &mut n, 2) {
                    Supervision::Restart(d) => d.as_secs(),
                    Supervision::Finish => unreachable!(),
                },
            )
            .collect();
        assert_eq!(delays, [1, 2, 4, 8, 16, 30, 30]);
        assert_eq!(
            decide(Err(AgentError::Transport), false, &mut n, 31),
            Supervision::Restart(Duration::from_secs(1))
        );
    }
    #[test]
    fn restart_delay_includes_jitter() {
        let mut n = 0;
        assert_eq!(
            restart_decision(
                &Err(AgentError::Transport),
                false,
                &mut n,
                Duration::ZERO,
                &Fixed(1000)
            ),
            Supervision::Restart(Duration::from_millis(1250))
        );
    }

    struct Auto {
        root: tempfile::TempDir,
        id: String,
        lease: ListenerContextLease,
        listener: Option<(
            crate::mcp::ShutdownSender,
            tauri::async_runtime::JoinHandle<()>,
        )>,
        config: Vec<u8>,
        key: Vec<u8>,
    }
    impl Auto {
        fn new() -> Self {
            let root = tempfile::tempdir().unwrap();
            let workspace = root.path().join("workspace");
            std::fs::create_dir(&workspace).unwrap();
            let id = Uuid::new_v4().to_string();
            let (shutdown, listener, _gate, lease) =
                crate::mcp::spawn_listener_with_origin_and_context_lease(
                    0,
                    workspace,
                    id.clone(),
                    AuthConfig {
                        auth_type: "noauth".into(),
                        ..Default::default()
                    },
                    PublicOrigin::managed("").unwrap(),
                    None,
                    None,
                    None,
                    RuntimeConfig::default(),
                )
                .unwrap();
            let pkcs8 = Ed25519KeyPair::generate_pkcs8(&ring::rand::SystemRandom::new()).unwrap();
            let pair = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
            let config = serde_json::to_vec(&json!({"origin":"https://127.0.0.1:9","prefix":"/bridge",
                "connector":Uuid::new_v4(),"device":Uuid::new_v4(),"device_epoch":1,"authority_epoch":1,
                "public_key":URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),
                "revision_file":root.path().join("runtime/revision.bin"),"ca_der_file":null,"run_seconds":60})).unwrap();
            let key = serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs8.as_ref())}))
                .unwrap();
            Self {
                root,
                id,
                lease,
                listener: Some((shutdown, listener)),
                config,
                key,
            }
        }
        fn material(&self) -> RuntimeMaterial {
            let cfg = coding_tools_cloud_agent::AgentConfig::from_bytes(&self.config).unwrap();
            let context = self.lease.with_live(Arc::clone).unwrap();
            RuntimeMaterial {
                config: self.config.clone(),
                key: Zeroizing::new(self.key.clone()),
                link: CloudTransport::new(
                    &self.id,
                    context.workspace.root(),
                    &cfg.origin,
                    &cfg.prefix,
                    cfg.connector,
                    cfg.device,
                    1,
                    "native-application-test-separate-binding-secret",
                )
                .unwrap(),
                root: self.root.path().join("runtime"),
                authority_epoch: 1,
            }
        }
        async fn close(&mut self) {
            if let Some((shutdown, task)) = self.listener.take() {
                let _ = shutdown.send(());
                tokio::time::timeout(Duration::from_secs(5), task)
                    .await
                    .unwrap()
                    .unwrap();
                self.lease.wait_closed().await;
            }
        }
    }
    async fn outcome(app: &ApplicationAgents, id: &str) -> RunOutcome {
        tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                let found = app
                    .views
                    .lock()
                    .unwrap()
                    .get(id)
                    .and_then(|view| view.handle.outcome());
                if let Some(outcome) = found {
                    return outcome;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("task did not finish")
    }

    #[test]
    fn link_state_is_exposed_to_the_ui_as_public_metadata_only() {
        use coding_tools_cloud_agent::LinkState::*;
        assert_eq!(link_view(None), ("none", None, None));
        assert_eq!(link_view(Some(Connecting)), ("connecting", None, None));
        assert_eq!(link_view(Some(Online)), ("online", None, None));
        assert_eq!(
            link_view(Some(Reconnecting { attempt: 7 })),
            ("reconnecting", Some(7), None)
        );
        assert_eq!(
            link_view(Some(NeedsOperator(AgentError::Tls))),
            ("needs_operator", None, Some("agent_tls_rejected".into()))
        );
        assert_eq!(
            link_view(Some(Failed(AgentError::Journal))),
            (
                "failed",
                None,
                Some("agent_journal_requires_local_review".into())
            )
        );
        assert_eq!(link_view(Some(Stopped)), ("stopped", None, None));
    }
    #[tokio::test]
    async fn auto_start_needs_both_an_imported_configuration_and_a_live_listener() {
        let mut fixture = Auto::new();
        let app = ApplicationAgents::default();
        assert!(app
            .auto_start(&fixture.id, Some(fixture.lease.clone()), None, true)
            .unwrap()
            .is_none());
        assert!(app
            .auto_start(&fixture.id, None, Some(fixture.material()), true)
            .unwrap()
            .is_none());
        assert!(app.views.lock().unwrap().is_empty());
        assert!(!fixture.root.path().join("runtime").exists());
        fixture.close().await;
    }
    #[tokio::test]
    async fn auto_start_never_initializes_journals_and_a_failed_view_is_not_replaced() {
        let mut fixture = Auto::new();
        let app = ApplicationAgents::default();
        let started = app
            .auto_start(
                &fixture.id,
                Some(fixture.lease.clone()),
                Some(fixture.material()),
                true,
            )
            .unwrap();
        assert!(started.is_some());
        // initialize=false: the unprepared workspace stays stopped, nothing is created.
        assert_eq!(outcome(&app, &fixture.id).await, RunOutcome::FailedDrained);
        assert!(!fixture.root.path().join("runtime").exists());
        assert_eq!(app.status(&fixture.id, true).unwrap().phase, "recovery");
        // A failed (needs-attention) view is left visible: no silent second attempt.
        assert!(app
            .auto_start(
                &fixture.id,
                Some(fixture.lease.clone()),
                Some(fixture.material()),
                true
            )
            .unwrap()
            .is_none());
        assert!(!fixture.root.path().join("runtime").exists());
        fixture.close().await;
    }
    #[tokio::test]
    async fn auto_start_never_undoes_a_manual_stop_or_a_never_started_connection() {
        let mut fixture = Auto::new();
        let app = ApplicationAgents::default();
        // No persisted start intent (never started, or the user stopped it): even with a
        // live listener and an imported configuration nothing is launched or created.
        assert!(app
            .auto_start(
                &fixture.id,
                Some(fixture.lease.clone()),
                Some(fixture.material()),
                false
            )
            .unwrap()
            .is_none());
        assert!(app.views.lock().unwrap().is_empty());
        assert!(!fixture.root.path().join("runtime").exists());
        // Same after a completed (Drained) run: a stop stays a stop.
        let started = app
            .auto_start(
                &fixture.id,
                Some(fixture.lease.clone()),
                Some(fixture.material()),
                true,
            )
            .unwrap();
        assert!(started.is_some());
        let _ = outcome(&app, &fixture.id).await;
        app.views.lock().unwrap().clear();
        assert!(app
            .auto_start(
                &fixture.id,
                Some(fixture.lease.clone()),
                Some(fixture.material()),
                false
            )
            .unwrap()
            .is_none());
        fixture.close().await;
    }
}
#[cfg(test)]
mod tests;

#[cfg(all(test, feature = "cloud-agent-integration-tests"))]
#[path = "cloud_application/wss_tests.rs"]
mod wss_tests;

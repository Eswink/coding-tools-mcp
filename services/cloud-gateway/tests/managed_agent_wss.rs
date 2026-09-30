//! Real PostgreSQL, verified TLS/WSS, HostAgent and local file reads under the
//! application lifecycle. FileHost is a disclosed TEST host, not a native GUI
//! approval or a substitute for a production native drain implementation.
mod host_agent_support;

use coding_tools_cloud_agent::{
    execution::{ExecutionRequest, PeerBinding},
    lifecycle::{AgentLifecycle, LifecycleError, Phase, RunHandle, RunOutcome},
    managed::{AgentStart, ManagedLocalHost},
    AgentError, HostAgent, HostAuthoritySnapshot, HostFuture, LocalHost,
};
use host_agent_support::{FileHost, Harness, Permit};
use serde_json::Value;
use std::{
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc,
    },
    time::Duration,
};
use tokio::sync::watch;
use uuid::Uuid;

const BUDGET: Duration = Duration::from_secs(8);
struct DrainHost {
    files: Arc<FileHost>,
    active: Arc<AtomicUsize>,
    hold_drain: Arc<AtomicBool>,
    fail_drain: Arc<AtomicBool>,
    drain_entered: Arc<AtomicBool>,
    connected: AtomicUsize,
}
struct Active(Arc<AtomicUsize>);
impl Drop for Active {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}
impl DrainHost {
    fn new(files: Arc<FileHost>) -> Arc<Self> {
        Arc::new(Self {
            files,
            active: Arc::new(AtomicUsize::new(0)),
            hold_drain: Arc::new(AtomicBool::new(false)),
            fail_drain: Arc::new(AtomicBool::new(false)),
            drain_entered: Arc::new(AtomicBool::new(false)),
            connected: AtomicUsize::new(0),
        })
    }
}
impl LocalHost for DrainHost {
    type Permit = Permit;
    fn connected(&self, peer: PeerBinding, seconds: u64) -> HostFuture<()> {
        self.connected.fetch_add(1, Ordering::SeqCst);
        self.files.connected(peer, seconds)
    }
    fn required_scope(&self, name: &str, _arguments: &Value) -> Option<&'static str> {
        self.files.required_scope(name, _arguments)
    }
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot> {
        self.files.snapshot()
    }
    fn admit(&self, expected: HostAuthoritySnapshot, req: ExecutionRequest) -> HostFuture<Permit> {
        self.files.admit(expected, req)
    }
    fn execute(
        &self,
        permit: Permit,
        req: ExecutionRequest,
        cancel: watch::Receiver<bool>,
    ) -> HostFuture<Value> {
        self.active.fetch_add(1, Ordering::SeqCst);
        let active = Active(self.active.clone());
        let work = self.files.execute(permit, req, cancel);
        Box::pin(async move {
            let _active = active;
            work.await
        })
    }
}
impl ManagedLocalHost for DrainHost {
    fn wait_for_drain(&self) -> HostFuture<()> {
        let (active, hold, fail, entered) = (
            self.active.clone(),
            self.hold_drain.clone(),
            self.fail_drain.clone(),
            self.drain_entered.clone(),
        );
        Box::pin(async move {
            entered.store(true, Ordering::SeqCst);
            while active.load(Ordering::SeqCst) != 0 || hold.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
            if fail.load(Ordering::SeqCst) {
                Err(AgentError::ExecutionUnknown)
            } else {
                Ok(())
            }
        })
    }
}
fn launch(
    h: &Harness,
    manager: &AgentLifecycle,
    workspace: Uuid,
    host: Arc<DrainHost>,
) -> RunHandle {
    AgentStart::new(
        h.config.clone(),
        h.key.clone(),
        h.root.join("host-state.bin"),
        false,
    )
    .unwrap()
    .launch(manager, workspace, host)
    .unwrap()
}
async fn generation(h: &Harness) -> i64 {
    sqlx::query_scalar("SELECT generation FROM ctm_agent_channel")
        .fetch_one(&h.pool)
        .await
        .unwrap()
}
async fn ready(h: &Harness, handle: &RunHandle, prior: i64) {
    tokio::time::timeout(BUDGET, async {
        loop {
            assert!(handle.outcome().is_none(), "managed Agent exited before reconciliation: {handle:?}");
            let found: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM ctm_agent_channel a JOIN ctm_grant_projection p USING(connector) WHERE a.connected=true AND a.last_seq>=5 AND a.generation>$1 AND p.reconciled=true AND p.gateway_boot=a.gateway_boot)")
                .bind(prior).fetch_one(&h.pool).await.unwrap();
            if found { break; }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }).await.expect("managed Agent did not become ready");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn managed_real_wss_reads_once_and_restart_preserves_no_replay() {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let workspace = Uuid::new_v4();
    let host = DrainHost::new(h.host.clone());
    let prior = generation(&h).await;
    let first = launch(&h, &manager, workspace, host.clone());
    ready(&h, &first, prior).await;
    assert_eq!(
        h.call(2801, "host-session-A").await["content"],
        "actual-local-file-canary"
    );
    assert_eq!(manager.stop(&first, BUDGET).await, Ok(RunOutcome::Drained));
    let prior = generation(&h).await;
    let second = launch(&h, &manager, workspace, host.clone());
    ready(&h, &second, prior).await;
    assert!(second.generation() > first.generation());
    assert_eq!(
        manager.request_stop(&first),
        Err(LifecycleError::StaleHandle)
    );
    assert_ne!(h.call(2801, "host-session-A").await["ok"], true);
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 1);
    assert_eq!(h.call(2802, "host-session-A").await["ok"], true);
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 2);
    assert_eq!(manager.shutdown(BUDGET).await, Ok(()));
    // The same durable journal remains usable by the existing runner after a
    // confirmed drain, and its original completed request still cannot replay.
    h.restart().await;
    assert_ne!(h.call(2801, "host-session-A").await["ok"], true);
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 2);
    h.stop_agent().await;
}

#[tokio::test]
async fn queued_shutdown_does_not_connect_or_initialize_another_journal() {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let host = DrainHost::new(h.host.clone());
    let path = h.root.join("must-not-be-created");
    let handle = AgentStart::new(h.config.clone(), h.key.clone(), path.clone(), true)
        .unwrap()
        .launch(&manager, Uuid::new_v4(), host.clone())
        .unwrap();
    manager.request_shutdown(); // Current-thread task cannot have been polled yet.
    assert_eq!(handle.wait(BUDGET).await, Ok(RunOutcome::NotStarted));
    assert_eq!(host.connected.load(Ordering::SeqCst), 0);
    assert!(!host.drain_entered.load(Ordering::SeqCst));
    assert!(!path.exists());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn real_channel_stop_timeout_keeps_slot_and_journal_until_drain() {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let host = DrainHost::new(h.host.clone());
    host.hold_drain.store(true, Ordering::SeqCst);
    let workspace = Uuid::new_v4();
    let prior = generation(&h).await;
    let handle = launch(&h, &manager, workspace, host.clone());
    ready(&h, &handle, prior).await;
    assert_eq!(h.call(2803, "host-session-A").await["ok"], true);
    assert_eq!(
        manager.stop(&handle, Duration::from_millis(50)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert_eq!(handle.phase().unwrap(), Some(Phase::Stopping));
    assert!(host.drain_entered.load(Ordering::SeqCst));
    assert!(matches!(
        AgentStart::new(
            h.config.clone(),
            h.key.clone(),
            h.root.join("host-state.bin"),
            false
        )
        .unwrap()
        .launch(&manager, workspace, host.clone()),
        Err(LifecycleError::Busy)
    ));
    assert!(matches!(
        HostAgent::open(
            &h.config,
            &h.key,
            &h.root.join("host-state.bin"),
            false,
            host.clone()
        ),
        Err(AgentError::Journal)
    ));
    host.hold_drain.store(false, Ordering::SeqCst);
    assert_eq!(handle.wait(BUDGET).await, Ok(RunOutcome::Drained));
    assert!(HostAgent::open(
        &h.config,
        &h.key,
        &h.root.join("host-state.bin"),
        false,
        host
    )
    .is_ok());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn managed_shutdown_is_permanent_and_foreign_requests_stay_private() {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let host = DrainHost::new(h.host.clone());
    let prior = generation(&h).await;
    let handle = launch(&h, &manager, Uuid::new_v4(), host.clone());
    ready(&h, &handle, prior).await;
    let denied = h.call(2804, "foreign").await;
    assert_ne!(denied["ok"], true);
    assert!(!denied.to_string().contains("actual-local-file-canary"));
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 0);
    manager.shutdown(BUDGET).await.unwrap();
    let connections = host.connected.load(Ordering::SeqCst);
    let late = AgentStart::new(
        h.config.clone(),
        h.key.clone(),
        h.root.join("late-state"),
        true,
    )
    .unwrap()
    .launch(&manager, Uuid::new_v4(), host.clone());
    assert!(matches!(late, Err(LifecycleError::Closed)));
    assert!(!h.root.join("late-state").exists());
    assert_eq!(host.connected.load(Ordering::SeqCst), connections);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn actual_agent_drain_error_quarantines_workspace_instead_of_restarting() {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    let manager = AgentLifecycle::new(1).unwrap();
    let host = DrainHost::new(h.host.clone());
    host.fail_drain.store(true, Ordering::SeqCst);
    let workspace = Uuid::new_v4();
    let prior = generation(&h).await;
    let handle = launch(&h, &manager, workspace, host.clone());
    ready(&h, &handle, prior).await;
    assert_eq!(
        manager.stop(&handle, BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
    assert_eq!(handle.phase().unwrap(), Some(Phase::Unconfirmed));
    assert!(matches!(
        AgentStart::new(
            h.config.clone(),
            h.key.clone(),
            h.root.join("host-state.bin"),
            false
        )
        .unwrap()
        .launch(&manager, workspace, host),
        Err(LifecycleError::Busy)
    ));
}

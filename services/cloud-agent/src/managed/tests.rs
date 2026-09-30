use super::*;
use crate::{
    execution::ExecutionRequest,
    lifecycle::{Phase, RunOutcome},
    HostAuthoritySnapshot,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use serde_json::{json, Value};
use std::{
    fs,
    sync::atomic::{AtomicBool, AtomicUsize, Ordering},
    time::Duration,
};
use tokio::sync::watch;
const BUDGET: Duration = Duration::from_secs(3);
struct Host {
    draining: Arc<AtomicBool>,
    drain_calls: Arc<AtomicUsize>,
    uncertain: bool,
}
impl LocalHost for Host {
    type Permit = ();
    fn required_scope(&self, _: &str, _: &Value) -> Option<&'static str> {
        None
    }
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot> {
        Box::pin(async { Err(AgentError::LocalAuthority) })
    }
    fn admit(&self, _: HostAuthoritySnapshot, _: ExecutionRequest) -> HostFuture<()> {
        Box::pin(async { Err(AgentError::LocalAuthority) })
    }
    fn execute(&self, _: (), _: ExecutionRequest, _: watch::Receiver<bool>) -> HostFuture<Value> {
        Box::pin(async { Err(AgentError::LocalAuthority) })
    }
}
impl ManagedLocalHost for Host {
    fn wait_for_drain(&self) -> HostFuture<()> {
        let hold = self.draining.clone();
        let calls = self.drain_calls.clone();
        let uncertain = self.uncertain;
        Box::pin(async move {
            calls.fetch_add(1, Ordering::SeqCst);
            while hold.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
            if uncertain {
                Err(AgentError::ExecutionUnknown)
            } else {
                Ok(())
            }
        })
    }
}
struct Fixture {
    root: PathBuf,
    config: Vec<u8>,
    key: Vec<u8>,
    host: Arc<Host>,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!("managed-agent-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let root = root.canonicalize().unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        let pair = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
        let config=serde_json::to_vec(&json!({"origin":"https://gateway.example.invalid","prefix":"/coding-tools",
            "connector":Uuid::new_v4(),"device":Uuid::new_v4(),"device_epoch":1,"authority_epoch":1,
            "public_key":URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),"revision_file":root.join("unused"),
            "ca_der_file":root.join("missing-ca.der"),"run_seconds":1})).unwrap();
        let key =
            serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs8.as_ref())})).unwrap();
        Self {
            root,
            config,
            key,
            host: Arc::new(Host {
                draining: Arc::new(AtomicBool::new(false)),
                drain_calls: Arc::new(AtomicUsize::new(0)),
                uncertain: false,
            }),
        }
    }
    fn start(&self, initialize: bool) -> AgentStart {
        AgentStart::new(
            self.config.clone(),
            self.key.clone(),
            self.root.join("state"),
            initialize,
        )
        .unwrap()
    }
    async fn wait_drain(&self) {
        tokio::time::timeout(BUDGET, async {
            while self.host.drain_calls.load(Ordering::SeqCst) == 0 {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
#[tokio::test]
async fn queued_shutdown_does_not_initialize_journal_or_call_host() {
    let f = Fixture::new();
    let m = AgentLifecycle::new(1).unwrap();
    let h = f
        .start(true)
        .launch(&m, Uuid::new_v4(), f.host.clone())
        .unwrap();
    m.request_shutdown();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::NotStarted));
    assert!(!f.root.join("state").exists());
    assert_eq!(f.host.drain_calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn duplicate_registration_does_not_open_or_replace_state() {
    let f = Fixture::new();
    let m = AgentLifecycle::new(1).unwrap();
    let workspace = Uuid::new_v4();
    let h = f.start(true).launch(&m, workspace, f.host.clone()).unwrap();
    assert!(matches!(
        f.start(true).launch(&m, workspace, f.host.clone()),
        Err(LifecycleError::Busy)
    ));
    m.request_stop(&h).unwrap();
    h.wait(BUDGET).await.unwrap();
    assert!(!f.root.join("state").exists());
}
#[tokio::test]
async fn bad_ca_fails_without_tls_fallback_and_reports_drained_failure() {
    let f = Fixture::new();
    let m = AgentLifecycle::new(1).unwrap();
    let h = f
        .start(true)
        .launch(&m, Uuid::new_v4(), f.host.clone())
        .unwrap();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::FailedDrained));
    assert_eq!(f.host.drain_calls.load(Ordering::SeqCst), 1);
    assert!(f.root.join("state").is_file());
}
#[tokio::test]
async fn stop_timeout_retains_actual_host_journal_lock_until_native_drain() {
    let f = Fixture::new();
    f.host.draining.store(true, Ordering::SeqCst);
    let m = AgentLifecycle::new(1).unwrap();
    let workspace = Uuid::new_v4();
    let h = f.start(true).launch(&m, workspace, f.host.clone()).unwrap();
    f.wait_drain().await;
    assert_eq!(
        m.stop(&h, Duration::from_millis(10)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert_eq!(h.phase().unwrap(), Some(Phase::Stopping));
    assert!(matches!(
        HostAgent::open(
            &f.config,
            &f.key,
            &f.root.join("state"),
            false,
            f.host.clone()
        ),
        Err(AgentError::Journal)
    ));
    f.host.draining.store(false, Ordering::SeqCst);
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::FailedDrained));
    assert!(HostAgent::open(
        &f.config,
        &f.key,
        &f.root.join("state"),
        false,
        f.host.clone()
    )
    .is_ok());
}
#[tokio::test]
async fn native_unknown_drain_quarantines_agent_instead_of_restarting() {
    let mut f = Fixture::new();
    Arc::get_mut(&mut f.host).unwrap().uncertain = true;
    let m = AgentLifecycle::new(1).unwrap();
    let workspace = Uuid::new_v4();
    let h = f.start(true).launch(&m, workspace, f.host.clone()).unwrap();
    assert_eq!(
        h.wait(BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
    assert!(matches!(
        f.start(false).launch(&m, workspace, f.host.clone()),
        Err(LifecycleError::Busy)
    ));
}
#[tokio::test]
async fn existing_journal_is_not_reinitialized_or_overwritten() {
    let f = Fixture::new();
    fs::write(f.root.join("state"), b"owned-corrupt-marker").unwrap();
    let m = AgentLifecycle::new(1).unwrap();
    let h = f
        .start(true)
        .launch(&m, Uuid::new_v4(), f.host.clone())
        .unwrap();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::FailedDrained));
    assert_eq!(
        fs::read(f.root.join("state")).unwrap(),
        b"owned-corrupt-marker"
    );
    assert_eq!(f.host.drain_calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn missing_restart_journal_is_not_automatically_created() {
    let f = Fixture::new();
    let m = AgentLifecycle::new(1).unwrap();
    let h = f
        .start(false)
        .launch(&m, Uuid::new_v4(), f.host.clone())
        .unwrap();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::FailedDrained));
    assert!(!f.root.join("state").exists());
}
#[test]
fn inputs_are_bounded_and_debug_never_contains_keys_or_paths() {
    let f = Fixture::new();
    let spec = f.start(false);
    let text = format!("{spec:?}");
    assert!(!text.contains(&f.root.display().to_string()));
    assert!(!text.contains("pkcs8"));
    assert!(AgentStart::new(
        f.config.clone(),
        vec![1; 16_385],
        f.root.join("other"),
        false
    )
    .is_err());
    assert!(AgentStart::new(
        f.config.clone(),
        f.key.clone(),
        PathBuf::from("relative"),
        false
    )
    .is_err());
}

//! These tests exercise real loopback TCP and the production run/stop API.
//! They do not claim authenticated WSS, native approval or desktop integration.
use crate::*;
use futures_util::future::BoxFuture;
use ring::{rand::SystemRandom, signature::Ed25519KeyPair};
use serde_json::Value;
use std::{path::PathBuf, sync::Arc, time::Duration};
use tokio::{net::TcpListener, task::JoinHandle};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;
use zeroize::Zeroizing;

struct DenyingHost;
impl NativeHost for DenyingHost {
    type Proof = ();
    fn connected(&self, _: &Session) -> Result<()> { Err(LinkError::NotApproved) }
    fn observe<'a>(&'a self, _: &'a Session) -> BoxFuture<'a, Result<Observation<()>>> {
        Box::pin(async { Err(LinkError::NotApproved) })
    }
    fn approval(&self, _: ApprovalCall) -> BoxFuture<'_, Result<Value>> {
        Box::pin(async { Err(LinkError::NotApproved) })
    }
    fn execute(&self, _: ExecutionCall<()>) -> BoxFuture<'_, Result<Value>> {
        Box::pin(async { Err(LinkError::NotApproved) })
    }
}

struct Fixture {
    _temp: tempfile::TempDir,
    cfg: DeviceConfig,
    key: Arc<DeviceKey>,
    journal: Arc<Journal>,
    listener: TcpListener,
}
impl Fixture {
    async fn new() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let cfg = DeviceConfig::new(format!("https://127.0.0.1:{port}/coding-tools"),
            Uuid::new_v4(), Uuid::new_v4(), 1).unwrap();
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        let key = Arc::new(DeviceKey::from_pkcs8(Zeroizing::new(pkcs8.as_ref().to_vec())).unwrap());
        let temp = tempfile::tempdir().unwrap();
        let root: PathBuf = temp.path().canonicalize().unwrap();
        #[cfg(unix)] {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        let journal = Arc::new(Journal::create(&root, &cfg, key.clone()).unwrap());
        Self { _temp: temp, cfg, key, journal, listener }
    }
    fn link(&self) -> Arc<NativeLink<DenyingHost>> {
        Arc::new(NativeLink::new(self.cfg.clone(), self.key.clone(), self.journal.clone(), Arc::new(DenyingHost), None).unwrap())
    }
    async fn start(&self, link: Arc<NativeLink<DenyingHost>>) -> (CancellationToken, JoinHandle<Result<()>>, tokio::net::TcpStream) {
        let stop = CancellationToken::new();
        let signal = stop.clone();
        let task = tokio::spawn(async move { link.run(signal).await });
        // Keep the TCP peer open: the genuine TLS handshake remains pending.
        let (peer, _) = tokio::time::timeout(Duration::from_secs(5), self.listener.accept()).await.unwrap().unwrap();
        (stop, task, peer)
    }
}

#[tokio::test]
async fn different_links_sharing_journal_cannot_start_concurrently() {
    let fixture = Fixture::new().await;
    let (stop, first, peer) = fixture.start(fixture.link()).await;
    let second_link = fixture.link();
    let second_stop = CancellationToken::new();
    let signal = second_stop.clone();
    let mut second = tokio::spawn(async move { second_link.run(signal).await });
    let result = tokio::time::timeout(Duration::from_millis(250), &mut second).await;
    let rejected = matches!(result, Ok(Ok(Err(LinkError::Capacity))));
    stop.cancel(); second_stop.cancel();
    tokio::time::timeout(Duration::from_secs(6), first).await.unwrap().unwrap().unwrap();
    if result.is_err() { let _ = tokio::time::timeout(Duration::from_secs(6), second).await; }
    drop(peer);
    assert!(rejected, "NATIVE_CONCURRENT_CONNECTION_OWNER");
}

#[tokio::test]
async fn identical_link_cannot_run_two_connection_loops() {
    let fixture = Fixture::new().await;
    let link = fixture.link();
    let (stop, task, peer) = fixture.start(link.clone()).await;
    assert_eq!(link.run(CancellationToken::new()).await, Err(LinkError::Capacity));
    stop.cancel();
    assert_eq!(tokio::time::timeout(Duration::from_secs(6), task).await.unwrap().unwrap(), Ok(()));
    drop(peer);
}

#[tokio::test]
async fn stop_waits_for_native_work_not_just_socket_closure() {
    let fixture = Fixture::new().await;
    let link = fixture.link();
    let (stop, mut task, peer) = fixture.start(link.clone()).await;
    let work = fixture.journal.lifecycle.worker().unwrap();
    stop.cancel();
    assert!(tokio::time::timeout(Duration::from_millis(50), &mut task).await.is_err());
    assert!(link.connection_status().loop_running);
    assert_eq!(link.connection_status().active_requests, 1);
    work.finish();
    assert_eq!(tokio::time::timeout(Duration::from_secs(2), task).await.unwrap().unwrap(), Ok(()));
    assert!(!link.connection_status().loop_running);
    drop(peer);
}

#[tokio::test]
async fn aborted_loop_cannot_overlap_its_surviving_worker() {
    let fixture = Fixture::new().await;
    let link = fixture.link();
    let (_stop, task, peer) = fixture.start(link.clone()).await;
    let work = fixture.journal.lifecycle.worker().unwrap();
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert!(!link.connection_status().loop_running);
    assert_eq!(link.run(CancellationToken::new()).await, Err(LinkError::Capacity));
    work.finish();
    let signal = CancellationToken::new(); signal.cancel();
    assert_eq!(link.run(signal).await, Ok(()));
    drop(peer);
}

#[tokio::test]
async fn unfinished_worker_drop_returns_recovery_not_success() {
    let fixture = Fixture::new().await;
    let link = fixture.link();
    let (stop, task, peer) = fixture.start(link.clone()).await;
    let work = fixture.journal.lifecycle.worker().unwrap();
    stop.cancel(); drop(work);
    assert_eq!(tokio::time::timeout(Duration::from_secs(2), task).await.unwrap().unwrap(), Err(LinkError::Journal));
    assert!(link.connection_status().recovery_required);
    assert_eq!(fixture.link().run(CancellationToken::new()).await, Err(LinkError::Journal));
    drop(peer);
}

#[tokio::test]
async fn precancelled_run_does_not_connect_or_create_approval() {
    let fixture = Fixture::new().await;
    let signal = CancellationToken::new(); signal.cancel();
    let link = fixture.link();
    assert_eq!(link.run(signal).await, Ok(()));
    assert!(tokio::time::timeout(Duration::from_millis(50), fixture.listener.accept()).await.is_err());
    assert_eq!(link.connection_status().active_requests, 0);
}

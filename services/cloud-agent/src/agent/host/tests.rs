use super::*;
use crate::{
    canonical::digest_json as canonical_digest,
    projection::{ExecutionState, LocalLease, ProjectionPhase},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use std::{
    fs,
    io::{Seek, SeekFrom, Write},
    path::PathBuf,
    sync::atomic::{AtomicUsize, Ordering},
};
use uuid::Uuid;

struct Fixture {
    root: PathBuf,
    config: Vec<u8>,
    key: Vec<u8>,
    host: Arc<TestHost>,
    peer: PeerBinding,
}
struct TestHost {
    state: Mutex<HostAuthoritySnapshot>,
    calls: AtomicUsize,
    admit_delay: Duration,
    execution_delay: Duration,
    output: Value,
}
struct Permit;
impl LocalHost for TestHost {
    type Permit = Permit;
    fn required_scope(&self, name: &str, _arguments: &Value) -> Option<&'static str> {
        match name {
            "workspace_probe" | "read_file" => Some("files.read"),
            _ => None,
        }
    }
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot> {
        let state = self.state.lock().unwrap().clone();
        Box::pin(async move { Ok(state) })
    }
    fn admit(&self, expected: HostAuthoritySnapshot, _: ExecutionRequest) -> HostFuture<Permit> {
        let matches = self.state.lock().unwrap().eq(&expected);
        let delay = self.admit_delay;
        Box::pin(async move {
            tokio::time::sleep(delay).await;
            if matches {
                Ok(Permit)
            } else {
                Err(AgentError::LocalAuthority)
            }
        })
    }
    fn execute(
        &self,
        _: Permit,
        _: ExecutionRequest,
        mut cancel: watch::Receiver<bool>,
    ) -> HostFuture<Value> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        let delay = self.execution_delay;
        let out = self.output.clone();
        Box::pin(async move {
            tokio::select! {
                _=cancel.changed()=>Err(AgentError::ExecutionUnknown),
                _=tokio::time::sleep(delay)=>Ok(out),
            }
        })
    }
}
impl Fixture {
    fn new(admit_delay: Duration, execution_delay: Duration, output: Value) -> Self {
        let root = std::env::temp_dir().join(format!("ctm-host-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let root = root.canonicalize().unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let pkcs = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        let key = Ed25519KeyPair::from_pkcs8(pkcs.as_ref()).unwrap();
        let connector = Uuid::new_v4();
        let device = Uuid::new_v4();
        let config = serde_json::to_vec(&json!({
            "origin":"https://gateway.example.invalid","prefix":"/coding-tools",
            "connector":connector,"device":device,"device_epoch":1,"authority_epoch":1,
            "public_key":URL_SAFE_NO_PAD.encode(key.public_key().as_ref()),
            "revision_file":root.join("legacy-state"),"run_seconds":30,
        }))
        .unwrap();
        let key =
            serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs.as_ref())})).unwrap();
        let at = now().unwrap();
        let snapshot = HostAuthoritySnapshot::new(
            1,
            1,
            1,
            ProjectionPhase::Active,
            ExecutionState::Online,
            Some(LocalLease {
                id: Uuid::new_v4(),
                conversation: URL_SAFE_NO_PAD.encode([3; 32]),
                issued_at: at - 1,
                expires_at: at + 180,
                scopes: vec!["files.read".into()],
            }),
            None,
        )
        .unwrap();
        Self {
            root,
            config,
            key,
            host: Arc::new(TestHost {
                state: Mutex::new(snapshot),
                calls: AtomicUsize::new(0),
                admit_delay,
                execution_delay,
                output,
            }),
            peer: PeerBinding {
                connector,
                device,
                device_epoch: 1,
                gateway_boot: Uuid::new_v4(),
                channel_session: Uuid::new_v4(),
                channel_generation: 1,
            },
        }
    }
    fn simple() -> Self {
        Self::new(
            Duration::ZERO,
            Duration::ZERO,
            json!({"ok":true,"fixture":"read-canary"}),
        )
    }
    fn agent(&self, initialize: bool) -> Result<HostAgent<TestHost>, AgentError> {
        HostAgent::open(
            &self.config,
            &self.key,
            &self.root.join("state.bin"),
            initialize,
            self.host.clone(),
        )
    }
    fn request(&self, agent: &HostAgent<TestHost>) -> (ExecutionRequest, ProjectedHost) {
        let snapshot = self.host.state.lock().unwrap().clone();
        let revision = agent.worker.revision().unwrap();
        let arguments = json!({});
        let request = ExecutionRequest {
            binding: crate::execution::ExecutionBinding {
                request_id: Uuid::new_v4(),
                peer: self.peer.clone(),
                grant_id: snapshot.grant.as_ref().unwrap().id,
                grant_revision: revision,
                authority_epoch: snapshot.epoch,
                conversation: snapshot.grant.as_ref().unwrap().conversation.clone(),
                scope: "files.read".into(),
                tool: "workspace_probe".into(),
                arguments_hash: canonical_digest(&arguments, 4096).unwrap(),
                deadline: now().unwrap() + 30,
            },
            arguments,
        };
        (
            request,
            ProjectedHost {
                snapshot,
                revision,
                until: now().unwrap() + 30,
            },
        )
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
#[test]
fn host_state_is_redacted_and_validates_shape() {
    let f = Fixture::simple();
    let s = f.host.state.lock().unwrap().clone();
    assert_eq!(format!("{s:?}"), "HostAuthoritySnapshot([REDACTED])");
    assert!(
        HostAuthoritySnapshot::new(0, 1, 1, s.phase, s.execution, s.grant.clone(), None).is_err()
    );
    assert!(
        HostAuthoritySnapshot::new(1, 1, 0, s.phase, s.execution, s.grant.clone(), None).is_err()
    );
    assert!(HostAuthoritySnapshot::new(
        1,
        1,
        1,
        ProjectionPhase::Free,
        ExecutionState::Online,
        None,
        None
    )
    .is_err());
    assert!(HostAuthoritySnapshot::new(
        1,
        1,
        1,
        ProjectionPhase::Free,
        ExecutionState::Offline,
        s.grant,
        None
    )
    .is_err());
}
#[test]
fn initialization_is_explicit_and_never_overwrites() {
    let f = Fixture::simple();
    assert!(matches!(f.agent(false), Err(AgentError::Journal)));
    let a = f.agent(true).unwrap();
    assert!(matches!(f.agent(true), Err(AgentError::Journal)));
    drop(a);
    assert!(f.agent(false).is_ok());
}
#[test]
fn concurrent_journal_ownership_is_rejected() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    assert!(matches!(f.agent(false), Err(AgentError::Journal)));
    drop(a);
    assert!(f.agent(false).is_ok());
}
#[test]
fn journal_revisions_are_reserved_once_and_never_reused_after_restart() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let first = a.worker.revision().unwrap();
    let mut last = first;
    for _ in 0..50 {
        last = a.worker.revision().unwrap();
    }
    assert!(last > first);
    assert_eq!(
        fs::metadata(f.root.join("state.bin")).unwrap().len(),
        104 + 168
    );
    drop(a);
    let next = f.agent(false).unwrap().worker.revision().unwrap();
    assert!(next > last);
    assert_eq!(next, 1025);
}
#[test]
fn partial_journal_record_is_rejected_not_truncated() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    a.worker.revision().unwrap();
    drop(a);
    let path = f.root.join("state.bin");
    let old = fs::metadata(&path).unwrap().len();
    fs::OpenOptions::new()
        .write(true)
        .open(&path)
        .unwrap()
        .set_len(old - 1)
        .unwrap();
    assert!(matches!(f.agent(false), Err(AgentError::Journal)));
    assert_eq!(fs::metadata(path).unwrap().len(), old - 1);
}
#[test]
fn journal_signature_tampering_fails_closed() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    a.worker.revision().unwrap();
    drop(a);
    let path = f.root.join("state.bin");
    let mut file = fs::OpenOptions::new().write(true).open(&path).unwrap();
    file.seek(SeekFrom::Start(121)).unwrap();
    file.write_all(&[99]).unwrap();
    file.sync_all().unwrap();
    drop(file);
    assert!(matches!(f.agent(false), Err(AgentError::Journal)));
}
#[test]
fn journal_reordered_records_fail_closed() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, _) = f.request(&a);
    a.worker
        .journal
        .lock()
        .unwrap()
        .claim(&a.worker.signer, &r)
        .unwrap();
    drop(a);
    let path = f.root.join("state.bin");
    let mut bytes = fs::read(&path).unwrap();
    let a = bytes[104..272].to_vec();
    let b = bytes[272..440].to_vec();
    bytes[104..272].copy_from_slice(&b);
    bytes[272..440].copy_from_slice(&a);
    fs::write(&path, bytes).unwrap();
    assert!(matches!(f.agent(false), Err(AgentError::Journal)));
}
#[test]
fn journal_binding_cannot_move_to_another_device() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    drop(a);
    let mut cfg: Value = serde_json::from_slice(&f.config).unwrap();
    cfg["device"] = json!(Uuid::new_v4());
    let cfg = serde_json::to_vec(&cfg).unwrap();
    assert!(matches!(
        HostAgent::open(
            &cfg,
            &f.key,
            &f.root.join("state.bin"),
            false,
            f.host.clone()
        ),
        Err(AgentError::Journal)
    ));
}
#[cfg(unix)]
#[test]
fn journal_rejects_symlinks_and_world_readable_files() {
    use std::os::unix::fs::{symlink, PermissionsExt};
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    drop(a);
    let path = f.root.join("state.bin");
    let real = f.root.join("real.bin");
    fs::rename(&path, &real).unwrap();
    symlink(&real, &path).unwrap();
    assert!(f.agent(false).is_err());
    fs::remove_file(&path).unwrap();
    fs::rename(&real, &path).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
    assert!(f.agent(false).is_err());
}
#[test]
fn completed_dispatch_id_is_retained_across_restart() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, _) = f.request(&a);
    let mut journal = a.worker.journal.lock().unwrap();
    journal.claim(&a.worker.signer, &r).unwrap();
    journal.complete(&a.worker.signer, &r).unwrap();
    drop(journal);
    drop(a);
    let a = f.agent(false).unwrap();
    assert_eq!(
        a.worker.journal.lock().unwrap().claim(&a.worker.signer, &r),
        Err(AgentError::Duplicate)
    );
}
#[test]
fn unfinished_dispatch_is_not_replayed_after_restart() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, _) = f.request(&a);
    a.worker
        .journal
        .lock()
        .unwrap()
        .claim(&a.worker.signer, &r)
        .unwrap();
    drop(a);
    let a = f.agent(false).unwrap();
    assert_eq!(
        a.worker.journal.lock().unwrap().claim(&a.worker.signer, &r),
        Err(AgentError::Duplicate)
    );
}
#[tokio::test]
async fn exact_native_permit_executes_and_returns_bounded_result() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    let result = a.worker.execute_inner(&r, &f.peer, &p).await.unwrap();
    assert_eq!(result["fixture"], "read-canary");
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 1);
}
#[tokio::test]
async fn wrong_conversation_or_scope_cannot_reach_host_execution() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (mut r, p) = f.request(&a);
    r.binding.conversation = URL_SAFE_NO_PAD.encode([4; 32]);
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
    r.binding.conversation = p.snapshot.grant.as_ref().unwrap().conversation.clone();
    r.binding.scope = "exec.run".into();
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn mutated_arguments_and_foreign_channel_cannot_execute() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (mut r, p) = f.request(&a);
    r.arguments = json!({"path":"private-canary"});
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Protocol)
    );
    r.arguments = json!({});
    r.binding.peer.channel_session = Uuid::new_v4();
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Protocol)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn paused_then_resumed_host_rejects_the_old_projection_generation() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    {
        let mut s = f.host.state.lock().unwrap();
        s.execution = ExecutionState::Offline;
        s.generation += 1;
    }
    {
        let mut s = f.host.state.lock().unwrap();
        s.execution = ExecutionState::Online;
        s.generation += 1;
    }
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn native_revision_or_epoch_change_rejects_stale_admission() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    f.host.state.lock().unwrap().revision += 1;
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
    f.host.state.lock().unwrap().epoch += 1;
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn expired_projection_is_not_authority_even_with_a_live_grant() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, mut p) = f.request(&a);
    p.until = now().unwrap();
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::LocalAuthority)
    );
}
#[tokio::test]
async fn duplicate_claim_does_not_poison_the_original_invocation() {
    let f = Fixture::new(
        Duration::ZERO,
        Duration::from_millis(150),
        json!({"ok":true}),
    );
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    let first = tokio::spawn(
        a.worker
            .clone()
            .execute(r.clone(), f.peer.clone(), p.clone()),
    );
    while f.host.calls.load(Ordering::SeqCst) == 0 {
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Duplicate)
    );
    assert_eq!(first.await.unwrap().1["ok"], true);
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 1);
}
#[tokio::test]
async fn revocation_during_execution_suppresses_private_output() {
    let f = Fixture::new(
        Duration::ZERO,
        Duration::from_millis(150),
        json!({"ok":true,"private":"secret-fixture-output"}),
    );
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    let first = tokio::spawn(a.worker.clone().execute(r, f.peer.clone(), p));
    while f.host.calls.load(Ordering::SeqCst) == 0 {
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    {
        let mut s = f.host.state.lock().unwrap();
        s.phase = ProjectionPhase::Draining;
        s.execution = ExecutionState::Offline;
        s.revision += 1;
    }
    let value = first.await.unwrap().1;
    assert_eq!(value["ok"], false);
    assert_eq!(value["outcome_unknown"], true);
    assert!(!value.to_string().contains("secret-fixture-output"));
}
#[tokio::test]
async fn admission_wait_cannot_outlive_the_request_deadline() {
    let f = Fixture::new(
        Duration::from_millis(1600),
        Duration::ZERO,
        json!({"ok":true}),
    );
    let a = f.agent(true).unwrap();
    let (mut r, p) = f.request(&a);
    r.binding.deadline = now().unwrap() + 1;
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::ExecutionUnknown)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn oversized_result_is_unknown_and_cannot_be_replayed() {
    let f = Fixture::new(
        Duration::ZERO,
        Duration::ZERO,
        json!({"ok":true,"data":"x".repeat(8192)}),
    );
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::ExecutionUnknown)
    );
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Duplicate)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 1);
}
#[tokio::test]
async fn cancellation_leaves_a_durable_non_replayable_claim() {
    let f = Fixture::new(Duration::ZERO, Duration::from_secs(30), json!({"ok":true}));
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    let task = tokio::spawn(
        a.worker
            .clone()
            .execute(r.clone(), f.peer.clone(), p.clone()),
    );
    while f.host.calls.load(Ordering::SeqCst) == 0 {
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Duplicate)
    );
}
#[tokio::test]
async fn local_capacity_rejection_does_not_claim_or_queue_work() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (r, p) = f.request(&a);
    let held = a
        .worker
        .capacity
        .clone()
        .acquire_many_owned(MAX_HOST_IN_FLIGHT as u32)
        .await
        .unwrap();
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Capacity)
    );
    assert_eq!(f.host.calls.load(Ordering::SeqCst), 0);
    drop(held);
    assert_eq!(
        a.worker.execute_inner(&r, &f.peer, &p).await.unwrap()["ok"],
        true
    );
}
#[test]
fn journal_does_not_persist_command_arguments_or_output() {
    let f = Fixture::simple();
    let a = f.agent(true).unwrap();
    let (mut r, _) = f.request(&a);
    r.arguments = json!({"sensitive-fixture-path":"not-for-cloud-or-state"});
    r.binding.arguments_hash = canonical_digest(&r.arguments, 4096).unwrap();
    a.worker
        .journal
        .lock()
        .unwrap()
        .claim(&a.worker.signer, &r)
        .unwrap();
    let bytes = fs::read(f.root.join("state.bin")).unwrap();
    assert!(!bytes
        .windows(b"sensitive-fixture-path".len())
        .any(|x| x == b"sensitive-fixture-path"));
    assert!(!String::from_utf8_lossy(&bytes).contains("not-for-cloud-or-state"));
}

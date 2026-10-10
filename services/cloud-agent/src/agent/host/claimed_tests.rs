use super::*;
use crate::{
    canonical::digest_json,
    projection::{ExecutionState, LocalLease, ProjectionPhase},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicUsize, Ordering},
};
use uuid::Uuid;

struct ClaimedHost {
    state: HostAuthoritySnapshot,
    legacy: AtomicUsize,
    claimed: AtomicUsize,
    retained: Mutex<Option<ClaimedDispatch>>,
    unknown: bool,
}
impl LocalHost for ClaimedHost {
    type Permit = ();
    fn required_scope(&self, _: &str, _: &Value) -> Option<&'static str> {
        Some("files.read")
    }
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot> {
        let state = self.state.clone();
        Box::pin(async move { Ok(state) })
    }
    fn admit(&self, expected: HostAuthoritySnapshot, _: ExecutionRequest) -> HostFuture<()> {
        let matches = expected == self.state;
        Box::pin(async move {
            if matches {
                Ok(())
            } else {
                Err(AgentError::LocalAuthority)
            }
        })
    }
    fn execute(&self, _: (), _: ExecutionRequest, _: watch::Receiver<bool>) -> HostFuture<Value> {
        self.legacy.fetch_add(1, Ordering::SeqCst);
        Box::pin(async { Err(AgentError::ExecutionUnknown) })
    }
    fn execute_claimed(
        &self,
        _: (),
        request: ExecutionRequest,
        _: watch::Receiver<bool>,
        claimed: ClaimedDispatch,
    ) -> HostFuture<Value> {
        let valid = claimed.verify_for(self, &request, now().unwrap()).is_ok();
        self.claimed.fetch_add(1, Ordering::SeqCst);
        *self.retained.lock().unwrap() = Some(claimed);
        let unknown = self.unknown;
        Box::pin(async move {
            if !valid {
                Err(AgentError::LocalAuthority)
            } else if unknown {
                Err(AgentError::ExecutionUnknown)
            } else {
                Ok(json!({"ok":true,"actual_claim":true}))
            }
        })
    }
}
struct Fixture {
    root: PathBuf,
    config: Vec<u8>,
    key: Vec<u8>,
    peer: PeerBinding,
    host: Arc<ClaimedHost>,
}
impl Fixture {
    fn new(unknown: bool) -> Self {
        let root = std::env::temp_dir().join(format!("ctm-claimed-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        let root = root.canonicalize().unwrap();
        // Existing HostJournal fixture contract; process-local temporary owner.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let pkcs = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        let pair = Ed25519KeyPair::from_pkcs8(pkcs.as_ref()).unwrap();
        let connector = Uuid::new_v4();
        let device = Uuid::new_v4();
        let config = serde_json::to_vec(&json!({"origin":"https://gateway.example.invalid","prefix":"/coding-tools",
            "connector":connector,"device":device,"device_epoch":1,"authority_epoch":1,
            "public_key":URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),"revision_file":root.join("legacy"),"run_seconds":30})).unwrap();
        let key =
            serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs.as_ref())})).unwrap();
        let at = now().unwrap();
        let state = HostAuthoritySnapshot::new(
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
            peer: PeerBinding {
                connector,
                device,
                device_epoch: 1,
                gateway_boot: Uuid::new_v4(),
                channel_session: Uuid::new_v4(),
                channel_generation: 1,
            },
            host: Arc::new(ClaimedHost {
                state,
                legacy: AtomicUsize::new(0),
                claimed: AtomicUsize::new(0),
                retained: Mutex::new(None),
                unknown,
            }),
        }
    }
    fn open(&self, initialize: bool) -> Result<HostAgent<ClaimedHost>, AgentError> {
        HostAgent::open(
            &self.config,
            &self.key,
            &self.root.join("state.bin"),
            initialize,
            self.host.clone(),
        )
    }
    fn request(&self, agent: &HostAgent<ClaimedHost>) -> (ExecutionRequest, ProjectedHost) {
        let state = self.host.state.clone();
        let revision = agent.worker.revision().unwrap();
        let arguments = json!({"path":"input.txt"});
        let request = ExecutionRequest {
            binding: crate::execution::ExecutionBinding {
                request_id: Uuid::new_v4(),
                peer: self.peer.clone(),
                grant_id: state.grant().unwrap().id,
                grant_revision: revision,
                authority_epoch: state.epoch(),
                conversation: state.grant().unwrap().conversation.clone(),
                scope: "files.read".into(),
                tool: "read_file".into(),
                arguments_hash: digest_json(&arguments, 4096).unwrap(),
                deadline: now().unwrap() + 30,
            },
            arguments,
        };
        (
            request,
            ProjectedHost {
                snapshot: state,
                revision,
                until: now().unwrap() + 30,
            },
        )
    }
    async fn dispatch(&self) -> (HostAgent<ClaimedHost>, ExecutionRequest) {
        let agent = self.open(true).unwrap();
        let (request, projected) = self.request(&agent);
        let result = agent
            .worker
            .execute_inner(&request, &self.peer, &projected)
            .await;
        if self.host.unknown {
            assert_eq!(result, Err(AgentError::ExecutionUnknown));
        } else {
            assert_eq!(result, Ok(json!({"ok":true,"actual_claim":true})));
        }
        (agent, request)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        self.host.retained.lock().unwrap().take();
        let _ = fs::remove_dir_all(&self.root);
    }
}
#[tokio::test]
async fn claimed_dispatch_reaches_actual_host_after_durable_claim() {
    let f = Fixture::new(false);
    let (_agent, _) = f.dispatch().await;
    assert_eq!(f.host.legacy.load(Ordering::SeqCst), 0);
    assert_eq!(f.host.claimed.load(Ordering::SeqCst), 1);
    assert_eq!(
        format!("{:?}", f.host.retained.lock().unwrap().as_ref().unwrap()),
        "ClaimedDispatch([REDACTED])"
    );
}
#[tokio::test]
async fn claimed_dispatch_rejects_another_actual_host_instance() {
    let f = Fixture::new(true);
    let (_agent, r) = f.dispatch().await;
    let other = Fixture::new(true);
    let held = f.host.retained.lock().unwrap();
    let claim = held.as_ref().unwrap();
    assert!(claim.verify_for(&*f.host, &r, now().unwrap()).is_ok());
    assert!(claim.verify_for(&*other.host, &r, now().unwrap()).is_err());
}
#[tokio::test]
async fn claimed_dispatch_rejects_binding_peer_and_argument_mutations() {
    let f = Fixture::new(true);
    let (_agent, r) = f.dispatch().await;
    let held = f.host.retained.lock().unwrap();
    let claim = held.as_ref().unwrap();
    let mut changes = Vec::new();
    let mut v = r.clone();
    v.binding.request_id = Uuid::new_v4();
    changes.push(v);
    let mut v = r.clone();
    v.binding.peer.channel_session = Uuid::new_v4();
    changes.push(v);
    let mut v = r.clone();
    v.binding.conversation = URL_SAFE_NO_PAD.encode([9; 32]);
    changes.push(v);
    let mut v = r.clone();
    v.binding.deadline += 1;
    changes.push(v);
    let mut v = r.clone();
    v.arguments = json!({"path":"other.txt"});
    changes.push(v);
    let mut v = r.clone();
    v.arguments = json!({"path":"other.txt"});
    v.binding.arguments_hash = digest_json(&v.arguments, 4096).unwrap();
    changes.push(v);
    for v in changes {
        assert!(claim.verify_for(&*f.host, &v, now().unwrap()).is_err());
    }
}
#[tokio::test]
async fn claimed_dispatch_rejects_deadline_and_completed_claim() {
    let f = Fixture::new(true);
    let (agent, r) = f.dispatch().await;
    let held = f.host.retained.lock().unwrap();
    let claim = held.as_ref().unwrap();
    assert!(claim.verify_for(&*f.host, &r, r.binding.deadline).is_err());
    agent
        .worker
        .journal
        .lock()
        .unwrap()
        .complete(&agent.worker.signer, &r)
        .unwrap();
    assert!(claim.verify_for(&*f.host, &r, now().unwrap()).is_err());
}
#[tokio::test]
async fn claimed_dispatch_retains_actual_exclusive_journal_after_agent_drop() {
    let f = Fixture::new(true);
    let (agent, r) = f.dispatch().await;
    drop(agent);
    assert!(f.open(false).is_err());
    assert!(f
        .host
        .retained
        .lock()
        .unwrap()
        .as_ref()
        .unwrap()
        .verify_for(&*f.host, &r, now().unwrap())
        .is_ok());
    f.host.retained.lock().unwrap().take();
    assert!(f.open(false).is_ok());
}
#[tokio::test]
async fn claimed_dispatch_durable_unknown_cannot_issue_a_second_call() {
    let f = Fixture::new(true);
    let (agent, r) = f.dispatch().await;
    let p = ProjectedHost {
        snapshot: f.host.state.clone(),
        revision: r.binding.grant_revision,
        until: r.binding.deadline,
    };
    assert_eq!(
        agent.worker.execute_inner(&r, &f.peer, &p).await,
        Err(AgentError::Duplicate)
    );
    assert_eq!(f.host.claimed.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn claimed_dispatch_rejects_poisoned_actual_journal_lock() {
    let f = Fixture::new(true);
    let (agent, r) = f.dispatch().await;
    let actual = agent.worker.journal.clone();
    assert!(std::thread::spawn(move || {
        let _held = actual.lock().unwrap();
        panic!("controlled temporary journal lock poison");
    })
    .join()
    .is_err());
    let held = f.host.retained.lock().unwrap();
    assert_eq!(
        held.as_ref()
            .unwrap()
            .verify_for(&*f.host, &r, now().unwrap()),
        Err(AgentError::Journal)
    );
}

#[tokio::test]
async fn claimed_dispatch_rejects_missing_actual_pending_claim() {
    let f = Fixture::new(true);
    let agent = f.open(true).unwrap();
    let (r, _) = f.request(&agent);
    // Trusted-module controlled negative fixture. External code has no mint.
    let unclaimed = ClaimedDispatch::new(f.host.clone(), agent.worker.journal.clone(), r.clone());
    assert_eq!(
        unclaimed.verify_for(&*f.host, &r, now().unwrap()),
        Err(AgentError::Duplicate)
    );
    assert_eq!(f.host.claimed.load(Ordering::SeqCst), 0);
}

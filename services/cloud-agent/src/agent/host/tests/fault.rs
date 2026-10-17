//! S1 fault injection: the real `HostAgent::run` over real loopback TLS/WSS
//! against a minimal in-process gateway that can cut, black-hole, stall, reject
//! and restart. Real sockets need real time (tokio's paused clock auto-advances
//! past in-flight I/O), so protocol timeouts and backoff are compressed by
//! `DIV` (8s/10s/12s become 0.4s/0.5s/0.6s); measured times are reported both
//! as real and as "virtual" (real x DIV). The exact 3599/3600/3601s boundary is
//! proven separately with the paused clock in `reconnect::tests`.
//!
//! Scope limits (stated, not hidden): this gateway follows the real wire shape
//! but does NOT verify signatures, generation fencing or the admission ledger;
//! those are covered by the real PostgreSQL gateway tests. These tests prove
//! the AGENT side of A1-A4: detection, reconnect, no exhaustion, no replay.
use super::*;
use crate::channel::{ConnectChallenge, SUBPROTOCOL};
use crate::identity::PublicIdentity;
use futures_util::{SinkExt, StreamExt};
use std::{collections::VecDeque, process::Command, sync::atomic::AtomicU64};
use tokio::{
    net::{TcpListener, TcpStream},
    sync::mpsc,
    task::{JoinHandle, JoinSet},
    time::Instant,
};
use tokio_rustls::TlsAcceptor;
use tokio_tungstenite::tungstenite::{
    handshake::server::{ErrorResponse, Request, Response},
    Message,
};

#[derive(Clone, Copy, Debug)]
enum Plan {
    Healthy,
    /// Complete the handshake, then drop the TCP connection without a close frame.
    CutAfterOnline,
    /// Complete the handshake, then go silent but keep the socket open (half-open).
    Blackhole,
    /// Serve everything except heartbeat acks once online.
    IgnoreHeartbeats,
    /// Upgrade to WebSocket and never send the challenge.
    StallHandshake,
    /// Refuse the WebSocket upgrade with this HTTP status.
    Http(u16),
    /// Upgrade, challenge, read the signed proof, then close without `connected`
    /// (what the real gateway does when the device is revoked: it only learns that
    /// after the upgrade, so there is no HTTP status the Agent could classify).
    RejectAfterProof,
}
#[derive(Clone, Debug, PartialEq)]
enum Ev {
    Accepted,
    Online,
    Heartbeat,
    Reply { request_id: Uuid, code: String },
}
#[derive(Clone, Debug)]
struct At {
    at: Instant,
    conn: usize,
    ev: Ev,
}
struct Live {
    push: mpsc::UnboundedSender<String>,
    peer: PeerBinding,
}
struct Shared {
    plans: Mutex<VecDeque<Plan>>,
    accepted: AtomicUsize,
    generation: AtomicU64,
    revision: AtomicU64,
    boot: Mutex<Uuid>,
    events: Mutex<Vec<At>>,
    live: Mutex<Option<Live>>,
    connector: Uuid,
    device: Uuid,
    identity: Mutex<(String, String)>,
}
struct Gate {
    port: u16,
    tls: TlsAcceptor,
    shared: Arc<Shared>,
    listener: Option<JoinHandle<()>>,
}
fn openssl(args: &[&str], dir: &Path) {
    let out = Command::new("openssl")
        .args(args)
        .current_dir(dir)
        .output()
        .expect("openssl is required by the existing TLS fixtures too");
    assert!(out.status.success(), "test certificate generation failed");
}
/// Fresh CA + localhost leaf in `dir` (EC P-256). Returns (leaf DER, key PKCS8 DER, CA DER path).
fn certificates(dir: &Path, name: &str) -> (Vec<u8>, Vec<u8>, PathBuf) {
    let (ca, cak, leaf, key, csr, ext) = (
        format!("{name}-ca.pem"),
        format!("{name}-ca.key"),
        format!("{name}-leaf.pem"),
        format!("{name}-leaf.key"),
        format!("{name}-leaf.csr"),
        format!("{name}-leaf.ext"),
    );
    let ec = [
        "-newkey",
        "ec",
        "-pkeyopt",
        "ec_paramgen_curve:prime256v1",
        "-nodes",
    ];
    let mut ca_args = vec!["req", "-x509", "-days", "1", "-subj", "/CN=FaultCA"];
    ca_args.extend(["-addext", "basicConstraints=critical,CA:TRUE"]);
    ca_args.extend(ec);
    ca_args.extend(["-keyout", &cak, "-out", &ca]);
    openssl(&ca_args, dir);
    let mut leaf_args = vec!["req", "-new", "-subj", "/CN=localhost"];
    leaf_args.extend(ec);
    leaf_args.extend(["-keyout", &key, "-out", &csr]);
    openssl(&leaf_args, dir);
    fs::write(
        dir.join(&ext),
        "subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n",
    )
    .unwrap();
    openssl(
        &[
            "x509",
            "-req",
            "-in",
            &csr,
            "-CA",
            &ca,
            "-CAkey",
            &cak,
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            &ext,
            "-out",
            &leaf,
        ],
        dir,
    );
    let leaf_der = format!("{name}-leaf.der");
    let key_der = format!("{name}-leaf.pk8");
    let ca_der = format!("{name}-ca.der");
    openssl(
        &["x509", "-in", &leaf, "-outform", "DER", "-out", &leaf_der],
        dir,
    );
    openssl(
        &[
            "pkcs8", "-topk8", "-nocrypt", "-in", &key, "-outform", "DER", "-out", &key_der,
        ],
        dir,
    );
    openssl(
        &["x509", "-in", &ca, "-outform", "DER", "-out", &ca_der],
        dir,
    );
    #[cfg(unix)]
    for entry in fs::read_dir(dir).unwrap() {
        use std::os::unix::fs::PermissionsExt;
        let p = entry.unwrap().path();
        if p.is_file() {
            fs::set_permissions(&p, fs::Permissions::from_mode(0o600)).unwrap();
        }
    }
    (
        fs::read(dir.join(&leaf_der)).unwrap(),
        fs::read(dir.join(&key_der)).unwrap(),
        dir.join(&ca_der),
    )
}
fn acceptor(leaf: Vec<u8>, key: Vec<u8>) -> TlsAcceptor {
    let config = rustls::ServerConfig::builder_with_provider(Arc::new(
        rustls::crypto::ring::default_provider(),
    ))
    .with_safe_default_protocol_versions()
    .unwrap()
    .with_no_client_auth()
    .with_single_cert(
        vec![rustls::pki_types::CertificateDer::from(leaf)],
        rustls::pki_types::PrivatePkcs8KeyDer::from(key).into(),
    )
    .unwrap();
    TlsAcceptor::from(Arc::new(config))
}
fn wall() -> i64 {
    now().unwrap()
}
impl Gate {
    async fn start(f: &Fixture, tls: TlsAcceptor, plans: Vec<Plan>) -> Self {
        let cfg: Value = serde_json::from_slice(&f.config).unwrap();
        let connector: Uuid = serde_json::from_value(cfg["connector"].clone()).unwrap();
        let shared = Arc::new(Shared {
            plans: Mutex::new(plans.into()),
            accepted: AtomicUsize::new(0),
            generation: AtomicU64::new(0),
            revision: AtomicU64::new(0),
            boot: Mutex::new(Uuid::new_v4()),
            events: Mutex::new(Vec::new()),
            live: Mutex::new(None),
            connector,
            device: f.peer.device,
            identity: Mutex::new((String::new(), String::new())),
        });
        let mut gate = Self {
            port: 0,
            tls,
            shared,
            listener: None,
        };
        gate.listen(0).await;
        gate
    }
    async fn listen(&mut self, port: u16) {
        let listener = TcpListener::bind(("127.0.0.1", port)).await.unwrap();
        self.port = listener.local_addr().unwrap().port();
        let identity = PublicIdentity::new(
            &format!("https://localhost:{}", self.port),
            "/coding-tools",
            self.shared.connector,
        )
        .unwrap();
        *self.shared.identity.lock().unwrap() = (identity.issuer(), identity.resource());
        *self.shared.boot.lock().unwrap() = Uuid::new_v4();
        let (shared, tls) = (self.shared.clone(), self.tls.clone());
        self.listener = Some(tokio::spawn(async move {
            // Dropping the JoinSet (on abort) aborts every connection task: a
            // gateway process dying takes all its sockets with it.
            let mut conns = JoinSet::new();
            loop {
                let Ok((tcp, _)) = listener.accept().await else {
                    return;
                };
                let n = shared.accepted.fetch_add(1, Ordering::SeqCst) + 1;
                let plan = shared
                    .plans
                    .lock()
                    .unwrap()
                    .pop_front()
                    .unwrap_or(Plan::Healthy);
                conns.spawn(serve(shared.clone(), tls.clone(), tcp, n, plan));
            }
        }));
    }
    /// Gateway process death: listener and every connection vanish, port goes dark.
    async fn kill(&mut self) {
        if let Some(l) = self.listener.take() {
            l.abort();
            let _ = l.await;
        }
        *self.shared.live.lock().unwrap() = None;
    }
    fn events(&self) -> Vec<At> {
        self.shared.events.lock().unwrap().clone()
    }
    fn count(&self, ev: &Ev) -> usize {
        self.events().iter().filter(|e| &e.ev == ev).count()
    }
    fn first(&self, conn: usize, ev: &Ev) -> Option<Instant> {
        self.events()
            .iter()
            .find(|e| e.conn == conn && &e.ev == ev)
            .map(|e| e.at)
    }
    fn accepted(&self) -> usize {
        self.shared.accepted.load(Ordering::SeqCst)
    }
    fn push(&self, frame: Value) {
        let live = self.shared.live.lock().unwrap();
        live.as_ref().unwrap().push.send(frame.to_string()).unwrap();
    }
    fn revision(&self) -> i64 {
        self.shared.revision.load(Ordering::SeqCst) as i64
    }
    fn peer(&self) -> PeerBinding {
        self.shared
            .live
            .lock()
            .unwrap()
            .as_ref()
            .unwrap()
            .peer
            .clone()
    }
}
fn record(shared: &Shared, conn: usize, ev: Ev) {
    shared.events.lock().unwrap().push(At {
        at: Instant::now(),
        conn,
        ev,
    });
}
async fn serve(shared: Arc<Shared>, tls: TlsAcceptor, tcp: TcpStream, n: usize, plan: Plan) {
    record(&shared, n, Ev::Accepted);
    let Ok(tls) = tls.accept(tcp).await else {
        return;
    };
    #[allow(clippy::result_large_err)] // the callback signature is fixed by tungstenite
    let callback = move |_: &Request, mut response: Response| -> Result<Response, ErrorResponse> {
        if let Plan::Http(code) = plan {
            return Err(tokio_tungstenite::tungstenite::http::Response::builder()
                .status(code)
                .body(None)
                .unwrap());
        }
        response
            .headers_mut()
            .insert("sec-websocket-protocol", SUBPROTOCOL.parse().unwrap());
        Ok(response)
    };
    let Ok(mut ws) = tokio_tungstenite::accept_hdr_async(tls, callback).await else {
        return;
    };
    if matches!(plan, Plan::StallHandshake) {
        return std::future::pending().await;
    }
    let boot = *shared.boot.lock().unwrap();
    let (issuer, resource) = shared.identity.lock().unwrap().clone();
    let at = wall();
    let challenge = ConnectChallenge {
        version: 1,
        issuer,
        resource,
        connector: shared.connector,
        gateway_boot: boot,
        attempt: Uuid::new_v4(),
        nonce: URL_SAFE_NO_PAD.encode([9; 32]),
        issued_at: at - 1,
        expires_at: at - 1 + crate::channel::AUTH_SECONDS,
    };
    let send = |v: Value| Message::Text(v.to_string().into());
    if ws
        .send(send(
            json!({"type":"connect_challenge","challenge":challenge}),
        ))
        .await
        .is_err()
    {
        return;
    }
    let Some(Ok(Message::Text(_proof))) = ws.next().await else {
        return;
    };
    if matches!(plan, Plan::RejectAfterProof) {
        let _ = ws.send(Message::Close(None)).await;
        return;
    }
    if ws
        .send(send(
            json!({"type":"connected","heartbeat_seconds":10,"lease_seconds":30}),
        ))
        .await
        .is_err()
    {
        return;
    }
    let generation = shared.generation.fetch_add(1, Ordering::SeqCst) as i64 + 1;
    let peer = PeerBinding {
        connector: shared.connector,
        device: shared.device,
        device_epoch: 1,
        gateway_boot: boot,
        channel_session: Uuid::new_v4(),
        channel_generation: generation,
    };
    let (push, mut pushed) = mpsc::unbounded_channel::<String>();
    // A newer connection fences the older one (it simply stops being the live route).
    *shared.live.lock().unwrap() = Some(Live {
        push,
        peer: peer.clone(),
    });
    let mut online = false;
    loop {
        let message = tokio::select! {
            m = ws.next() => m,
            Some(frame) = pushed.recv() => {
                if ws.send(Message::Text(frame.into())).await.is_err() { return; }
                continue;
            }
        };
        let Some(Ok(Message::Text(text))) = message else {
            return;
        };
        let v: Value = serde_json::from_str(&text).unwrap();
        let seq = v["seq"].clone();
        let reply = match v["type"].as_str().unwrap() {
            "heartbeat" => {
                record(&shared, n, Ev::Heartbeat);
                if matches!(plan, Plan::IgnoreHeartbeats) && online {
                    continue;
                }
                json!({"type":"heartbeat_ack","seq":seq})
            }
            "execution_ready" => json!({"type":"execution_ready_ack","seq":seq,"peer":peer}),
            "approval_ready" => json!({"type":"approval_ready_ack","seq":seq,"version":1}),
            "projection_challenge" => {
                let at = wall();
                json!({"type":"projection_challenge","seq":seq,"gateway_boot":boot,
                    "nonce":URL_SAFE_NO_PAD.encode([7; 32]),"expires_at":at+30,"snapshot_valid_until":at+25})
            }
            "projection" => {
                // The signed claims carry the revision the Agent will accept requests for.
                let payload = URL_SAFE_NO_PAD
                    .decode(v["proof"]["payload"].as_str().unwrap())
                    .unwrap();
                let claims: Value = serde_json::from_slice(&payload).unwrap();
                shared
                    .revision
                    .store(claims["revision"].as_u64().unwrap(), Ordering::SeqCst);
                json!({"type":"projection_ack","seq":seq})
            }
            "execution_reply" => {
                let request_id: Uuid =
                    serde_json::from_value(v["reply"]["binding"]["request_id"].clone()).unwrap();
                let code = v["reply"]["result"]["error"]["code"]
                    .as_str()
                    .unwrap_or("OK")
                    .to_owned();
                record(&shared, n, Ev::Reply { request_id, code });
                json!({"type":"execution_reply_ack","seq":seq})
            }
            other => panic!("unexpected agent frame {other}"),
        };
        if matches!(plan, Plan::Blackhole) && online {
            continue; // never answer again, never close
        }
        let ack_is_projection = reply["type"] == "projection_ack";
        if ws.send(send(reply)).await.is_err() {
            return;
        }
        if ack_is_projection && !online {
            online = true;
            record(&shared, n, Ev::Online);
            match plan {
                Plan::CutAfterOnline => return, // dropped: TCP closed, no WS close frame
                Plan::Blackhole => {}
                _ => {}
            }
        }
    }
}

const DIV: u32 = 20;
struct Rig {
    f: Fixture,
    gate: Gate,
    stop: watch::Sender<bool>,
    state: watch::Receiver<LinkState>,
    task: Option<JoinHandle<Result<(), AgentError>>>,
}
struct NoJitter;
impl Jitter for NoJitter {
    fn permille(&self) -> u64 {
        0
    }
}
/// Real seconds to protocol ("virtual") seconds.
fn virt(real: Duration) -> f64 {
    real.as_secs_f64() * f64::from(DIV)
}
impl Rig {
    async fn start(plans: Vec<Plan>) -> Self {
        Self::start_with(plans, Duration::from_secs(600), 3600, false).await
    }
    async fn start_with(
        plans: Vec<Plan>,
        exec: Duration,
        run_seconds: u64,
        wrong_ca: bool,
    ) -> Self {
        let mut f = Fixture::new(
            Duration::ZERO,
            exec,
            json!({"ok":true,"fixture":"read-canary"}),
        );
        let (leaf, key, ca) = certificates(&f.root, "gw");
        let ca = if wrong_ca {
            certificates(&f.root, "other").2
        } else {
            ca
        };
        let gate = Gate::start(&f, acceptor(leaf, key), plans).await;
        let mut cfg: Value = serde_json::from_slice(&f.config).unwrap();
        cfg["origin"] = json!(format!("https://localhost:{}", gate.port));
        cfg["ca_der_file"] = json!(ca);
        cfg["run_seconds"] = json!(run_seconds);
        f.config = serde_json::to_vec(&cfg).unwrap();
        let mut agent = f
            .agent(true)
            .unwrap()
            .with_jitter(Arc::new(NoJitter))
            .with_time_divisor(DIV);
        let (stop, rx) = watch::channel(false);
        let state = agent.link_state();
        let task = tokio::spawn(async move { agent.run(rx).await });
        Self {
            f,
            gate,
            stop,
            state,
            task: Some(task),
        }
    }
    async fn until(&self, what: &str, max_real_secs: u64, cond: impl Fn(&Gate) -> bool) {
        for _ in 0..(max_real_secs * 100) {
            if cond(&self.gate) {
                return;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        panic!(
            "timed out after {max_real_secs}s waiting for: {what}; state={:?} accepted={}",
            *self.state.borrow(),
            self.gate.accepted()
        );
    }
    async fn online(&self, nth: usize) {
        self.until("agent online", 30, |g| g.count(&Ev::Online) >= nth)
            .await;
    }
    fn alive(&self) -> bool {
        !self.task.as_ref().unwrap().is_finished()
    }
    async fn finish(mut self) {
        self.stop.send(true).unwrap();
        assert_eq!(self.task.take().unwrap().await.unwrap(), Ok(()));
        self.gate.kill().await;
    }
    fn request(&self, peer: PeerBinding) -> ExecutionRequest {
        let snapshot = self.f.host.state.lock().unwrap().clone();
        let revision = self.gate.revision();
        let arguments = json!({});
        ExecutionRequest {
            binding: crate::execution::ExecutionBinding {
                request_id: Uuid::new_v4(),
                peer,
                grant_id: snapshot.grant.as_ref().unwrap().id,
                grant_revision: revision,
                authority_epoch: snapshot.epoch,
                conversation: snapshot.grant.as_ref().unwrap().conversation.clone(),
                scope: "files.read".into(),
                tool: "workspace_probe".into(),
                arguments_hash: canonical_digest(&arguments, 4096).unwrap(),
                deadline: wall() + 30,
            },
            arguments,
        }
    }
}
fn gap(from: Instant, to: Instant) -> Duration {
    to.duration_since(from)
}
async fn pause(real: Duration) {
    tokio::time::sleep(real).await
}

#[tokio::test]
async fn wss_session_outlives_run_seconds_without_reconnecting() {
    // run_seconds = 1 (the minimum) used to end the Agent after one second.
    let rig = Rig::start_with(vec![], Duration::from_secs(600), 1, false).await;
    rig.online(1).await;
    pause(Duration::from_secs(3)).await;
    assert!(rig.alive(), "Agent exited at run_seconds");
    assert_eq!(rig.gate.accepted(), 1, "healthy link must not reconnect");
    assert_eq!(*rig.state.borrow(), LinkState::Online);
    assert!(
        rig.gate.count(&Ev::Heartbeat) >= 5,
        "heartbeats keep flowing"
    );
    rig.finish().await;
}
#[tokio::test]
async fn cut_connection_reconnects_automatically() {
    let rig = Rig::start(vec![Plan::CutAfterOnline]).await;
    rig.online(2).await;
    assert_eq!(rig.gate.accepted(), 2);
    assert_eq!(*rig.state.borrow(), LinkState::Online);
    assert_eq!(rig.gate.peer().channel_generation, 2);
    rig.finish().await;
}
#[tokio::test]
async fn network_flaps_back_off_then_recover_without_giving_up() {
    let rig = Rig::start(vec![Plan::CutAfterOnline; 4]).await;
    rig.online(5).await;
    let starts: Vec<Instant> = (1..=5)
        .map(|c| rig.gate.first(c, &Ev::Accepted).unwrap())
        .collect();
    let gaps: Vec<Duration> = starts.windows(2).map(|w| gap(w[0], w[1])).collect();
    eprintln!(
        "MEASURED flap gaps (virtual s): {:?}",
        gaps.iter().map(|g| virt(*g).round()).collect::<Vec<_>>()
    );
    // Unstable (<30s) links keep growing the backoff (1,2,4,8s virtual): no tight loop.
    assert!(gaps.windows(2).all(|w| w[1] > w[0]), "{gaps:?}");
    assert!(
        gaps[3] >= Duration::from_millis(7_000 / u64::from(DIV)),
        "{gaps:?}"
    );
    rig.finish().await;
}
#[tokio::test]
async fn black_holed_link_is_declared_dead_by_the_ack_timeout_inside_the_lease() {
    let rig = Rig::start(vec![Plan::Blackhole]).await;
    rig.online(2).await;
    let online1 = rig.gate.first(1, &Ev::Online).unwrap();
    let conn2 = rig.gate.first(2, &Ev::Accepted).unwrap();
    // First unanswered probe (projection challenge at ~4s) + 10s ack timeout,
    // then the 1s first backoff (all virtual). Must beat the 30s server lease.
    let detect = virt(gap(online1, conn2)) - 1.0;
    eprintln!("MEASURED black-hole detection: {detect:.1}s virtual (lease 30s)");
    assert!((9.0..20.0).contains(&detect), "{detect}");
    rig.finish().await;
}
#[tokio::test]
async fn missing_heartbeat_acks_alone_trigger_reconnect_at_eight_plus_ten_seconds() {
    // Everything else is answered, so only the 8s heartbeat + 10s ack path can notice.
    let rig = Rig::start(vec![Plan::IgnoreHeartbeats]).await;
    rig.online(1).await;
    rig.until("second connection", 30, |g| g.accepted() >= 2)
        .await;
    let online1 = rig.gate.first(1, &Ev::Online).unwrap();
    let conn2 = rig.gate.first(2, &Ev::Accepted).unwrap();
    let detect = virt(gap(online1, conn2)) - 1.0;
    eprintln!("MEASURED heartbeat-ack detection: {detect:.1}s virtual after online (8s + 10s)");
    assert!((16.0..30.0).contains(&detect), "{detect}");
    rig.finish().await;
}
#[tokio::test]
async fn stalled_handshake_times_out_at_twelve_seconds_and_retries() {
    let rig = Rig::start(vec![Plan::StallHandshake]).await;
    rig.online(1).await;
    let c1 = rig.gate.first(1, &Ev::Accepted).unwrap();
    let c2 = rig.gate.first(2, &Ev::Accepted).unwrap();
    let wait = virt(gap(c1, c2)) - 1.0;
    eprintln!("MEASURED stalled-handshake detection: {wait:.1}s virtual");
    assert!(
        (11.0..16.0).contains(&wait),
        "receive timeout is 12s: {wait}"
    );
    rig.finish().await;
}
#[tokio::test]
async fn gateway_restart_with_a_long_outage_reconnects_and_never_exhausts() {
    let mut rig = Rig::start(vec![]).await;
    rig.online(1).await;
    let port = rig.gate.port;
    rig.gate.kill().await;
    // ~4 virtual minutes dark (12s real x 20): beyond the old 8-failure budget.
    pause(Duration::from_secs(12)).await;
    assert!(rig.alive(), "Agent gave up during the outage");
    let state = *rig.state.borrow();
    assert!(
        matches!(state, LinkState::Reconnecting { attempt } if attempt > 8),
        "{state:?}"
    );
    let back = Instant::now();
    rig.gate.listen(port).await;
    rig.online(2).await;
    let waited = virt(gap(back, rig.gate.first(2, &Ev::Online).unwrap()));
    eprintln!("MEASURED reconnect after gateway came back: {waited:.1}s virtual (cap 30s)");
    assert!(waited <= 33.0, "{waited}");
    assert_eq!(rig.gate.peer().channel_generation, 2);
    rig.finish().await;
}
#[tokio::test]
async fn upgrade_5xx_is_retried_but_401_needs_an_operator_without_a_retry_storm() {
    let rig = Rig::start(vec![Plan::Http(503), Plan::Http(502), Plan::Http(520)]).await;
    rig.online(1).await;
    assert_eq!(rig.gate.accepted(), 4);
    rig.finish().await;

    let mut rig = Rig::start(vec![Plan::Http(401)]).await;
    let result = rig.task.take().unwrap().await.unwrap();
    assert_eq!(result, Err(AgentError::Authentication));
    assert_eq!(
        *rig.state.borrow(),
        LinkState::NeedsOperator(AgentError::Authentication)
    );
    pause(Duration::from_secs(2)).await; // 40 virtual seconds: many backoffs
    assert_eq!(rig.gate.accepted(), 1, "retry storm after a rejection");
}
#[tokio::test]
async fn device_rejected_after_the_proof_is_retried_at_capped_backoff_and_never_exits() {
    // The gateway closes the socket after the proof for a revoked device. That is
    // indistinguishable from a transient close, so the always-on Agent keeps trying
    // at the capped backoff: no Exhausted, no exit, no tight loop, never online.
    let rig = Rig::start(vec![Plan::RejectAfterProof; 64]).await;
    // 6 real seconds = 120 virtual seconds: attempts at ~0,1,3,7,15,31,61,91.
    pause(Duration::from_secs(6)).await;
    assert!(rig.alive(), "Agent exited for a revoked-style rejection");
    let state = *rig.state.borrow();
    assert!(
        matches!(state, LinkState::Reconnecting { attempt } if attempt >= 5),
        "{state:?}"
    );
    let accepted = rig.gate.accepted();
    assert!((6..=10).contains(&accepted), "attempts {accepted}");
    assert_eq!(rig.gate.count(&Ev::Online), 0);
    let starts: Vec<Instant> = (1..=accepted)
        .map(|c| rig.gate.first(c, &Ev::Accepted).unwrap())
        .collect();
    let gaps: Vec<Duration> = starts.windows(2).map(|w| gap(w[0], w[1])).collect();
    assert!(
        gaps.windows(2)
            .all(|w| w[1] + Duration::from_millis(20) >= w[0]),
        "backoff must not shrink: {gaps:?}"
    );
    rig.finish().await;
}
#[tokio::test]
async fn gateway_answering_403_while_restarting_recovers_by_itself() {
    // The real gateway answers 403 to upgrades while its stop flag is set; a proxy can
    // answer 404 mid-deploy. Neither may strand the Agent: it retries and reconnects.
    let rig = Rig::start(vec![
        Plan::Http(403),
        Plan::Http(404),
        Plan::Http(403),
        Plan::Http(403),
    ])
    .await;
    rig.online(1).await;
    assert_eq!(rig.gate.accepted(), 5);
    assert!(rig.alive());
    assert_eq!(*rig.state.borrow(), LinkState::Online);
    rig.finish().await;
}
#[tokio::test]
async fn permanent_403_needs_an_operator_after_the_limit_and_not_before() {
    let mut rig = Rig::start(vec![Plan::Http(403); 400]).await;
    // Limit is 600 virtual seconds = 30 real seconds at DIV 20. Half way: still trying.
    pause(Duration::from_secs(15)).await;
    assert!(rig.alive(), "gave up before the limit");
    assert!(matches!(
        *rig.state.borrow(),
        LinkState::Reconnecting { .. } | LinkState::Connecting
    ));
    let halfway = rig.gate.accepted();
    assert!((10..=22).contains(&halfway), "attempts {halfway}");
    let result = tokio::time::timeout(Duration::from_secs(30), rig.task.take().unwrap())
        .await
        .expect("never escalated")
        .unwrap();
    assert_eq!(result, Err(AgentError::Authentication));
    assert_eq!(
        *rig.state.borrow(),
        LinkState::NeedsOperator(AgentError::Authentication)
    );
    let total = rig.gate.accepted();
    assert!((20..=40).contains(&total), "attempts {total}");
    pause(Duration::from_secs(2)).await; // 40 virtual seconds more
    assert_eq!(rig.gate.accepted(), total, "retry storm after escalating");
}
#[tokio::test]
async fn untrusted_gateway_certificate_needs_an_operator_and_does_not_retry() {
    let mut rig = Rig::start_with(vec![], Duration::from_secs(600), 3600, true).await;
    let result = rig.task.take().unwrap().await.unwrap();
    assert_eq!(result, Err(AgentError::Tls));
    assert_eq!(
        *rig.state.borrow(),
        LinkState::NeedsOperator(AgentError::Tls)
    );
    pause(Duration::from_secs(2)).await;
    assert_eq!(rig.gate.count(&Ev::Online), 0);
}
#[tokio::test]
async fn request_in_flight_when_the_link_drops_is_never_replayed_by_the_agent() {
    // A4 window 1: dispatched, executing, link lost before the reply.
    let mut rig = Rig::start(vec![]).await;
    rig.online(1).await;
    let first = rig.request(rig.gate.peer());
    let id = first.binding.request_id;
    rig.gate
        .push(json!({"type":"execution_request","request":first}));
    rig.until("host executes once", 30, |_| {
        rig.f.host.calls.load(Ordering::SeqCst) == 1
    })
    .await;
    let port = rig.gate.port;
    rig.gate.kill().await; // gateway dies mid-execution
    pause(Duration::from_millis(300)).await;
    rig.gate.listen(port).await;
    rig.online(2).await;
    assert_eq!(rig.f.host.calls.load(Ordering::SeqCst), 1);
    let replied = |g: &Gate| {
        g.events()
            .iter()
            .any(|e| matches!(&e.ev, Ev::Reply { request_id, .. } if *request_id == id))
    };
    assert!(
        !replied(&rig.gate),
        "an aborted execution answered on the new link"
    );
    // A buggy or hostile cloud re-sends the same request_id on the new generation.
    let mut again = rig.request(rig.gate.peer());
    again.binding.request_id = id;
    rig.gate
        .push(json!({"type":"execution_request","request":again}));
    rig.until("duplicate answered", 30, replied).await;
    let code = rig.gate.events().into_iter().find_map(|e| match e.ev {
        Ev::Reply { request_id, code } if request_id == id => Some(code),
        _ => None,
    });
    assert_eq!(code.as_deref(), Some("LOCAL_REQUEST_ALREADY_CLAIMED"));
    assert_eq!(
        rig.f.host.calls.load(Ordering::SeqCst),
        1,
        "replay reached the native host"
    );
    rig.finish().await;
}
#[tokio::test]
async fn request_bound_to_the_previous_generation_is_refused_after_reconnect() {
    // Agent-side fence: a frame carrying the OLD peer binding never reaches the host.
    let rig = Rig::start(vec![Plan::CutAfterOnline]).await;
    rig.online(1).await;
    let old_peer = rig.gate.peer();
    rig.online(2).await;
    assert_ne!(
        old_peer.channel_generation,
        rig.gate.peer().channel_generation
    );
    let stale = rig.request(old_peer);
    rig.gate
        .push(json!({"type":"execution_request","request":stale}));
    // A mismatched binding is a protocol violation: the session is torn down and
    // re-established (retryable) and the native host is never invoked.
    rig.online(3).await;
    assert_eq!(rig.f.host.calls.load(Ordering::SeqCst), 0);
    assert!(rig.alive());
    rig.finish().await;
}

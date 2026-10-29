//! Real WSS/PG fixture with an explicit file-reading test host, not native desktop approval.
use axum::{
    body::Body,
    http::{header, Request},
    Router,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_agent::{
    execution::ExecutionRequest,
    projection::{ExecutionState, LocalLease, ProjectionPhase},
    AgentError,
};
use coding_tools_cloud_gateway::{
    agent::host::{HostAgent, HostAuthoritySnapshot, HostFuture, LocalHost},
    channel::{agent_channel_routes, ChannelController},
    device::enrollment_message,
    mcp::{self, MODERN},
    projection::ProjectionStore,
    AuthorizationRequest, ClientCredential, IdentityStore, Lifetimes, OAuthPrincipal,
    PublicIdentity, SecretKey,
};
use http_body_util::BodyExt;
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde_json::{json, Value};
use sqlx::{postgres::PgPoolOptions, PgPool};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{net::TcpListener, sync::watch, task::JoinHandle};
use tower::ServiceExt;
use uuid::Uuid;

pub fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}
#[derive(Clone)]
pub struct FileHost {
    pub inner: Arc<FileState>,
}
pub struct FileState {
    pub root: PathBuf,
    pub grant: LocalLease,
    pub generation: AtomicU64,
    pub online: AtomicBool,
    pub calls: AtomicUsize,
    pub delay: AtomicU64,
}
pub struct Permit {
    id: Uuid,
}
impl FileHost {
    pub fn view(&self) -> HostAuthoritySnapshot {
        HostAuthoritySnapshot::new(
            1,
            1,
            self.inner.generation.load(Ordering::SeqCst),
            ProjectionPhase::Active,
            if self.inner.online.load(Ordering::SeqCst) {
                ExecutionState::Online
            } else {
                ExecutionState::Offline
            },
            Some(self.inner.grant.clone()),
            None,
        )
        .unwrap()
    }
}
impl LocalHost for FileHost {
    type Permit = Permit;
    fn required_scope(&self, name: &str, _arguments: &Value) -> Option<&'static str> {
        if name == "workspace_probe" {
            Some("files.read")
        } else {
            None
        }
    }
    fn snapshot(&self) -> HostFuture<HostAuthoritySnapshot> {
        let value = self.view();
        Box::pin(async move { Ok(value) })
    }
    fn admit(
        &self,
        expected: HostAuthoritySnapshot,
        request: ExecutionRequest,
    ) -> HostFuture<Permit> {
        let host = self.clone();
        Box::pin(async move {
            if expected != host.view() || !host.inner.online.load(Ordering::SeqCst) {
                return Err(AgentError::LocalAuthority);
            }
            Ok(Permit {
                id: request.binding.request_id,
            })
        })
    }
    fn execute(
        &self,
        permit: Permit,
        request: ExecutionRequest,
        mut cancel: watch::Receiver<bool>,
    ) -> HostFuture<Value> {
        let host = self.clone();
        Box::pin(async move {
            if permit.id != request.binding.request_id {
                return Err(AgentError::LocalAuthority);
            }
            host.inner.calls.fetch_add(1, Ordering::SeqCst);
            tokio::select! {
                _=cancel.changed()=>return Err(AgentError::ExecutionUnknown),
                _=tokio::time::sleep(Duration::from_millis(host.inner.delay.load(Ordering::SeqCst)))=>{},
            }
            let content = tokio::fs::read_to_string(host.inner.root.join("canary.txt"))
                .await
                .map_err(|_| AgentError::ExecutionUnknown)?;
            Ok(json!({"ok":true,"content":content}))
        })
    }
}
pub struct Harness {
    pub pool: PgPool,
    pub app: Router,
    pub identity: PublicIdentity,
    pub token: String,
    pub host: Arc<FileHost>,
    pub config: Vec<u8>,
    pub key: Vec<u8>,
    pub root: PathBuf,
    relay: Child,
    server: JoinHandle<()>,
    pub agent: Option<JoinHandle<Result<(), AgentError>>>,
    stop: watch::Sender<bool>,
}
impl Drop for Harness {
    fn drop(&mut self) {
        let _ = self.stop.send(true);
        if let Some(a) = &self.agent {
            a.abort();
        }
        self.server.abort();
        let _ = self.relay.kill();
        let _ = self.relay.wait();
        let _ = fs::remove_dir_all(&self.root);
    }
}
impl Harness {
    pub async fn start() -> Self {
        let root = std::env::temp_dir().join(format!("host-agent-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        fs::write(root.join("canary.txt"), "actual-local-file-canary").unwrap();
        let mut relay = Command::new("python3")
            .arg("-S")
            .arg(format!(
                "{}/tests/host_agent_support/relay.py",
                env!("CARGO_MANIFEST_DIR")
            ))
            .arg(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let mut line = String::new();
        BufReader::new(relay.stdout.take().unwrap())
            .read_line(&mut line)
            .unwrap();
        let port = serde_json::from_str::<Value>(&line).unwrap()["port"]
            .as_u64()
            .unwrap();
        let identity = PublicIdentity::new(
            &format!("https://localhost:{port}"),
            "/coding-tools",
            Uuid::new_v4(),
        )
        .unwrap();
        let dsn = std::env::var("TEST_DATABASE_URL").expect("real dedicated database required");
        let parsed = url::Url::parse(&dsn).unwrap();
        assert_eq!(parsed.path(), "/coding_tools_identity_test");
        assert!(matches!(parsed.host_str(), Some("127.0.0.1" | "localhost")));
        let admin = PgPoolOptions::new()
            .max_connections(1)
            .connect(&dsn)
            .await
            .unwrap();
        let schema = format!("ctm_host_{}", Uuid::new_v4().simple());
        sqlx::query(&format!("CREATE SCHEMA {schema}"))
            .execute(&admin)
            .await
            .unwrap();
        let pool = PgPoolOptions::new()
            .max_connections(8)
            .after_connect(move |conn, _| {
                let q = format!("SET search_path TO {schema}");
                Box::pin(async move {
                    sqlx::query(&q).execute(conn).await?;
                    Ok(())
                })
            })
            .connect(&dsn)
            .await
            .unwrap();
        admin.close().await;
        IdentityStore::migrate(&pool).await.unwrap();
        let store = IdentityStore::open(
            pool.clone(),
            identity.clone(),
            SecretKey::new([7; 32]).unwrap(),
            Lifetimes::default(),
        )
        .await
        .unwrap();
        store
            .register_client(
                "public-client",
                "https://client.example.invalid/callback",
                None,
            )
            .await
            .unwrap();
        let verifier = "a".repeat(43);
        let code = store
            .issue_after_owner_consent(
                Uuid::from_u128(8),
                AuthorizationRequest {
                    client_id: "public-client",
                    redirect_uri: "https://client.example.invalid/callback",
                    resource: &identity.resource(),
                    code_challenge: &coding_tools_cloud_gateway::crypto::pkce_challenge(&verifier)
                        .unwrap(),
                    code_challenge_method: "S256",
                },
            )
            .await
            .unwrap();
        let token = store
            .exchange_code(
                ClientCredential {
                    client_id: "public-client",
                    secret: None,
                },
                code.expose(),
                &verifier,
                "https://client.example.invalid/callback",
                &identity.resource(),
            )
            .await
            .unwrap()
            .access_token
            .expose()
            .to_owned();
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&ring::rand::SystemRandom::new()).unwrap();
        let kp = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
        let invite = store.create_device_invitation().await.unwrap();
        let msg =
            enrollment_message(&identity, invite.token.expose(), kp.public_key().as_ref()).unwrap();
        let device = store
            .redeem_device_invitation(
                invite.token.expose(),
                kp.public_key().as_ref(),
                kp.sign(&msg).as_ref(),
            )
            .await
            .unwrap();
        let projection = ProjectionStore::activate(store.clone()).await.unwrap();
        projection.bind_device(device.id).await.unwrap();
        let controller = ChannelController::activate(store.clone()).await.unwrap();
        let conv = controller
            .conversation_binding(
                &OAuthPrincipal {
                    subject: Uuid::from_u128(8),
                    client_id: "public-client".into(),
                    resource: identity.resource(),
                },
                "host-session-A",
            )
            .unwrap();
        let host = Arc::new(FileHost {
            inner: Arc::new(FileState {
                root: root.clone(),
                grant: LocalLease {
                    id: Uuid::new_v4(),
                    conversation: conv.as_str().into(),
                    issued_at: now(),
                    expires_at: now() + 600,
                    scopes: vec!["files.read".into()],
                },
                generation: AtomicU64::new(1),
                online: AtomicBool::new(true),
                calls: AtomicUsize::new(0),
                delay: AtomicU64::new(0),
            }),
        });
        let config=serde_json::to_vec(&json!({"origin":format!("https://localhost:{port}"),"prefix":"/coding-tools",
            "connector":identity.connector(),"device":device.id,"device_epoch":device.epoch,"authority_epoch":1,
            "public_key":URL_SAFE_NO_PAD.encode(kp.public_key().as_ref()),
            "revision_file":root.join("unused-recovery-journal"),"ca_der_file":root.join("ca.der"),"run_seconds":120})).unwrap();
        let key =
            serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs8.as_ref())})).unwrap();
        let app = mcp::routes(store, controller.clone());
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        writeln!(
            relay.stdin.as_mut().unwrap(),
            "{}",
            listener.local_addr().unwrap().port()
        )
        .unwrap();
        relay.stdin.take();
        let router = agent_channel_routes(controller).merge(app.clone());
        let server = tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
        let (stop, rx) = watch::channel(false);
        let mut agent = HostAgent::open(
            &config,
            &key,
            &root.join("host-state.bin"),
            true,
            host.clone(),
        )
        .unwrap();
        let agent = Some(tokio::spawn(async move {
            let result = agent.run(rx).await;
            if let Err(error) = result {
                eprintln!("HOST_FIXTURE_AGENT_EXIT={error:?}");
            }
            result
        }));
        let h = Self {
            pool,
            app,
            identity,
            token,
            host,
            config,
            key,
            root,
            relay,
            server,
            agent,
            stop,
        };
        h.wait_ready(0).await;
        h
    }
    pub async fn wait_ready(&self, prior_generation: i64) {
        let end = tokio::time::Instant::now() + Duration::from_secs(8);
        loop {
            let ready:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM ctm_agent_channel a JOIN ctm_grant_projection p USING(connector) WHERE a.connected=true AND a.last_seq>=5 AND a.generation>$1 AND p.reconciled=true AND p.gateway_boot=a.gateway_boot)").bind(prior_generation).fetch_one(&self.pool).await.unwrap();
            if ready {
                break;
            }
            if self.agent.as_ref().unwrap().is_finished() {
                let row: Option<i64> = sqlx::query_scalar("SELECT last_seq FROM ctm_agent_channel")
                    .fetch_optional(&self.pool)
                    .await
                    .unwrap();
                let revisions: Vec<i64> =
                    sqlx::query_scalar("SELECT revision FROM ctm_grant_projection")
                        .fetch_all(&self.pool)
                        .await
                        .unwrap();
                panic!("HOST_AGENT_DISCONNECTED_BEFORE_READY seq={row:?} projection_revisions={revisions:?}");
            }
            assert!(tokio::time::Instant::now() < end, "HOST_AGENT_NOT_READY");
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }
    pub async fn stop_agent(&mut self) {
        self.stop.send(true).unwrap();
        let result = tokio::time::timeout(Duration::from_secs(3), self.agent.take().unwrap())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(result, Ok(()));
    }
    pub async fn restart(&mut self) {
        let prior_generation: i64 = sqlx::query_scalar("SELECT generation FROM ctm_agent_channel")
            .fetch_one(&self.pool)
            .await
            .unwrap();
        let (stop, rx) = watch::channel(false);
        self.stop = stop;
        let mut agent = HostAgent::open(
            &self.config,
            &self.key,
            &self.root.join("host-state.bin"),
            false,
            self.host.clone(),
        )
        .unwrap();
        self.agent = Some(tokio::spawn(async move { agent.run(rx).await }));
        self.wait_ready(prior_generation).await;
    }
    pub async fn call(&self, id: i64, chat: &str) -> Value {
        let body = json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":"workspace_probe","arguments":{},
            "_meta":{"openai/session":chat,"io.modelcontextprotocol/protocolVersion":MODERN,
            "io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"host-fixture","version":"1"}}}});
        let r = Request::builder()
            .method("POST")
            .uri(self.identity.resource_path())
            .header("host", self.identity.authority())
            .header(header::AUTHORIZATION, format!("Bearer {}", self.token))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "application/json, text/event-stream")
            .header("mcp-protocol-version", MODERN)
            .header("mcp-method", "tools/call")
            .header("mcp-name", "workspace_probe")
            .body(Body::from(body.to_string()))
            .unwrap();
        let response = self.app.clone().oneshot(r).await.unwrap();
        assert_eq!(response.status(), 200);
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        serde_json::from_slice::<Value>(&bytes).unwrap()["result"]["structuredContent"].clone()
    }
}

//! Actual application manager + locally imported config + real native listener + WSS/PG.
//! Local approval invokes the same native service as IPC, never a cloud approval.
use super::*;
use crate::{
    auth::PublicOrigin,
    cloud_connection::{CheckedImport, ConnectionStore},
    workspace::{AuthConfig, RuntimeConfig},
};
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, Command, Stdio},
    time::Instant,
};

struct Server(Child);
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
struct Fixture {
    root: tempfile::TempDir,
    _server: Server,
    id: String,
    store: ConnectionStore,
    app: ApplicationAgents,
    lease: ListenerContextLease,
    listener: Option<(
        crate::mcp::ShutdownSender,
        tauri::async_runtime::JoinHandle<()>,
    )>,
    http: reqwest::Client,
    origin: String,
    resource: String,
    token: String,
    inspect_token: String,
    protocol: String,
}
impl Fixture {
    async fn new() -> Self {
        let binary = std::env::var("CTM_NATIVE_GATEWAY_FIXTURE_BIN")
            .expect("native fixture binary is required");
        let dsn = std::env::var("TEST_DATABASE_URL").expect("dedicated PG required");
        let parsed = reqwest::Url::parse(&dsn).unwrap();
        assert_eq!(parsed.path(), "/coding_tools_identity_test");
        assert!(matches!(parsed.host_str(), Some("localhost" | "127.0.0.1")));
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join(".native-cloud-fixture"), "owned").unwrap();
        let mut server = Server(
            Command::new(binary)
                .env("CTM_NATIVE_E2E_FIXTURE", "1")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        writeln!(
            server.0.stdin.as_mut().unwrap(),
            "{}",
            json!({"root":root.path()})
        )
        .unwrap();
        server.0.stdin.take();
        let out = server.0.stdout.take().unwrap();
        let read = tokio::task::spawn_blocking(move || {
            let mut line = String::new();
            BufReader::new(out)
                .take(32769)
                .read_line(&mut line)
                .unwrap();
            line
        });
        let line = tokio::time::timeout(Duration::from_secs(25), read)
            .await
            .unwrap()
            .unwrap();
        assert!(line.len() <= 32768);
        let info: Value = serde_json::from_str(&line).unwrap();
        let origin = info["config"]["origin"].as_str().unwrap().to_owned();
        let id = Uuid::new_v4().to_string();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        std::fs::write(workspace.join("native-canary.txt"), "native-app-canary").unwrap();
        let store = ConnectionStore::application_test_store(
            root.path().join("connections/selected"),
            &id,
            &workspace,
        );
        let mut public = info["config"].clone();
        public.as_object_mut().unwrap().remove("revision_file");
        public.as_object_mut().unwrap().remove("ca_der_file");
        public["version"] = json!(1);
        let key = zeroize::Zeroizing::new(info["key"].to_string());
        store
            .initialize(CheckedImport::parse(&public.to_string(), &key).unwrap())
            .unwrap();
        let (shutdown, listener, _gate, lease) =
            crate::mcp::spawn_listener_with_origin_and_context_lease(
                0,
                workspace,
                id.clone(),
                AuthConfig {
                    auth_type: "oauth".into(),
                    ..Default::default()
                },
                PublicOrigin::managed("").unwrap(),
                Some("native-fixture-client".into()),
                Some("native-fixture-owner".into()),
                Some("native-fixture-token-secret-long-enough".into()),
                RuntimeConfig::default(),
            )
            .unwrap();
        let ca = std::fs::read(root.path().join("ca.der")).unwrap();
        let http = reqwest::Client::builder()
            .no_proxy()
            .add_root_certificate(reqwest::Certificate::from_der(&ca).unwrap())
            .timeout(Duration::from_secs(12))
            .build()
            .unwrap();
        let fixture = Self {
            root,
            _server: server,
            id,
            store,
            app: ApplicationAgents::default(),
            lease,
            listener: Some((shutdown, listener)),
            http,
            origin,
            resource: info["resource"].as_str().unwrap().into(),
            token: info["access_token"].as_str().unwrap().into(),
            inspect_token: info["inspection_token"].as_str().unwrap().into(),
            protocol: info["protocol"].as_str().unwrap().into(),
        };
        fixture.start(true);
        fixture.wait("ready", true).await;
        fixture
    }
    fn start(&self, initialize: bool) {
        let mut material = self.store.runtime_material().unwrap();
        // Private fixture CA is local test trust only; production import has no
        // CA/path override and always uses normal HTTPS certificate validation.
        let mut config: Value = serde_json::from_slice(&material.config).unwrap();
        config["ca_der_file"] = json!(self.root.path().join("ca.der"));
        material.config = serde_json::to_vec(&config).unwrap();
        self.app
            .start(&self.id, self.lease.clone(), material, initialize)
            .unwrap();
    }
    async fn inspect(&self) -> Value {
        self.http
            .get(format!("{}/__native_fixture", self.origin))
            .bearer_auth(&self.inspect_token)
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap()
    }
    async fn wait(&self, field: &str, expected: bool) {
        let end = Instant::now() + Duration::from_secs(20);
        loop {
            if self.inspect().await[field] == expected {
                return;
            }
            assert!(
                Instant::now() < end,
                "application WSS state timeout ({field})"
            );
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    }
    async fn rpc(&self, id: i64, chat: &str, name: &str, args: Value) -> Value {
        let result=self.http.post(&self.resource).bearer_auth(&self.token)
            .header("mcp-protocol-version",&self.protocol).header("mcp-method","tools/call").header("mcp-name",name)
            .header("accept","application/json, text/event-stream")
            .json(&json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":name,"arguments":args,
                "_meta":{"openai/session":chat,"io.modelcontextprotocol/protocolVersion":self.protocol,
                "io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"native-app-fixture","version":"1"}}}}))
            .send().await.unwrap();
        assert_eq!(result.status(), reqwest::StatusCode::OK);
        let value: Value = result.json().await.unwrap();
        value["result"]["structuredContent"].clone()
    }
    async fn close(mut self) {
        self.app.stop(&self.id).await.unwrap();
        let (shutdown, listener) = self.listener.take().unwrap();
        let _ = shutdown.send(());
        tokio::time::timeout(Duration::from_secs(5), listener)
            .await
            .unwrap()
            .unwrap();
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn application_import_listener_native_approval_pause_revoke_and_stop_are_end_to_end() {
    let fixture = Fixture::new().await;
    assert!(fixture.app.status(&fixture.id, true).unwrap().connected);
    let pending = fixture
        .rpc(
            8100,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":["files.read"]}),
        )
        .await;
    assert_eq!(pending["authorization"]["status"], "pending");
    assert_eq!(
        fixture.app.status(&fixture.id, true).unwrap().phase,
        "pending_approval"
    );
    assert_eq!(fixture.inspect().await["eligible_a"], false);
    let request = pending["authorization"]["id"].as_str().unwrap();
    crate::auth::chat::service()
        .decide(&fixture.id, request, true, &["files.read".into()])
        .unwrap();
    fixture.wait("eligible_a", true).await;
    assert_eq!(
        fixture.app.status(&fixture.id, true).unwrap().phase,
        "approved"
    );
    let result = fixture
        .rpc(8101, "native-A", "workspace_probe", json!({}))
        .await;
    assert_eq!(result["ok"], true);
    assert_eq!(result["execution"], "native_tool_dispatch");
    let gate = fixture
        .lease
        .with_live(|context| context.execution_gate())
        .unwrap();
    gate.pause().unwrap();
    assert_eq!(
        fixture.app.status(&fixture.id, true).unwrap().phase,
        "paused"
    );
    fixture.wait("eligible_a", false).await;
    gate.resume().unwrap();
    fixture.wait("eligible_a", true).await;
    crate::auth::chat::service().revoke(&fixture.id, Some(request));
    fixture.wait("eligible_a", false).await;
    fixture.app.stop(&fixture.id).await.unwrap();
    fixture.wait("ready", false).await;
    assert_eq!(
        fixture.app.status(&fixture.id, true).unwrap().phase,
        "configured"
    );
    fixture.start(false);
    fixture.wait("ready", true).await;
    // Reopening durable native journals never recreates the revoked grant.
    assert_eq!(fixture.inspect().await["eligible_a"], false);
    assert_ne!(
        fixture.app.status(&fixture.id, true).unwrap().phase,
        "approved"
    );
    fixture.close().await;
}

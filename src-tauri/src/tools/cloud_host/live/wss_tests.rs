//! Real native ChatAuthorizer + tool dispatcher + production Agent + WSS/HTTP/PG.
//! Native decide() is exercised directly; this is NOT a WebDriver/human approval claim.
use super::*;
use crate::{
    auth::{chat::ChatAuthorizer, cloud_context::CloudTransport},
    tools::ToolContext,
};
use coding_tools_cloud_agent::HostAgent;
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
struct Harness {
    _root: tempfile::TempDir,
    _server: Server,
    host: Arc<NativeLiveHost>,
    config: Vec<u8>,
    key: Vec<u8>,
    journal: std::path::PathBuf,
    stop: watch::Sender<bool>,
    agent: Option<tokio::task::JoinHandle<Result<(), AgentError>>>,
    http: reqwest::Client,
    origin: String,
    resource: String,
    token: String,
    inspect_token: String,
    protocol: String,
    token_endpoint: String,
    refresh: String,
}
impl Drop for Harness {
    fn drop(&mut self) {
        let _ = self.stop.send(true);
        if let Some(task) = self.agent.take() {
            task.abort();
        }
    }
}
impl Harness {
    async fn start() -> Self {
        let bin = std::env::var("CTM_NATIVE_GATEWAY_FIXTURE_BIN")
            .expect("CTM_NATIVE_GATEWAY_FIXTURE_BIN required; no fake fallback");
        let dsn = std::env::var("TEST_DATABASE_URL").expect("dedicated PostgreSQL required");
        let parsed = reqwest::Url::parse(&dsn).unwrap();
        assert_eq!(parsed.path(), "/coding_tools_identity_test");
        assert!(matches!(parsed.host_str(), Some("localhost" | "127.0.0.1")));
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join(".native-cloud-fixture"), "owned").unwrap();
        let mut server = Server(
            Command::new(bin)
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
        // Bootstrap read is bounded by an outer task timeout. Secret fixture
        // bytes never enter logs, assertions, test artifacts or source control.
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
        let info: Value = serde_json::from_str(&line).expect("bounded fixture bootstrap");
        let config = serde_json::to_vec(&info["config"]).unwrap();
        let key = serde_json::to_vec(&info["key"]).unwrap();
        let cfg = coding_tools_cloud_agent::AgentConfig::from_bytes(&config).unwrap();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        std::fs::write(
            workspace.join("native-canary.txt"),
            "native-cloud-real-file-canary",
        )
        .unwrap();
        let context = Arc::new(
            ToolContext::for_test(workspace.clone(), root.path().join("harness")).unwrap(),
        );
        let authorizer = Arc::new(ChatAuthorizer::default());
        authorizer
            .attach_storage(
                "native-wss",
                &root.path().join("auth"),
                &root.path().join("harness"),
            )
            .unwrap();
        let link = CloudTransport::new(
            "native-wss",
            &workspace,
            &cfg.origin,
            &cfg.prefix,
            cfg.connector,
            cfg.device,
            cfg.device_epoch as u64,
            "native-wss-fixture-separate-binding-key",
        )
        .unwrap();
        let tools = Arc::new(NativeToolHost::new("native-wss", context, link, authorizer).unwrap());
        let host = Arc::new(
            NativeLiveHost::open(tools, &root.path().join("projection"), true, 1).unwrap(),
        );
        let journal = root.path().join("host-state.bin");
        let mut agent = HostAgent::open(&config, &key, &journal, true, host.clone()).unwrap();
        let (stop, rx) = watch::channel(false);
        let agent = Some(tokio::spawn(async move { agent.run(rx).await }));
        let ca = std::fs::read(root.path().join("ca.der")).unwrap();
        let http = reqwest::Client::builder()
            .no_proxy()
            .add_root_certificate(reqwest::Certificate::from_der(&ca).unwrap())
            .timeout(Duration::from_secs(12))
            .build()
            .unwrap();
        let h = Self {
            _root: root,
            _server: server,
            host,
            config,
            key,
            journal,
            stop,
            agent,
            http,
            origin: cfg.origin.clone(),
            resource: info["resource"].as_str().unwrap().into(),
            token: info["access_token"].as_str().unwrap().into(),
            inspect_token: info["inspection_token"].as_str().unwrap().into(),
            protocol: info["protocol"].as_str().unwrap().into(),
            token_endpoint: info["token_endpoint"].as_str().unwrap().into(),
            refresh: info["refresh_token"].as_str().unwrap().into(),
        };
        h.wait("ready", true).await;
        h
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
    async fn wait(&self, field: &str, value: bool) {
        let end = Instant::now() + Duration::from_secs(18);
        loop {
            if self.inspect().await[field] == value {
                return;
            }
            if self.agent.as_ref().is_some_and(|task| task.is_finished()) {
                panic!("native Agent exited before expected fixture state");
            }
            assert!(
                Instant::now() < end,
                "native gateway state timeout ({field})"
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
                "io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"native-wss-fixture","version":"1"}}}}))
            .send().await.unwrap();
        assert_eq!(result.status(), reqwest::StatusCode::OK);
        let value: Value = result.json().await.unwrap();
        value["result"]["structuredContent"].clone()
    }
    async fn approve(&self, chat: &str, field: &str) -> String {
        let pending = self
            .rpc(
                7001,
                chat,
                "request_chat_authorization",
                json!({"scopes":["files.read"]}),
            )
            .await;
        assert_eq!(
            pending["authorization"]["status"], "pending",
            "pending authorization did not reach native authorizer"
        );
        let id = pending["authorization"]["id"].as_str().unwrap().to_owned();
        assert!(!self.inspect().await[field].as_bool().unwrap());
        self.host
            .tools
            .authorizer
            .decide("native-wss", &id, true, &["files.read".into()])
            .unwrap();
        self.wait(field, true).await;
        id
    }
    async fn stop_agent(&mut self) {
        self.stop.send(true).unwrap();
        let result = tokio::time::timeout(Duration::from_secs(5), self.agent.take().unwrap())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(result, Ok(()));
    }
    async fn restart_agent(&mut self) {
        let (stop, rx) = watch::channel(false);
        self.stop = stop;
        let mut agent = HostAgent::open(
            &self.config,
            &self.key,
            &self.journal,
            false,
            self.host.clone(),
        )
        .unwrap();
        self.agent = Some(tokio::spawn(async move { agent.run(rx).await }));
        self.wait("ready", true).await;
    }
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn cloud_request_reaches_native_pending_and_only_native_decision_enables_real_tools() {
    let h = Harness::start().await;
    let before = h.rpc(7000, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(before["ok"], true);
    h.approve("native-A", "eligible_a").await;
    let result = h.rpc(7002, "native-A", "workspace_probe", json!({})).await;
    assert_eq!(result["ok"], true, "NATIVE_CLOUD_DISPATCH_DID_NOT_EXECUTE");
    assert_eq!(result["execution"], "native_tool_dispatch");
    assert!(!result.to_string().contains("native-canary.txt"));
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn cloud_oauth_forgery_and_foreign_session_never_approve_or_disclose_native_files() {
    let h = Harness::start().await;
    let forged = h
        .rpc(
            7010,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":["files.read"],"approve":true}),
        )
        .await;
    assert_ne!(forged["ok"], true);
    assert!(h.host.tools.authorizer.snapshot("native-wss")["records"]
        .as_array()
        .unwrap()
        .is_empty());
    h.approve("native-A", "eligible_a").await;
    for id in 7011..7021 {
        let foreign = h
            .rpc(
                id,
                "native-B",
                "request_chat_authorization",
                json!({"scopes":["files.read"]}),
            )
            .await;
        assert_ne!(foreign["ok"], true);
        assert!(!foreign
            .to_string()
            .contains("native-cloud-real-file-canary"));
    }
    assert_eq!(
        h.host.tools.authorizer.snapshot("native-wss")["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn native_revoke_and_both_signed_drain_barriers_precede_successor_execution() {
    let h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    let old_epoch = h.inspect().await["authority_epoch"].as_i64().unwrap();
    h.host.tools.authorizer.revoke("native-wss", None);
    h.wait("eligible_a", false).await;
    let end = Instant::now() + Duration::from_secs(18);
    loop {
        if h.inspect().await["phase"] == "free" {
            break;
        }
        assert!(Instant::now() < end);
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    h.approve("native-B", "eligible_b").await;
    assert!(h.inspect().await["authority_epoch"].as_i64().unwrap() > old_epoch);
    assert_ne!(
        h.rpc(7030, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
    assert_eq!(
        h.rpc(7031, "native-B", "workspace_probe", json!({})).await["ok"],
        true
    );
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn actual_native_pause_resume_fences_stale_cloud_projection_and_pending_allocation() {
    let h = Harness::start().await;
    h.host.tools.context.execution_gate.pause().unwrap();
    let p = h
        .rpc(
            7040,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":["files.read"]}),
        )
        .await;
    assert_ne!(p["ok"], true);
    assert!(h.host.tools.authorizer.snapshot("native-wss")["records"]
        .as_array()
        .unwrap()
        .is_empty());
    h.host.tools.context.execution_gate.resume().unwrap();
    h.approve("native-A", "eligible_a").await;
    h.host.tools.context.execution_gate.pause().unwrap();
    let off = h.rpc(7041, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(off["ok"], true);
    h.wait("eligible_a", false).await;
    h.host.tools.context.execution_gate.resume().unwrap();
    h.wait("eligible_a", true).await;
    assert_eq!(
        h.rpc(7042, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn native_agent_restart_preserves_request_tombstone_without_reexecution() {
    let mut h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    assert_eq!(
        h.rpc(7050, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
    h.stop_agent().await;
    h.wait("ready", false).await;
    h.restart_agent().await;
    h.wait("eligible_a", true).await;
    let again = h.rpc(7050, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(again["ok"], true);
    assert_eq!(
        h.rpc(7051, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn agent_absence_keeps_oauth_refresh_and_public_catalog_available_without_queue() {
    let mut h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    h.stop_agent().await;
    h.wait("ready", false).await;
    let offline = h.rpc(7060, "native-A", "workspace_probe", json!({})).await;
    assert_eq!(offline["error"]["code"], "WORKSPACE_OFFLINE");
    let refresh = h
        .http
        .post(&h.token_endpoint)
        .form(&[
            ("grant_type", "refresh_token"),
            ("client_id", "native-fixture-client"),
            ("refresh_token", h.refresh.as_str()),
            ("resource", h.resource.as_str()),
        ])
        .send()
        .await
        .unwrap();
    assert_eq!(refresh.status(), reqwest::StatusCode::OK);
    let data: Value = refresh.json().await.unwrap();
    assert!(data["access_token"].as_str().is_some());
    let response=h.http.post(&h.resource).bearer_auth(data["access_token"].as_str().unwrap())
        .header("mcp-protocol-version",&h.protocol).header("mcp-method","tools/list")
        .header("accept","application/json, text/event-stream")
        .json(&json!({"jsonrpc":"2.0","id":7061,"method":"tools/list","params":{"_meta":{
            "io.modelcontextprotocol/protocolVersion":h.protocol,"io.modelcontextprotocol/clientCapabilities":{}}}}))
        .send().await.unwrap();
    assert_eq!(response.status(), reqwest::StatusCode::OK);
    let catalog: Value = response.json().await.unwrap();
    assert!(!catalog["result"]["tools"].as_array().unwrap().is_empty());
    assert_ne!(
        h.rpc(
            7062,
            "native-B",
            "request_chat_authorization",
            json!({"scopes":["files.read"]})
        )
        .await["ok"],
        true
    );
    assert_eq!(
        h.host.tools.authorizer.snapshot("native-wss")["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}

#[path = "wss_drain_tests.rs"]
mod managed_drain_tests;

#[path = "wss_catalog_tests.rs"]
mod catalog_tests;

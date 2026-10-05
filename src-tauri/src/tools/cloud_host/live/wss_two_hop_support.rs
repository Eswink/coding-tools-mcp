//! Shipped enrollment, real native authority, HTTPS443 -> Nginx8080 -> Gateway.
//! Private IPC observes database facts; it never supplies native eligibility.
use super::super::*;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_agent::AgentConfig;
use std::{collections::BTreeSet, os::unix::fs::MetadataExt, path::Path};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use uuid::Uuid;

const PROTOCOL: &str = "2026-07-28";
pub(super) const CANARY: &str = "native-cloud-real-file-canary";
#[derive(serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Op {
    Inspect,
    GatewayStop,
    GatewayStart,
    RevokeDevice,
    RestartDatabase,
}
fn private_bytes(path: &Path) -> Vec<u8> {
    assert_eq!(path.canonicalize().unwrap(), path);
    let parent = path.parent().unwrap().metadata().unwrap();
    let file = path.symlink_metadata().unwrap();
    // SAFETY: geteuid has no arguments or writable user memory.
    let uid = unsafe { libc::geteuid() };
    assert_eq!(uid, 65532);
    assert!(parent.uid() == uid && parent.mode() & 0o777 == 0o700);
    assert!(file.is_file() && file.nlink() == 1 && file.uid() == uid);
    assert!(file.mode() & 0o777 == 0o600 && file.len() <= 32768);
    std::fs::read(path).unwrap()
}
fn exact_fields(value: &Value, names: &[&str]) {
    let keys: BTreeSet<_> = value
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(keys, names.iter().copied().collect());
}
pub(super) fn denied(value: &Value) {
    assert_eq!(value["ok"], false);
    assert!(value["error"]["code"].is_string());
    let text = value.to_string();
    for private in [CANARY, "grant_id", "authority_epoch", "conversation_digest"] {
        assert!(
            !text.contains(private),
            "private authority or output disclosed"
        );
    }
}
pub(super) fn sockets() -> BTreeSet<String> {
    ["/proc/net/tcp", "/proc/net/tcp6"]
        .into_iter()
        .flat_map(|path| {
            std::fs::read_to_string(path)
                .unwrap()
                .lines()
                .skip(1)
                .filter_map(|line| {
                    let fields: Vec<_> = line.split_whitespace().collect();
                    (fields[3] == "01" && fields[2].ends_with(":01BB"))
                        .then(|| format!("{} {}", fields[1], fields[2]))
                })
                .collect::<Vec<_>>()
        })
        .collect()
}
pub(super) struct TwoHop {
    pub(super) root: tempfile::TempDir,
    pub(super) input: Value,
    pub(super) cfg: AgentConfig,
    pub(super) config: Vec<u8>,
    pub(super) key: Vec<u8>,
    pub(super) host: Option<Arc<NativeLiveHost>>,
    pub(super) agent: Option<tokio::task::JoinHandle<Result<(), AgentError>>>,
    pub(super) stop: watch::Sender<bool>,
    pub(super) started: Instant,
    pub(super) ids: tokio::sync::Mutex<u64>,
    pub(super) http: reqwest::Client,
    pub(super) token: String,
}
impl Drop for TwoHop {
    fn drop(&mut self) {
        let _ = self.stop.send(true);
        if let Some(task) = self.agent.take() {
            task.abort();
        }
    }
}
impl TwoHop {
    pub(super) async fn load(case: &str, mode: &str) -> Self {
        let path = std::env::var("CTM_TWO_HOP_BOOTSTRAP").expect("dedicated fixture required");
        let input: Value = serde_json::from_slice(&private_bytes(Path::new(&path))).unwrap();
        exact_fields(
            &input,
            &[
                "schema",
                "key",
                "connection",
                "owner_password",
                "control_socket",
                "ca_der_file",
                "case",
                "client_id",
                "redirect_uri",
                "certificate_mode",
                "certificate_preflight",
            ],
        );
        assert_eq!(input["schema"], 1);
        assert_eq!(input["case"], case);
        assert_eq!(input["certificate_mode"], mode);
        assert_eq!(input["certificate_preflight"], true);
        let mut connection = input["connection"].clone();
        exact_fields(
            &connection,
            &[
                "version",
                "origin",
                "prefix",
                "connector",
                "device",
                "device_epoch",
                "authority_epoch",
                "public_key",
                "run_seconds",
            ],
        );
        assert_eq!(connection["version"], 1);
        let root = tempfile::tempdir().unwrap();
        let object = connection.as_object_mut().unwrap();
        object.remove("version");
        object.insert(
            "revision_file".into(),
            json!(root.path().join("unused-revision")),
        );
        object.insert("ca_der_file".into(), input["ca_der_file"].clone());
        let config = serde_json::to_vec(&connection).unwrap();
        let cfg = AgentConfig::from_bytes(&config).unwrap();
        assert_eq!(cfg.origin, "https://gateway.example.invalid");
        assert_eq!(cfg.prefix, "/coding-tools");
        let ca = private_bytes(cfg.ca_der_file.as_ref().unwrap());
        let http = reqwest::Client::builder()
            .no_proxy()
            .pool_max_idle_per_host(0)
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(12))
            .add_root_certificate(reqwest::Certificate::from_der(&ca).unwrap())
            .build()
            .unwrap();
        let tcp = tokio::time::timeout(
            Duration::from_secs(3),
            tokio::net::TcpStream::connect(("gateway.example.invalid", 443)),
        )
        .await
        .unwrap()
        .unwrap();
        drop(tcp);
        let host = Some(native_host(root.path(), &cfg, true));
        let key = serde_json::to_vec(&input["key"]).unwrap();
        let (stop, _) = watch::channel(false);
        let mut h = Self {
            root,
            input,
            cfg,
            config,
            key,
            host,
            agent: None,
            stop,
            started: Instant::now(),
            ids: tokio::sync::Mutex::new(0),
            http,
            token: String::new(),
        };
        h.launch(true);
        h
    }
    pub(super) fn host(&self) -> &Arc<NativeLiveHost> {
        self.host.as_ref().unwrap()
    }
    pub(super) fn journal(&self) -> std::path::PathBuf {
        self.root.path().join("host-state.bin")
    }
    pub(super) fn launch(&mut self, initialize: bool) {
        let mut agent = HostAgent::open(
            &self.config,
            &self.key,
            &self.journal(),
            initialize,
            self.host().clone(),
        )
        .unwrap();
        let (stop, rx) = watch::channel(false);
        self.stop = stop;
        self.started = Instant::now();
        self.agent = Some(tokio::spawn(async move { agent.run(rx).await }));
    }
    pub(super) async fn stop(&mut self) {
        self.stop.send(true).unwrap();
        assert_eq!(
            tokio::time::timeout(Duration::from_secs(6), self.agent.take().unwrap())
                .await
                .unwrap()
                .unwrap(),
            Ok(())
        );
    }
    pub(super) async fn control(&self, op: Op) -> Value {
        tokio::time::timeout(Duration::from_secs(65), async {
            let mut ids = self.ids.lock().await;
            *ids += 1;
            let id = *ids;
            let mut socket =
                tokio::net::UnixStream::connect(self.input["control_socket"].as_str().unwrap())
                    .await
                    .unwrap();
            socket
                .write_all(format!("{}\n", json!({"id":id,"op":op})).as_bytes())
                .await
                .unwrap();
            drop(ids);
            let mut bytes = Vec::new();
            socket.take(4097).read_to_end(&mut bytes).await.unwrap();
            assert!(bytes.len() <= 4096);
            let reply: Value = serde_json::from_slice(&bytes).unwrap();
            assert_eq!(reply["id"], id);
            assert_eq!(reply["ok"], true);
            reply["result"].clone()
        })
        .await
        .expect("bounded private fixture operation")
    }
    pub(super) async fn wait(&self, predicate: impl Fn(&Value) -> bool) -> Value {
        tokio::time::timeout(Duration::from_secs(20), async {
            loop {
                let state = self.control(Op::Inspect).await;
                if predicate(&state) {
                    break state;
                }
                assert!(
                    self.agent.as_ref().is_none_or(|a| !a.is_finished()),
                    "Agent exited before readiness"
                );
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        })
        .await
        .expect("native channel/projection did not reach required state")
    }
    pub(super) async fn ready(&self) -> Value {
        self.wait(|s| {
            s["connected"] == true
                && s["reconciled"] == true
                && s["last_seq"].as_i64().unwrap() >= 5
                && self
                    .host()
                    .tools
                    .link
                    .matches(&crate::auth::cloud_context::CloudPeer {
                        connector: self.cfg.connector,
                        device: self.cfg.device,
                        device_epoch: self.cfg.device_epoch as u64,
                        gateway_boot: Uuid::parse_str(s["gateway_boot"].as_str().unwrap()).unwrap(),
                        session: Uuid::parse_str(s["session"].as_str().unwrap()).unwrap(),
                        generation: s["generation"].as_u64().unwrap(),
                    })
        })
        .await
    }
    pub(super) async fn start(case: &str) -> Self {
        let mut h = Self::load(case, "valid").await;
        h.ready().await;
        h.token = h.oauth().await;
        h
    }
    pub(super) fn endpoint(&self, path: &str) -> String {
        format!("{}{}{path}", self.cfg.origin, self.cfg.prefix)
    }
    pub(super) async fn oauth(&self) -> String {
        let verifier = "a".repeat(43);
        let challenge = URL_SAFE_NO_PAD.encode(ring::digest::digest(
            &ring::digest::SHA256,
            verifier.as_bytes(),
        ));
        let client = self.input["client_id"].as_str().unwrap();
        let redirect = self.input["redirect_uri"].as_str().unwrap();
        let resource = self.endpoint(&format!("/mcp/{}", self.cfg.connector));
        let response = self
            .http
            .get(self.endpoint("/oauth/authorize"))
            .query(&[
                ("response_type", "code"),
                ("client_id", client),
                ("redirect_uri", redirect),
                ("resource", &resource),
                ("scope", "mcp"),
                ("state", "native-two-hop"),
                ("code_challenge", &challenge),
                ("code_challenge_method", "S256"),
            ])
            .send()
            .await
            .unwrap();
        let (cookie, csrf) = oauth_page(response).await;
        let response = self
            .http
            .post(self.endpoint("/oauth/login"))
            .header("Origin", &self.cfg.origin)
            .header("Cookie", cookie)
            .form(&[
                ("csrf", csrf.as_str()),
                ("password", self.input["owner_password"].as_str().unwrap()),
            ])
            .send()
            .await
            .unwrap();
        let (cookie, csrf) = oauth_page(response).await;
        let response = self
            .http
            .post(self.endpoint("/oauth/consent"))
            .header("Origin", &self.cfg.origin)
            .header("Cookie", cookie)
            .form(&[("csrf", csrf.as_str()), ("decision", "allow")])
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::SEE_OTHER);
        let location = response.headers()["location"].to_str().unwrap();
        assert!(location.starts_with(&format!("{redirect}?")));
        let url = reqwest::Url::parse(location).unwrap();
        let query: std::collections::HashMap<_, _> = url.query_pairs().collect();
        assert_eq!(query["state"], "native-two-hop");
        let response = self
            .http
            .post(self.endpoint("/oauth/token"))
            .form(&[
                ("grant_type", "authorization_code"),
                ("client_id", client),
                ("code", query["code"].as_ref()),
                ("redirect_uri", redirect),
                ("code_verifier", &verifier),
                ("resource", &resource),
            ])
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::OK);
        response.json::<Value>().await.unwrap()["access_token"]
            .as_str()
            .unwrap()
            .into()
    }
    pub(super) async fn rpc(&self, id: i64, chat: &str, name: &str, args: Value) -> Value {
        let response = self.http.post(self.endpoint(&format!("/mcp/{}", self.cfg.connector))).bearer_auth(&self.token)
            .header("mcp-protocol-version", PROTOCOL).header("mcp-method", "tools/call").header("mcp-name", name)
            .header("accept", "application/json, text/event-stream").json(&json!({"jsonrpc":"2.0","id":id,
                "method":"tools/call","params":{"name":name,"arguments":args,"_meta":{"openai/session":chat,
                "io.modelcontextprotocol/protocolVersion":PROTOCOL,"io.modelcontextprotocol/clientCapabilities":{},
                "io.modelcontextprotocol/clientInfo":{"name":"native-two-hop","version":"1"}}}})).send().await.unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::OK);
        let envelope = response.json::<Value>().await.unwrap();
        let result = &envelope["result"]["structuredContent"];
        assert!(
            result.is_object() && result["ok"].is_boolean(),
            "missing actual MCP tool result"
        );
        result.clone()
    }
    pub(super) async fn read(&self, id: i64, chat: &str) -> Value {
        self.rpc(id, chat, "read_file", json!({"path":"native-canary.txt"}))
            .await
    }
    pub(super) async fn grant(&self) {
        denied(&self.read(9000, "native-A").await);
        let pending = self
            .rpc(
                9001,
                "native-A",
                "request_chat_authorization",
                json!({"scopes":["files.read"]}),
            )
            .await;
        assert_eq!(pending["authorization"]["status"], "pending");
        let id = pending["authorization"]["id"].as_str().unwrap();
        assert!(
            self.host().tools.authorizer.snapshot("native-wss")["records"]
                .as_array()
                .unwrap()
                .iter()
                .any(|r| r["id"] == id && r["status"] == "pending")
        );
        denied(&self.read(9002, "native-A").await);
        self.host()
            .tools
            .authorizer
            .decide("native-wss", id, true, &["files.read".into()])
            .unwrap();
        self.wait(|s| s["reconciled"] == true && s["phase"] == "active")
            .await;
    }
    pub(super) async fn no_replay(&self, id: i64) {
        let before = self.control(Op::Inspect).await["ledger"].clone();
        let canary = std::fs::read(self.root.path().join("workspace/native-canary.txt")).unwrap();
        denied(&self.read(id, "native-A").await);
        assert!(
            self.control(Op::Inspect).await["ledger"] == before,
            "duplicate changed the request ledger"
        );
        assert_eq!(
            std::fs::read(self.root.path().join("workspace/native-canary.txt")).unwrap(),
            canary
        );
        assert!(self
            .read(id + 1, "native-A")
            .await
            .to_string()
            .contains(CANARY));
    }
}
async fn oauth_page(response: reqwest::Response) -> (String, String) {
    assert_eq!(response.status(), reqwest::StatusCode::OK);
    let cookie = response.headers()["set-cookie"]
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_owned();
    let body = response.text().await.unwrap();
    let captures = regex::Regex::new(r#"name=csrf value="([A-Za-z0-9_-]+)""#)
        .unwrap()
        .captures(&body)
        .unwrap();
    (cookie, captures[1].into())
}

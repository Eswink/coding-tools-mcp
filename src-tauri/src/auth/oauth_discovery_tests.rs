//! Network characterization tests. Fixture credentials are not user credentials.
use serde_json::{json, Value};
use crate::workspace::{AuthConfig, RuntimeConfig};
use super::PublicOrigin;

const ORIGIN: &str = "https://oauth-fixture.example";

struct Server {
    _root: tempfile::TempDir,
    stop: Option<crate::mcp::ShutdownSender>,
    task: tauri::async_runtime::JoinHandle<()>,
    base: String,
    client: reqwest::Client,
}
impl Server {
    fn start() -> Self {
        let root = tempfile::tempdir().unwrap();
        let reservation = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = reservation.local_addr().unwrap().port();
        drop(reservation);
        let (stop, task) = crate::mcp::spawn_listener_with_origin(
            port, root.path().into(), uuid::Uuid::new_v4().to_string(),
            AuthConfig { oauth_client_id: "fixture-client".into(), ..Default::default() },
            PublicOrigin::managed(ORIGIN).unwrap(), Some("fixture-client-secret".into()),
            Some("fixture-password".into()), Some("fixture-signing-key".into()),
            RuntimeConfig::default(),
        ).unwrap();
        Self { _root: root, stop: Some(stop), task, base: format!("http://127.0.0.1:{port}"),
            client: reqwest::Client::builder().no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(std::time::Duration::from_secs(5)).build().unwrap() }
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
        self.task.abort();
    }
}

#[tokio::test]
async fn path_specific_discovery_is_available_without_credentials() {
    let s = Server::start();
    for path in ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"] {
        let r = s.client.get(format!("{}{path}", s.base)).send().await.unwrap();
        assert_eq!(r.status(), 200, "missing discovery route: {path}");
        let value: Value = r.json().await.unwrap();
        assert_eq!(value["authorization_servers"], json!([ORIGIN]));
    }
}

#[tokio::test]
async fn advertised_resource_matches_the_selected_mcp_endpoint_contract() {
    let s = Server::start();
    let value: Value = s.client.get(format!("{}/.well-known/oauth-protected-resource", s.base))
        .send().await.unwrap().json().await.unwrap();
    // Origin-only identifiers are legal in MCP. This application explicitly
    // chooses /mcp, independently from the authorization-server issuer.
    assert_eq!(value["resource"], format!("{ORIGIN}/mcp"));
}

#[tokio::test]
async fn unauthenticated_post_advertises_path_specific_metadata() {
    let s = Server::start();
    let r = s.client.post(format!("{}/mcp", s.base))
        .json(&json!({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{}}))
        .send().await.unwrap();
    assert_eq!(r.status(), 401);
    let challenge = r.headers().get("www-authenticate").unwrap().to_str().unwrap();
    assert!(challenge.contains(&format!("resource_metadata=\"{ORIGIN}/.well-known/oauth-protected-resource/mcp\"")), "{challenge}");
}

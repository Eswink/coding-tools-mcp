use serde_json::json;

use crate::auth::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};

struct TestServer {
    stop: Option<crate::mcp::ShutdownSender>,
    task: tauri::async_runtime::JoinHandle<()>,
    base: String,
    origin: PublicOrigin,
    _root: tempfile::TempDir,
}

impl TestServer {
    fn new(initial_public_origin: &str) -> Self {
        let root = tempfile::tempdir().unwrap();
        let reserve = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = reserve.local_addr().unwrap().port();
        drop(reserve);
        let origin = PublicOrigin::managed(initial_public_origin).unwrap();
        let (stop, task) = crate::mcp::spawn_listener_with_origin(
            port,
            root.path().into(),
            uuid::Uuid::new_v4().to_string(),
            AuthConfig { oauth_client_id: "test-client".into(), ..Default::default() },
            origin.clone(),
            None,
            Some("password".into()),
            Some(fixture::KEY.into()),
            RuntimeConfig::default(),
        ).unwrap();
        Self {
            stop: Some(stop),
            task,
            base: format!("http://127.0.0.1:{port}"),
            origin,
            _root: root,
        }
    }
}

impl Drop for TestServer {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
    }
}

async fn get(client: &reqwest::Client, url: &str, origin: Option<&str>) -> reqwest::Response {
    let mut request = client.get(url);
    if let Some(origin) = origin {
        request = request.header("Origin", origin);
    }
    request.send().await.unwrap()
}

#[tokio::test]
async fn missing_and_local_origin_remain_compatible() {
    let server = TestServer::new("https://mcp.example.com");
    let client = fixture::client();
    let url = format!("{}/mcp", server.base);

    assert_eq!(get(&client, &url, None).await.status(), 200);
    assert_eq!(get(&client, &url, Some("http://localhost:1420")).await.status(), 200);
    assert_eq!(get(&client, &url, Some("http://127.0.0.1:1420")).await.status(), 200);
}

#[tokio::test]
async fn unrelated_malformed_and_opaque_origins_are_forbidden() {
    let server = TestServer::new("https://mcp.example.com");
    let client = fixture::client();
    let url = format!("{}/mcp", server.base);

    for origin in ["https://attacker.example", "not-a-url", "null"] {
        let response = get(&client, &url, Some(origin)).await;
        assert_eq!(response.status(), 403, "origin={origin}");
        let text = response.text().await.unwrap();
        assert!(!text.contains(origin), "rejection reflected attacker Origin: {text}");
    }
}

#[tokio::test]
async fn managed_public_origin_allowlist_tracks_live_publication() {
    let server = TestServer::new("https://old.example.com");
    let client = fixture::client();
    let url = format!("{}/mcp", server.base);

    assert_eq!(get(&client, &url, Some("https://old.example.com:9443")).await.status(), 200);
    server.origin.publish("https://current.example.com").unwrap();
    assert_eq!(get(&client, &url, Some("https://current.example.com")).await.status(), 200);
    assert_eq!(get(&client, &url, Some("https://old.example.com")).await.status(), 403);
}

#[tokio::test]
async fn oauth_control_plane_is_guarded_but_missing_origin_remains_compatible() {
    let server = TestServer::new("https://mcp.example.com");
    let client = fixture::client();

    let metadata = format!("{}/.well-known/oauth-authorization-server", server.base);
    assert_eq!(get(&client, &metadata, None).await.status(), 200);
    assert_eq!(get(&client, &metadata, Some("https://attacker.example")).await.status(), 403);

    let token = format!("{}/oauth/token", server.base);
    let missing = client.post(&token)
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body("grant_type=refresh_token&refresh_token=synthetic")
        .send().await.unwrap();
    assert_ne!(missing.status(), 403);

    let blocked = client.post(&token)
        .header("Origin", "https://attacker.example")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body("grant_type=refresh_token&refresh_token=synthetic")
        .send().await.unwrap();
    assert_eq!(blocked.status(), 403);

    let mcp = format!("{}/mcp", server.base);
    let post = client.post(&mcp)
        .json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
        .send().await.unwrap();
    assert_ne!(post.status(), 403);
}

use serde_json::{json, Value};

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

async fn assert_generic_forbidden(response: reqwest::Response, forbidden_values: &[&str]) {
    assert_eq!(response.status(), 403);
    assert_eq!(
        response.headers().get("cache-control").and_then(|value| value.to_str().ok()),
        Some("no-store")
    );
    let value: Value = response.json().await.unwrap();
    assert_eq!(value["jsonrpc"], "2.0");
    assert_eq!(value["id"], Value::Null);
    assert_eq!(value["error"]["code"], -32000);
    assert_eq!(value["error"]["message"], "Invalid Origin");
    assert!(value["error"].get("data").is_none());
    let encoded = value.to_string();
    for forbidden in forbidden_values {
        assert!(
            !encoded.contains(forbidden),
            "rejection reflected attacker-controlled value {forbidden:?}: {encoded}"
        );
    }
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

    assert_generic_forbidden(
        get(&client, &url, Some("https://attacker.example")).await,
        &["attacker.example"],
    ).await;
    assert_generic_forbidden(
        get(&client, &url, Some("not-a-url")).await,
        &["not-a-url"],
    ).await;
    // JSON-RPC itself contains `id:null`, so validate the generic error shape
    // instead of searching the encoded body for the literal "null".
    assert_generic_forbidden(get(&client, &url, Some("null")).await, &[]).await;
}

#[tokio::test]
async fn managed_public_origin_allowlist_tracks_live_publication() {
    let server = TestServer::new("https://old.example.com");
    let client = fixture::client();
    let url = format!("{}/mcp", server.base);

    assert_eq!(get(&client, &url, Some("https://old.example.com:9443")).await.status(), 200);
    server.origin.publish("https://current.example.com").unwrap();
    assert_eq!(get(&client, &url, Some("https://current.example.com")).await.status(), 200);
    assert_eq!(get(&client, &url, Some("https://CURRENT.EXAMPLE.COM:8443")).await.status(), 200);
    assert_generic_forbidden(
        get(&client, &url, Some("https://old.example.com")).await,
        &["old.example.com"],
    ).await;
}

#[tokio::test]
async fn oauth_control_plane_is_guarded_but_missing_origin_remains_compatible() {
    let server = TestServer::new("https://mcp.example.com");
    let client = fixture::client();

    let metadata = format!("{}/.well-known/oauth-authorization-server", server.base);
    assert_eq!(get(&client, &metadata, None).await.status(), 200);
    assert_generic_forbidden(
        get(&client, &metadata, Some("https://attacker.example")).await,
        &["attacker.example"],
    ).await;

    let resource = format!("{}/.well-known/oauth-protected-resource/mcp", server.base);
    assert_generic_forbidden(
        get(&client, &resource, Some("https://attacker.example")).await,
        &["attacker.example"],
    ).await;

    let authorize = format!("{}/oauth/authorize", server.base);
    assert_generic_forbidden(
        get(&client, &authorize, Some("https://attacker.example")).await,
        &["attacker.example"],
    ).await;
    let authorize_post = client.post(&authorize)
        .header("Origin", "https://attacker.example")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body("action=approve")
        .send().await.unwrap();
    assert_generic_forbidden(authorize_post, &["attacker.example"]).await;

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
    assert_generic_forbidden(blocked, &["attacker.example"]).await;

    let mcp = format!("{}/mcp", server.base);
    let post = client.post(&mcp)
        .json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
        .send().await.unwrap();
    assert_ne!(post.status(), 403);

    let blocked_post = client.post(&mcp)
        .header("Origin", "https://attacker.example")
        .json(&json!({"jsonrpc":"2.0","id":2,"method":"initialize","params":{}}))
        .send().await.unwrap();
    assert_generic_forbidden(blocked_post, &["attacker.example"]).await;

    let preflight = client.request(reqwest::Method::OPTIONS, &mcp)
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST")
        .send().await.unwrap();
    assert_generic_forbidden(preflight, &["attacker.example"]).await;

    let mut duplicate_origins = reqwest::header::HeaderMap::new();
    duplicate_origins.append(
        reqwest::header::ORIGIN,
        reqwest::header::HeaderValue::from_static("https://mcp.example.com"),
    );
    duplicate_origins.append(
        reqwest::header::ORIGIN,
        reqwest::header::HeaderValue::from_static("https://attacker.example"),
    );
    let duplicated = client.get(&mcp).headers(duplicate_origins).send().await.unwrap();
    assert_generic_forbidden(duplicated, &["attacker.example"]).await;
}

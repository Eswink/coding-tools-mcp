//! Local HTTP integration tests. No Cloudflare account, FRPS server or real key.
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use jsonwebtoken::{encode, EncodingKey, Header};
use serde_json::{json, Value};
use tokio::sync::oneshot;
use super::PublicOrigin;

const KEY: &str = "local-integration-signing-key-not-a-real-credential";

struct Listener {
    base: String,
    stop: Option<oneshot::Sender<()>>,
    task: Option<tauri::async_runtime::JoinHandle<()>>,
    _workspace: tempfile::TempDir,
}

impl Drop for Listener {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
    }
}

impl Listener {
    fn start(actions: bool, origin: PublicOrigin) -> Self {
        let workspace = tempfile::tempdir().unwrap();
        let reservation = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = reservation.local_addr().unwrap().port();
        drop(reservation);
        let id = uuid::Uuid::new_v4().to_string();
        let pair = if actions {
            crate::actions::spawn_listener_with_origin(
                &id, port, workspace.path().to_path_buf(), origin,
                "oauth".into(), None, "test-client".into(), None,
                Some("test-password".into()), Some(KEY.into()),
                crate::tools::policy::PolicySettings::from_runtime(&crate::workspace::RuntimeConfig::default()),
            )
        } else {
            let mut auth = crate::workspace::AuthConfig::default();
            auth.oauth_client_id = "test-client".into();
            crate::mcp::spawn_listener_with_origin(
                port, workspace.path().to_path_buf(), id, auth, origin,
                None, Some("test-password".into()), Some(KEY.into()),
                crate::workspace::RuntimeConfig::default(),
            )
        }.expect("bind listener");
        Self { base: format!("http://127.0.0.1:{port}"), stop: Some(pair.0), task: Some(pair.1), _workspace: workspace }
    }

    async fn stop(mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
        if let Some(task) = self.task.take() {
            tokio::time::timeout(Duration::from_secs(5), task).await.expect("listener shutdown").expect("listener task");
        }
    }
}

fn client() -> reqwest::Client {
    reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(5)).build().unwrap()
}

fn token(origin: &str, mcp: bool) -> String {
    let resource = if mcp { format!("{origin}/mcp") } else { origin.to_string() };
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    encode(&Header::default(), &json!({
        "iss": origin, "aud": resource, "iat": now, "nbf": now, "exp": now + 600, "scope": "mcp",
        "sub":"desktop-owner", "client_id":"test-client", "jti":"identity-fixture"
    }), &EncodingKey::from_secret(KEY.as_bytes())).unwrap()
}

async fn metadata(base: &str) -> Value {
    client().get(format!("{base}/.well-known/oauth-authorization-server"))
        .send().await.unwrap().json().await.unwrap()
}

async fn authorized_status(base: &str, actions: bool, bearer: &str) -> reqwest::StatusCode {
    let path = if actions { "/actions/server_info" } else { "/mcp" };
    let body = if actions { json!({}) } else {
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
            "protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"local-test","version":"1"}
        }})
    };
    client().post(format!("{base}{path}")).bearer_auth(bearer).json(&body)
        .send().await.unwrap().status()
}

#[tokio::test]
async fn mcp_live_metadata_and_token_validation_switch_together() {
    let origin = PublicOrigin::managed("https://old.trycloudflare.com").unwrap();
    let listener = Listener::start(false, origin.clone());
    assert_eq!(metadata(&listener.base).await["issuer"], origin.snapshot());
    let old = token(&origin.snapshot(), true);
    assert_eq!(authorized_status(&listener.base, false, &old).await, 200);
    origin.publish("https://new.trycloudflare.com").unwrap();
    let metadata = metadata(&listener.base).await;
    assert_eq!(metadata["issuer"], "https://new.trycloudflare.com");
    assert_eq!(metadata["token_endpoint"], "https://new.trycloudflare.com/oauth/token");
    assert_eq!(authorized_status(&listener.base, false, &old).await, 401);
    assert_eq!(authorized_status(&listener.base, false, &token(&origin.snapshot(), true)).await, 200);
    listener.stop().await;
}

#[tokio::test]
async fn actions_openapi_metadata_and_bearer_share_the_live_origin() {
    let origin = PublicOrigin::managed("https://old.trycloudflare.com").unwrap();
    let listener = Listener::start(true, origin.clone());
    let old = token(&origin.snapshot(), false);
    origin.publish("https://new-actions.trycloudflare.com").unwrap();
    let document: Value = client().get(format!("{}/openapi.json", listener.base))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(document["servers"][0]["url"], origin.snapshot());
    assert_eq!(metadata(&listener.base).await["issuer"], origin.snapshot());
    assert_eq!(authorized_status(&listener.base, true, &old).await, 401);
    assert_eq!(authorized_status(&listener.base, true, &token(&origin.snapshot(), false)).await, 422); // OAuth valid, conversation unavailable: fail closed.
    listener.stop().await;
}

#[tokio::test]
async fn fixed_origin_and_key_keep_an_unexpired_token_valid_after_restart() {
    let fixed = "https://mcp.example.com";
    let bearer = token(fixed, true);
    let first = Listener::start(false, PublicOrigin::managed(fixed).unwrap());
    assert_eq!(authorized_status(&first.base, false, &bearer).await, 200);
    first.stop().await;
    let second = Listener::start(false, PublicOrigin::managed(fixed).unwrap());
    assert_eq!(authorized_status(&second.base, false, &bearer).await, 200);
    second.stop().await;
}

#[tokio::test]
async fn pending_managed_listener_does_not_advertise_attacker_controlled_issuer() {
    let origin = PublicOrigin::managed("").unwrap();
    let listener = Listener::start(false, origin);
    let value: Value = client().get(format!("{}/.well-known/oauth-authorization-server", listener.base))
        .header("x-forwarded-host", "attacker.example.com").header("x-forwarded-proto", "https")
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(value["issuer"], listener.base);
    listener.stop().await;
}

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

const CALLBACK: &str = "https://chatgpt.com/connector_platform_oauth_redirect";
const VERIFIER: &str = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";

async fn code(s: &Server, resource: &str) -> String {
    use base64::Engine;
    use sha2::Digest;
    let challenge = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .encode(sha2::Sha256::digest(VERIFIER.as_bytes()));
    let fields = [("response_type", "code"), ("client_id", "fixture-client"),
        ("redirect_uri", CALLBACK), ("code_challenge", challenge.as_str()),
        ("code_challenge_method", "S256"), ("resource", resource),
        ("scope", "mcp"), ("state", "discovery-fixture")];
    let page = s.client.get(format!("{}/oauth/authorize", s.base)).query(&fields)
        .send().await.unwrap();
    assert_eq!(page.status(), 200);
    assert!(page.text().await.unwrap().contains("<form"));
    let mut form = fields.to_vec();
    form.push(("password", "fixture-password"));
    let response = s.client.post(format!("{}/oauth/authorize", s.base)).form(&form)
        .send().await.unwrap();
    assert_eq!(response.status(), 303);
    let location = reqwest::Url::parse(response.headers()["location"].to_str().unwrap()).unwrap();
    assert_eq!(location.host_str(), Some("chatgpt.com"));
    assert!(location.query_pairs().any(|(k, v)| k == "state" && v == "discovery-fixture"));
    location.query_pairs().find(|(k, _)| k == "code").unwrap().1.into_owned()
}

async fn exchange(s: &Server, code: &str, resource: &str, verifier: &str, secret: &str) -> reqwest::Response {
    s.client.post(format!("{}/oauth/token", s.base))
        .basic_auth("fixture-client", Some(secret))
        .form(&[("grant_type", "authorization_code"), ("code", code),
            ("redirect_uri", CALLBACK), ("code_verifier", verifier), ("resource", resource)])
        .send().await.unwrap()
}

#[tokio::test]
async fn discovery_to_pkce_token_and_mcp_initialize_is_end_to_end() {
    let s = Server::start();
    let metadata: Value = s.client.get(format!("{}/.well-known/oauth-authorization-server", s.base))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(metadata["issuer"], ORIGIN);
    assert_eq!(metadata["authorization_endpoint"], format!("{ORIGIN}/oauth/authorize"));
    assert_eq!(metadata["token_endpoint"], format!("{ORIGIN}/oauth/token"));
    assert_eq!(metadata["code_challenge_methods_supported"], json!(["S256"]));
    assert_eq!(metadata["token_endpoint_auth_methods_supported"], json!(["client_secret_post", "client_secret_basic"]));
    assert!(metadata.get("registration_endpoint").is_none(), "Do not advertise unimplemented DCR");
    let resource = format!("{ORIGIN}/mcp");
    let auth_code = code(&s, &resource).await;
    let response = exchange(&s, &auth_code, &resource, VERIFIER, "fixture-client-secret").await;
    assert_eq!(response.status(), 200);
    let token: Value = response.json().await.unwrap();
    let bearer = token["access_token"].as_str().unwrap();
    assert!(super::principal::verify(bearer, "fixture-signing-key", ORIGIN, &resource).is_some());
    assert!(super::principal::verify(bearer, "fixture-signing-key", ORIGIN, ORIGIN).is_none());
    let response: Value = s.client.post(format!("{}/mcp", s.base)).bearer_auth(bearer)
        .json(&json!({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{}}))
        .send().await.unwrap().error_for_status().unwrap().json().await.unwrap();
    assert!(response.get("result").is_some(), "{response}");
    let denied: Value = s.client.post(format!("{}/mcp", s.base)).bearer_auth(bearer)
        .json(&json!({"jsonrpc":"2.0", "id":2, "method":"tools/call", "params":{
            "name":"server_info", "arguments":{}, "_meta":{"openai/session":"unapproved-fixture"}}}))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(denied["result"]["isError"], true, "OAuth is not a chat grant: {denied}");
    let replay = exchange(&s, &auth_code, &resource, VERIFIER, "fixture-client-secret").await;
    assert_eq!(replay.status(), 400);
    assert_eq!(replay.json::<Value>().await.unwrap()["error"], "invalid_grant");
}

#[tokio::test]
async fn resource_mismatch_and_invalid_pkce_do_not_issue_tokens() {
    let s = Server::start();
    let resource = format!("{ORIGIN}/mcp");
    for target in [ORIGIN, "https://other.example/mcp", "https://oauth-fixture.example/actions"] {
        let auth_code = code(&s, &resource).await;
        let response = exchange(&s, &auth_code, target, VERIFIER, "fixture-client-secret").await;
        assert_eq!(response.status(), 400);
        let body = response.json::<Value>().await.unwrap();
        assert_eq!(body["error"], "invalid_target");
        assert!(body.get("access_token").is_none());
    }
    let auth_code = code(&s, &resource).await;
    let wrong = "x".repeat(43);
    assert_eq!(exchange(&s, &auth_code, &resource, &wrong, "fixture-client-secret").await.status(), 400);
    // A failed PKCE attempt consumes the authorization code rather than enabling replay.
    assert_eq!(exchange(&s, &auth_code, &resource, VERIFIER, "fixture-client-secret").await.status(), 400);
}

#[tokio::test]
async fn client_authentication_and_resource_checks_are_not_relaxed() {
    let s = Server::start();
    let resource = format!("{ORIGIN}/mcp");
    let auth_code = code(&s, &resource).await;
    assert_eq!(exchange(&s, &auth_code, &resource, VERIFIER, "wrong-secret").await.status(), 401);
    assert_eq!(exchange(&s, &auth_code, &resource, VERIFIER, "fixture-client-secret").await.status(), 200);
    // A correctly signed token for the old origin audience must not reach MCP.
    let old = super::principal::issue(ORIGIN, ORIGIN, "fixture-signing-key", "fixture-client", 600).unwrap();
    let response = s.client.post(format!("{}/mcp", s.base)).bearer_auth(old)
        .json(&json!({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{}}))
        .send().await.unwrap();
    assert_eq!(response.status(), 401);
    assert!(response.headers()["www-authenticate"].to_str().unwrap().contains("/oauth-protected-resource/mcp"));
}

#[tokio::test]
async fn metadata_aliases_are_identical_and_uncacheable() {
    let s = Server::start();
    let mut documents = Vec::new();
    for path in ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-authorization-server"] {
        let response = s.client.get(format!("{}{path}", s.base)).send().await.unwrap();
        assert_eq!(response.status(), 200);
        assert_eq!(response.headers()["cache-control"], "no-store");
        documents.push(response.json::<Value>().await.unwrap());
    }
    assert_eq!(documents[0], documents[1]);
}

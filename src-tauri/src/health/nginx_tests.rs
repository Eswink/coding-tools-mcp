//! Opt-in real Nginx -> real application tests. Never contact a public host.
use std::{path::Path, process::Stdio, time::Duration};
use serde_json::{json, Value};
use super::probe::{self, Contract};
use crate::workspace::{AuthConfig, RuntimeConfig};

const ISSUER: &str = "https://nginx-fixture.example";
const CALLBACK: &str = "https://chatgpt.com/connector_platform_oauth_redirect";
const VERIFIER: &str = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";
const TEMPLATE: &str = include_str!("../../../docs/deployment/nginx-mcp-oauth.conf.template");

struct Backend {
    _root: tempfile::TempDir,
    base: String,
    stop: Option<crate::mcp::ShutdownSender>,
    task: tauri::async_runtime::JoinHandle<()>,
}
impl Backend {
    fn start() -> Self {
        let root = tempfile::tempdir().unwrap();
        let port = free_port();
        let (stop, task) = crate::mcp::spawn_listener_with_origin(port, root.path().into(),
            uuid::Uuid::new_v4().to_string(),
            AuthConfig { oauth_client_id: "fixture-client".into(), ..Default::default() },
            crate::auth::PublicOrigin::managed(ISSUER).unwrap(),
            Some("fixture-client-secret".into()), Some("fixture-password".into()),
            Some("fixture-signing".into()), RuntimeConfig::default()).unwrap();
        Self { _root: root, base: format!("http://127.0.0.1:{port}"), stop: Some(stop), task }
    }
}
impl Drop for Backend {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
        self.task.abort();
    }
}
fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port()
}
fn quoted(path: &Path) -> String {
    format!("\"{}\"", path.to_str().unwrap().replace('\\', "\\\\").replace('"', "\\\""))
}

struct Gateway { _root: tempfile::TempDir, base: String, child: tokio::process::Child }
impl Gateway {
    async fn start(upstream: &str, repaired: bool, shadow: &str) -> Self {
        let root = tempfile::tempdir().unwrap();
        let port = free_port();
        let www = root.path().join("www");
        let acme = www.join(".well-known/acme-challenge");
        std::fs::create_dir_all(&acme).unwrap();
        std::fs::write(acme.join("fixture"), "acme-preserved").unwrap();
        let routes = if repaired {
            TEMPLATE.replace("__MCP_UPSTREAM__", upstream).replace("__MCP_HOST__", "$host")
        } else { String::new() };
        let config = format!(r#"
worker_processes 1;
pid {};
error_log stderr crit;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {};
    proxy_temp_path {};
    server {{
        listen 127.0.0.1:{port};
        server_name _;
        root {};
        location = /ready {{ return 204; }}
        location ^~ /.well-known/acme-challenge/ {{ try_files $uri =404; }}
        {shadow}
        location ~ /\. {{ return 403; }}
        location / {{ proxy_pass {upstream}; proxy_http_version 1.1; }}
        {routes}
    }}
}}
"#, quoted(&root.path().join("nginx.pid")), quoted(&root.path().join("client-body")),
            quoted(&root.path().join("proxy-temp")), quoted(&www));
        let conf = root.path().join("nginx.conf");
        std::fs::write(&conf, config).unwrap();
        let test = tokio::process::Command::new("nginx").arg("-t").arg("-p").arg(root.path())
            .arg("-c").arg(&conf).output().await.expect("CI must install Nginx; do not silently skip");
        assert!(test.status.success(), "nginx -t: {}", String::from_utf8_lossy(&test.stderr));
        let child = tokio::process::Command::new("nginx").arg("-p").arg(root.path())
            .arg("-c").arg(conf).arg("-g").arg("daemon off; master_process off;")
            .kill_on_drop(true).stdout(Stdio::null()).stderr(Stdio::null()).spawn().unwrap();
        let mut gateway = Self { _root: root, base: format!("http://127.0.0.1:{port}"), child };
        // Bounded process readiness only, not retries of any test assertion.
        for _ in 0..40 {
            assert!(gateway.child.try_wait().unwrap().is_none(), "Nginx exited before readiness");
            if tokio::net::TcpStream::connect(("127.0.0.1", port)).await.is_ok() { return gateway; }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        panic!("Nginx did not become ready within two seconds");
    }
}
impl Drop for Gateway { fn drop(&mut self) { let _ = self.child.start_kill(); } }

async fn discovery(g: &Gateway, expected: &str) {
    let client = probe::client().unwrap();
    let resource = format!("{ISSUER}/mcp");
    assert!(probe::check(&client, &g.base, "/mcp", Contract::Mcp, ISSUER, "").await.ok);
    assert!(probe::check(&client, &g.base, "/mcp", Contract::Challenge, ISSUER, "").await.ok);
    for (path, contract) in [
        ("/.well-known/oauth-authorization-server", Contract::AuthorizationServer),
        ("/.well-known/oauth-protected-resource", Contract::ProtectedResource),
        ("/.well-known/oauth-protected-resource/mcp", Contract::ProtectedResource),
    ] {
        let result = probe::check(&client, &g.base, path, contract, ISSUER, &resource).await;
        assert_eq!(result.code, expected, "{path}: {result:?}");
        if expected == "verified" { assert!(result.ok); assert_eq!(result.status, Some(200)); }
        else { assert!(!result.ok); assert_eq!(result.status, Some(404)); }
    }
    let acme = client.get(format!("{}/.well-known/acme-challenge/fixture", g.base)).send().await.unwrap();
    assert_eq!(acme.status(), 200); assert_eq!(acme.text().await.unwrap(), "acme-preserved");
    assert_eq!(client.get(format!("{}/.git/HEAD", g.base)).send().await.unwrap().status(), 403);
}

#[tokio::test]
async fn real_nginx_exact_routes_override_static_and_regex_without_widening_access() {
    let backend = Backend::start();
    // Two independently reproduced config shapes; no guess that either is the live rule.
    for shadow in ["location ^~ /.well-known/ { try_files $uri =404; }",
        "location ~ ^/\\.well-known/ { return 404; }"] {
        let broken = Gateway::start(&backend.base, false, shadow).await;
        discovery(&broken, "nginx_discovery_route_not_found").await;
        let repaired = Gateway::start(&backend.base, true, shadow).await;
        discovery(&repaired, "verified").await;
    }
}

async fn issue_code(g: &Gateway, client: &reqwest::Client) -> String {
    use base64::Engine;
    use sha2::Digest;
    let challenge = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .encode(sha2::Sha256::digest(VERIFIER.as_bytes()));
    let resource = format!("{ISSUER}/mcp");
    let mut fields = vec![("response_type", "code"), ("client_id", "fixture-client"),
        ("redirect_uri", CALLBACK), ("code_challenge", &challenge), ("code_challenge_method", "S256"),
        ("resource", &resource), ("scope", "mcp"), ("state", "nginx-fixture")];
    let page = client.get(format!("{}/oauth/authorize", g.base)).query(&fields).send().await.unwrap();
    assert_eq!(page.status(), 200); assert!(page.text().await.unwrap().contains("<form"));
    fields.push(("password", "fixture-password"));
    let response = client.post(format!("{}/oauth/authorize", g.base)).form(&fields).send().await.unwrap();
    assert_eq!(response.status(), 303);
    let location = reqwest::Url::parse(response.headers()["location"].to_str().unwrap()).unwrap();
    assert_eq!(location.host_str(), Some("chatgpt.com"));
    assert!(location.query_pairs().any(|(k, v)| k == "state" && v == "nginx-fixture"));
    location.query_pairs().find(|(k, _)| k == "code").unwrap().1.into_owned()
}
async fn exchange(g: &Gateway, client: &reqwest::Client, code: &str, verifier: &str) -> reqwest::Response {
    client.post(format!("{}/oauth/token", g.base)).basic_auth("fixture-client", Some("fixture-client-secret"))
        .form(&[("grant_type", "authorization_code"), ("code", code), ("redirect_uri", CALLBACK),
            ("code_verifier", verifier), ("resource", &format!("{ISSUER}/mcp"))]).send().await.unwrap()
}

#[tokio::test]
async fn repaired_nginx_preserves_pkce_and_does_not_trust_forwarded_identity_or_grant_chat() {
    let backend = Backend::start();
    let gateway = Gateway::start(&backend.base, true, "location ^~ /.well-known/ { return 404; }").await;
    let client = probe::client().unwrap();
    discovery(&gateway, "verified").await;
    let metadata = client.get(format!("{}/.well-known/oauth-authorization-server", gateway.base))
        .header("x-forwarded-host", "attacker.example").header("x-forwarded-proto", "http")
        .header("forwarded", "host=attacker.example;proto=http").send().await.unwrap();
    assert_eq!(metadata.headers()["cache-control"], "no-store");
    assert_eq!(metadata.json::<Value>().await.unwrap()["issuer"], ISSUER);
    let code = issue_code(&gateway, &client).await;
    let token_response = exchange(&gateway, &client, &code, VERIFIER).await;
    assert_eq!(token_response.status(), 200);
    let token = token_response.json::<Value>().await.unwrap();
    let bearer = token["access_token"].as_str().unwrap();
    let initialized = client.post(format!("{}/mcp", gateway.base)).bearer_auth(bearer)
        .json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
        .send().await.unwrap();
    assert_eq!(initialized.status(), 200);
    assert!(initialized.json::<Value>().await.unwrap().get("result").is_some());
    let denied = client.post(format!("{}/mcp", gateway.base)).bearer_auth(bearer)
        .json(&json!({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
            "name":"server_info","arguments":{},"_meta":{"openai/session":"unapproved-fixture"}}}))
        .send().await.unwrap().json::<Value>().await.unwrap();
    assert_eq!(denied["result"]["isError"], true);
    assert_eq!(exchange(&gateway, &client, &code, VERIFIER).await.status(), 400);
    let code = issue_code(&gateway, &client).await;
    assert_eq!(exchange(&gateway, &client, &code, &"x".repeat(43)).await.status(), 400);
    assert_eq!(exchange(&gateway, &client, &code, VERIFIER).await.status(), 400);
}

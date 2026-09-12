use std::sync::{Arc, atomic::{AtomicUsize, Ordering}};
use std::time::{Duration, Instant};

use axum::{Router, Json, routing::get, http::StatusCode, response::IntoResponse};
use serde_json::{json, Value};

use super::{probe::{self, Contract}, run_health_checks, HealthRuntime};
use crate::workspace::{AuthConfig, RuntimeConfig, WorkspaceProfile};

const ISSUER: &str = "https://diagnostic-fixture.example";

struct HttpFixture {
    base: String,
    task: tokio::task::JoinHandle<()>,
}
impl HttpFixture {
    async fn start(app: Router) -> Self {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap(); });
        Self { base, task }
    }
}
impl Drop for HttpFixture { fn drop(&mut self) { self.task.abort(); } }

#[test]
fn metadata_requires_all_fields_and_exact_application_identity() {
    let metadata = crate::auth::authorization_server_metadata(ISSUER, Some("fixture-secret"));
    assert!(probe::validate_json(Contract::AuthorizationServer, &metadata, ISSUER, ""));
    for field in ["issuer", "authorization_endpoint", "token_endpoint", "response_types_supported",
        "grant_types_supported", "code_challenge_methods_supported", "token_endpoint_auth_methods_supported"] {
        for replacement in [Value::Null, json!("wrong"), json!([]), json!(["unimplemented"])] {
            let mut value = metadata.clone(); value[field] = replacement;
            assert!(!probe::validate_json(Contract::AuthorizationServer, &value, ISSUER, ""), "{field}");
        }
    }
    for value in [json!({}), json!([]), json!({"error":"canary-must-not-escape"})] {
        assert!(!probe::validate_json(Contract::AuthorizationServer, &value, ISSUER, ""));
    }
    assert!(!probe::validate_json(Contract::AuthorizationServer, &metadata, "https://other.example", ""));
}

#[test]
fn resource_validation_rejects_origin_other_host_and_actions_audience() {
    let resource = format!("{ISSUER}/mcp");
    let metadata = crate::auth::protected_resource_metadata(&resource, ISSUER);
    assert!(probe::validate_json(Contract::ProtectedResource, &metadata, ISSUER, &resource));
    for value in [json!(ISSUER), json!("https://other.example/mcp"), json!(format!("{ISSUER}/actions")), Value::Null] {
        let mut wrong = metadata.clone(); wrong["resource"] = value;
        assert!(!probe::validate_json(Contract::ProtectedResource, &wrong, ISSUER, &resource));
    }
    for field in ["authorization_servers", "bearer_methods_supported"] {
        let mut wrong = metadata.clone(); wrong[field] = json!([]);
        assert!(!probe::validate_json(Contract::ProtectedResource, &wrong, ISSUER, &resource));
    }
}

#[test]
fn challenge_is_parsed_not_matched_as_an_arbitrary_substring() {
    let url = format!("{ISSUER}/.well-known/oauth-protected-resource/mcp");
    let valid = format!("Bearer resource_metadata=\"{url}\", scope=\"mcp\"");
    assert!(probe::valid_challenge(&valid, &url));
    assert!(probe::valid_challenge(&valid.replacen("Bearer", "bearer", 1), &url));
    for value in [format!("Basic {valid}"), format!("{valid}, scope=\"mcp\""),
        format!("{valid}, resource_metadata=\"{url}\""), valid.replace("scope=\"mcp\"", "scope=\"admin\""),
        valid.replace("/mcp\"", "/other\""), format!("{valid}\r\n"), "x".repeat(4097)] {
        assert!(!probe::valid_challenge(&value, &url));
    }
}

#[test]
fn probe_destinations_disallow_credentials_fragments_paths_and_public_http() {
    for url in [ISSUER, "https://example.com:8443", "http://127.0.0.1:1234", "http://[::1]:1234"] {
        assert!(probe::valid_origin(url), "{url}");
    }
    for url in ["", "file:///tmp/canary", "http://example.com", "https://user:canary@example.com",
        "https://example.com?token=canary", "https://example.com/#canary", "https://example.com/mcp"] {
        assert!(!probe::valid_origin(url));
    }
}

#[tokio::test]
async fn http_404_html_empty_json_and_remote_errors_are_never_success() {
    let fixture = HttpFixture::start(Router::new()
        .route("/missing", get(|| async { (StatusCode::NOT_FOUND, Json(json!({}))) }))
        .route("/disabled", get(|| async { (StatusCode::NOT_FOUND, Json(json!({"error":"OAuth not configured"}))) }))
        .route("/frp", get(|| async { (StatusCode::NOT_FOUND, "<html>Powered by frp: not found canary-private</html>") }))
        .route("/html", get(|| async { "<html>canary-secret</html>" }))
        .route("/empty", get(|| async { Json(json!({})) }))
        .route("/bad", get(|| async { ([("content-type", "application/json")], "canary-invalid-json") }))
    ).await;
    for (path, expected) in [("/missing","http_error"), ("/disabled","oauth_not_configured"),
        ("/frp","frp_route_not_found"), ("/html","non_json_response"),
        ("/empty","metadata_or_identity_mismatch"), ("/bad","invalid_json")] {
        let result = probe::check(&probe::client().unwrap(), &fixture.base, path, Contract::AuthorizationServer, ISSUER, "").await;
        assert!(!result.ok, "{path}"); assert_eq!(result.code, expected);
        assert!(!result.detail().contains("canary"));
    }
}

#[tokio::test]
async fn redirect_does_not_fetch_destination_or_send_credentials() {
    let hits = Arc::new(AtomicUsize::new(0)); let seen = hits.clone();
    let destination = HttpFixture::start(Router::new().fallback(move || {
        let seen = seen.clone(); async move { seen.fetch_add(1, Ordering::SeqCst); Json(json!({})) }
    })).await;
    let url = destination.base.clone();
    let fixture = HttpFixture::start(Router::new().fallback(move |headers: axum::http::HeaderMap| {
        let url = url.clone(); async move {
            assert!(!headers.contains_key("authorization"));
            assert!(!headers.contains_key("cookie"));
            (StatusCode::FOUND, [("location", url)], "canary-location").into_response()
        }
    })).await;
    let result = probe::check(&probe::client().unwrap(), &fixture.base, "/", Contract::Mcp, ISSUER, "").await;
    assert_eq!(result.code, "redirect_rejected"); assert_eq!(hits.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn oversized_content_length_is_rejected_without_echoing_the_body() {
    let fixture = HttpFixture::start(Router::new().fallback(|| async {
        ([("content-type", "application/json")], "X".repeat(probe::MAX_METADATA_BYTES + 1))
    })).await;
    let result = probe::check(&probe::client().unwrap(), &fixture.base, "/", Contract::Mcp, ISSUER, "").await;
    assert_eq!(result.code, "response_too_large");
}

#[tokio::test]
async fn oversized_chunked_body_is_also_bounded() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = [0; 4096]; let _ = socket.read(&mut request).await;
        let mut wire = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n".to_vec();
        for _ in 0..3 { wire.extend_from_slice(b"8000\r\n"); wire.extend(vec![b'X'; 32768]); wire.extend_from_slice(b"\r\n"); }
        wire.extend_from_slice(b"0\r\n\r\n"); let _ = socket.write_all(&wire).await;
    });
    let result = probe::check(&probe::client().unwrap(), &base, "/", Contract::Mcp, ISSUER, "").await;
    task.await.unwrap(); assert_eq!(result.code, "response_too_large");
}

#[tokio::test]
async fn response_timeout_is_bounded_and_sanitized() {
    let fixture = HttpFixture::start(Router::new().fallback(|| async {
        tokio::time::sleep(probe::TIMEOUT + Duration::from_secs(2)).await; Json(json!({}))
    })).await;
    let start = Instant::now();
    let result = probe::check(&probe::client().unwrap(), &fixture.base, "/", Contract::Mcp, ISSUER, "").await;
    assert_eq!(result.code, "timeout"); assert!(start.elapsed() < probe::TIMEOUT + Duration::from_secs(4));
}

#[tokio::test]
async fn stopped_services_are_not_misreported_as_pass_or_oauth_failure() {
    let profile = WorkspaceProfile::new("fixture".into(), None);
    let items = run_health_checks(&profile, &HealthRuntime::default()).await;
    assert!(!items.is_empty()); assert!(items.iter().all(|item| item.skipped && !item.ok));
    assert!(items.iter().any(|item| item.label.contains("Actions")));
}

#[tokio::test]
async fn local_mcp_discovery_passes_while_proxy_metadata_failure_is_distinguished() {
    let proxy = HttpFixture::start(Router::new().route("/mcp", get(|| async { Json(json!({
        "name":"coding-tools-mcp", "version":env!("CARGO_PKG_VERSION"), "protocolVersion":"2025-06-18"
    })) }))).await;
    let root = tempfile::tempdir().unwrap();
    let port = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let id = uuid::Uuid::new_v4().to_string();
    let (stop, task) = crate::mcp::spawn_listener_with_origin(port, root.path().into(), id,
        AuthConfig::default(), proxy.base.clone().into(), Some("fixture-secret".into()),
        Some("fixture-password".into()), Some("fixture-signing".into()), RuntimeConfig::default()).unwrap();
    let mut profile = WorkspaceProfile::new(root.path().display().to_string(), None);
    profile.runtime.local_port = port;
    // A persisted stale URL must not replace the active runtime origin.
    profile.tunnel.public_url = "https://stale.example".into();
    let items = run_health_checks(&profile, &HealthRuntime {
        mcp_running: true, mcp_origin: proxy.base.clone(), ..Default::default()
    }).await;
    let _ = stop.send(()); task.abort();
    let local = items.iter().filter(|item| item.label.starts_with("本地 MCP OAuth")).collect::<Vec<_>>();
    assert_eq!(local.len(), 4); assert!(local.iter().all(|item| item.ok), "{items:?}");
    let public = items.iter().filter(|item| item.label.starts_with("公网 MCP OAuth")).collect::<Vec<_>>();
    assert_eq!(public.len(), 4); assert!(public.iter().all(|item| !item.ok && !item.skipped));
    assert!(public.iter().all(|item| item.hint.contains("本地 OAuth 发现链通过")));
    assert!(items.iter().filter(|item| item.label.contains("Actions")).all(|item| item.skipped));
    assert!(!serde_json::to_string(&items).unwrap().contains("fixture-secret"));
}

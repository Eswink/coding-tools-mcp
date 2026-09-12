//! Reproduce public metadata failures without credentials or external network.
use axum::{http::StatusCode, routing::get, Json, Router};
use serde_json::json;
use super::{probe::{self, Contract}, run_health_checks, HealthRuntime};
use crate::workspace::{AuthConfig, RuntimeConfig, WorkspaceProfile};

const ISSUER: &str = "https://route-fixture.example";
const METADATA: &str = "/.well-known/oauth-authorization-server";

struct Fixture { base: String, task: tokio::task::JoinHandle<()> }
impl Fixture {
    async fn start(router: Router) -> Self {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, router).await.unwrap(); });
        Self { base, task }
    }
}
impl Drop for Fixture { fn drop(&mut self) { self.task.abort(); } }

#[tokio::test]
async fn nginx_discovery_404_is_classified_as_a_route_failure() {
    let f = Fixture::start(Router::new().fallback(|| async {
        (StatusCode::NOT_FOUND, [("content-type", "text/html"), ("server", "nginx/1.24.0")],
            "<html>404 canary-response-secret</html>")
    })).await;
    for path in [METADATA, "/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"] {
        let result = probe::check(&probe::client().unwrap(), &f.base, path,
            Contract::AuthorizationServer, ISSUER, "").await;
        assert_eq!(result.code, "nginx_discovery_route_not_found");
        assert_eq!(result.status, Some(404)); assert!(!result.ok);
        assert!(!result.detail().contains("canary"));
    }
}

#[tokio::test]
async fn header_hint_does_not_change_http_success_or_auth_contract() {
    for (status, mime, server, body, expected) in [
        (404, "text/html", "other", "<h1>not found</h1>", "discovery_route_not_found"),
        (404, "text/html", "pretend-nginx", "404", "discovery_route_not_found"),
        (200, "text/html", "nginx", "404", "non_json_response"),
        (403, "text/html", "nginx", "denied", "non_json_response"),
        (404, "application/json", "nginx", "{}", "http_error"),
        (404, "application/json", "nginx", "{\"error\":\"OAuth not configured\"}", "oauth_not_configured"),
        (404, "text/html", "nginx", "{\"error\":\"OAuth not configured\"}", "nginx_discovery_route_not_found"),
        (404, "text/html", "nginx", "Powered by frp: not found", "frp_route_not_found"),
    ] {
        let f = Fixture::start(Router::new().fallback(move || async move {
            (StatusCode::from_u16(status).unwrap(), [("content-type", mime), ("server", server)], body)
        })).await;
        let result = probe::check(&probe::client().unwrap(), &f.base, METADATA,
            Contract::AuthorizationServer, ISSUER, "").await;
        assert_eq!(result.code, expected); assert!(!result.ok);
    }
}

#[tokio::test]
async fn unrelated_paths_are_not_reported_as_missing_discovery() {
    let f = Fixture::start(Router::new().fallback(|| async {
        (StatusCode::NOT_FOUND, [("content-type", "text/html"), ("server", "nginx")], "404")
    })).await;
    for (path, contract) in [("/mcp", Contract::Mcp), ("/openapi.json", Contract::OpenApi),
        ("/unrelated", Contract::AuthorizationServer)] {
        assert_eq!(probe::check(&probe::client().unwrap(), &f.base, path, contract, ISSUER, "")
            .await.code, "non_json_response");
    }
}

#[tokio::test]
async fn invalid_origin_never_appears_in_serialized_request_or_hint() {
    let mut profile = WorkspaceProfile::new("fixture".into(), None);
    profile.runtime.local_port = 1;
    let items = run_health_checks(&profile, &HealthRuntime {
        mcp_running: true, mcp_origin: "https://user:canary-origin-secret@example.com?token=canary".into(),
        ..Default::default()
    }).await;
    let text = serde_json::to_string(&items).unwrap();
    assert!(!text.contains("canary"));
    assert!(items.iter().filter(|i| i.label.starts_with("公网 MCP OAuth"))
        .all(|i| i.code == "invalid_or_missing_origin" && i.request.is_empty() && !i.ok));
}

#[tokio::test]
async fn healthy_challenge_and_missing_documents_produce_targeted_hints() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let challenge = format!("Bearer resource_metadata=\"{base}/.well-known/oauth-protected-resource/mcp\", scope=\"mcp\"");
    let router = Router::new().route("/mcp", get(|| async {
        Json(json!({"name":"coding-tools-mcp", "version":env!("CARGO_PKG_VERSION"),
            "protocolVersion":"2025-06-18"}))
    }).post(move || {
        let c = challenge.clone(); async move { (StatusCode::UNAUTHORIZED, [("www-authenticate", c)]) }
    })).fallback(|| async { (StatusCode::NOT_FOUND,
        [("server", "nginx"), ("content-type", "text/html")], "canary-route-body") });
    let task = tokio::spawn(async move { axum::serve(listener, router).await.unwrap(); });
    let gateway = Fixture { base, task };
    let root = tempfile::tempdir().unwrap();
    let port = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let (stop, task) = crate::mcp::spawn_listener_with_origin(port, root.path().into(),
        uuid::Uuid::new_v4().to_string(), AuthConfig::default(), gateway.base.clone().into(),
        Some("fixture-secret".into()), Some("fixture-password".into()), Some("fixture-signing".into()),
        RuntimeConfig::default()).unwrap();
    let mut profile = WorkspaceProfile::new(root.path().display().to_string(), None);
    profile.runtime.local_port = port;
    let items = run_health_checks(&profile, &HealthRuntime {
        mcp_running: true, mcp_origin: gateway.base.clone(), ..Default::default()
    }).await;
    let _ = stop.send(()); task.abort();
    let public = items.iter().filter(|i| i.label.starts_with("公网 MCP OAuth")).collect::<Vec<_>>();
    assert_eq!(public.len(), 4);
    for item in &public[..3] {
        assert!(!item.ok); assert_eq!(item.code, "nginx_discovery_route_not_found");
        assert!(item.request.starts_with(&format!("GET {}/.well-known/", gateway.base)));
        assert!(item.hint.contains("401 挑战也通过"));
        assert!(!item.detail.contains("canary"));
    }
    assert!(public[3].ok); assert_eq!(public[3].request, format!("POST {}/mcp", gateway.base));
}

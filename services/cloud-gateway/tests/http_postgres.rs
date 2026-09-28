mod common;
use axum::{
    body::Body,
    http::{header, Request, StatusCode},
};
use coding_tools_cloud_gateway::http::identity_routes;
use common::{identity, Fixture};
use http_body_util::BodyExt;
use tower::ServiceExt;
use uuid::Uuid;
fn req(path: &str, body: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(path)
        .header("host", identity().authority())
        .header(header::CONTENT_TYPE, "application/x-www-form-urlencoded")
        .body(Body::from(body.to_owned()))
        .unwrap()
}
#[tokio::test]
async fn discovery_is_stable_without_any_enrolled_agent() {
    let f = Fixture::new().await;
    for (path, expected) in [
        (
            identity().resource_metadata_path(),
            identity().resource_metadata(),
        ),
        (
            identity().server_metadata_path(),
            identity().server_metadata(),
        ),
    ] {
        let r = identity_routes(f.store.clone())
            .oneshot(
                Request::builder()
                    .uri(&path)
                    .header("host", identity().authority())
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(r.status(), StatusCode::OK);
        assert_eq!(r.headers()[header::CACHE_CONTROL], "no-store");
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(
                &r.into_body().collect().await.unwrap().to_bytes()
            )
            .unwrap(),
            expected
        );
    }
}
#[tokio::test]
async fn refresh_over_http_when_access_expired_and_no_agent_exists() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    sqlx::query("UPDATE ctm_access_tokens SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    let body = url::form_urlencoded::Serializer::new(String::new())
        .extend_pairs([
            ("grant_type", "refresh_token"),
            ("client_id", "public-client"),
            ("refresh_token", t.refresh_token.expose()),
            ("resource", identity().resource().as_str()),
        ])
        .finish();
    let r = identity_routes(f.store.clone())
        .oneshot(req(&identity().token_path(), &body))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    assert!(!r.headers().contains_key(header::WWW_AUTHENTICATE));
    let v: serde_json::Value =
        serde_json::from_slice(&r.into_body().collect().await.unwrap().to_bytes()).unwrap();
    assert_eq!(v["token_type"], "Bearer");
    assert!(f
        .store
        .authenticate_access(v["access_token"].as_str().unwrap())
        .await
        .is_ok());
}
#[tokio::test]
async fn invalid_refresh_is_oauth_error_not_workspace_offline() {
    let f = Fixture::new().await;
    let body = format!(
        "grant_type=refresh_token&client_id=public-client&resource={}&refresh_token={}",
        identity().resource(),
        "a".repeat(43)
    );
    let r = identity_routes(f.store)
        .oneshot(req(&identity().token_path(), &body))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::BAD_REQUEST);
    let v: serde_json::Value =
        serde_json::from_slice(&r.into_body().collect().await.unwrap().to_bytes()).unwrap();
    assert_eq!(v["error"], "invalid_grant");
}
#[tokio::test]
async fn duplicate_unknown_and_malformed_fields_are_rejected() {
    let f = Fixture::new().await;
    for body in [
        "client_id=a&client_id=b",
        "client_id=bad%GG",
        "subject=forged",
        "grant_type=refresh_token&code=x",
        "client_id=x&scope=root",
    ] {
        let r = identity_routes(f.store.clone())
            .oneshot(req(&identity().token_path(), body))
            .await
            .unwrap();
        assert_eq!(r.status(), StatusCode::BAD_REQUEST);
        assert_eq!(r.headers()[header::CACHE_CONTROL], "no-store");
    }
}
#[tokio::test]
async fn host_origin_and_duplicate_headers_fail_closed() {
    let f = Fixture::new().await;
    for (name, value, append) in [
        ("host", "foreign.invalid", false),
        ("origin", "https://foreign.invalid", false),
        ("origin", "null", false),
        ("origin", "https://gateway.example.invalid/path", false),
        ("host", "gateway.example.invalid", true),
        ("content-type", "application/json", true),
    ] {
        let mut r = req(&identity().token_path(), "");
        if append {
            r.headers_mut().append(name, value.parse().unwrap());
        } else {
            r.headers_mut().insert(name, value.parse().unwrap());
        }
        let r = identity_routes(f.store.clone()).oneshot(r).await.unwrap();
        assert_eq!(r.status(), StatusCode::FORBIDDEN, "{name}");
    }
}
#[tokio::test]
async fn forwarded_headers_cannot_change_public_identity() {
    let f = Fixture::new().await;
    let mut r = Request::builder()
        .uri(identity().resource_metadata_path())
        .header("host", identity().authority())
        .body(Body::empty())
        .unwrap();
    r.headers_mut()
        .insert("x-forwarded-host", "attacker.invalid".parse().unwrap());
    r.headers_mut().insert(
        "forwarded",
        "host=attacker.invalid;proto=http".parse().unwrap(),
    );
    let r = identity_routes(f.store).oneshot(r).await.unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    let v: serde_json::Value =
        serde_json::from_slice(&r.into_body().collect().await.unwrap().to_bytes()).unwrap();
    assert_eq!(v["resource"], identity().resource());
}
#[tokio::test]
async fn content_type_and_body_limit_are_enforced() {
    let f = Fixture::new().await;
    let mut r = req(&identity().token_path(), "{}");
    r.headers_mut()
        .insert(header::CONTENT_TYPE, "application/json".parse().unwrap());
    assert_eq!(
        identity_routes(f.store.clone())
            .oneshot(r)
            .await
            .unwrap()
            .status(),
        StatusCode::UNSUPPORTED_MEDIA_TYPE
    );
    let response = identity_routes(f.store)
        .oneshot(req(&identity().token_path(), &"a".repeat(8193)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
}
#[tokio::test]
async fn trusted_issuance_and_invitation_apis_are_not_http_routes() {
    let f = Fixture::new().await;
    // The browser entry now exists as GET, but POST cannot bypass login/consent.
    let response = identity_routes(f.store.clone())
        .oneshot(req("/coding-tools/oauth/authorize", "subject=forged"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    assert!(!response.headers().contains_key(header::LOCATION));
    let codes: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_codes")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(codes, 0);
    for path in [
        "/coding-tools/admin/issue-code",
        "/coding-tools/agents/enroll",
    ] {
        assert_eq!(
            identity_routes(f.store.clone())
                .oneshot(req(path, ""))
                .await
                .unwrap()
                .status(),
            StatusCode::NOT_FOUND
        );
    }
}
#[tokio::test]
async fn real_tcp_listener_returns_metadata_without_payload_logging() {
    use std::io::{Read, Write};
    let f = Fixture::new().await;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        axum::serve(listener, identity_routes(f.store))
            .await
            .unwrap()
    });
    let request = format!(
        "GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n",
        identity().resource_metadata_path(),
        identity().authority()
    );
    let bytes = tokio::task::spawn_blocking(move || {
        let mut c = std::net::TcpStream::connect(addr).unwrap();
        c.set_read_timeout(Some(std::time::Duration::from_secs(3)))
            .unwrap();
        c.write_all(request.as_bytes()).unwrap();
        let mut out = Vec::new();
        c.read_to_end(&mut out).unwrap();
        out
    })
    .await
    .unwrap();
    server.abort();
    let response = String::from_utf8(bytes).unwrap();
    assert!(response.starts_with("HTTP/1.1 200"));
    assert!(response.contains(&identity().resource()));
}

#[tokio::test]
async fn malformed_origins_are_not_normalized_into_trusted_origins() {
    let f = Fixture::new().await;
    for origin in [
        r"https:\gateway.example.invalid",
        r"https:\\gateway.example.invalid",
        "https:gateway.example.invalid",
        "https://gateway.example.invalid#",
    ] {
        let mut r = req(&identity().token_path(), "");
        r.headers_mut().insert("origin", origin.parse().unwrap());
        let r = identity_routes(f.store.clone()).oneshot(r).await.unwrap();
        assert_eq!(
            r.status(),
            StatusCode::FORBIDDEN,
            "malformed Origin {origin}"
        );
    }
}

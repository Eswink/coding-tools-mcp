//! Regression for ordinary HTML form Origin under the Fetch referrer algorithm.
//! No request-origin/CSRF validation is relaxed to make a browser form work.
mod browser_support;
#[allow(dead_code)]
mod common;
use browser_support::*;
use coding_tools_cloud_gateway::http::identity_routes;

#[tokio::test]
async fn form_pages_keep_origin_only_policy_through_outer_middleware() {
    let (fixture, _) = setup().await;
    let app = identity_routes(fixture.store);
    let begin = http_get(
        &app,
        &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
    )
    .await;
    assert_eq!(begin.headers()["referrer-policy"], "strict-origin");
    let (cookie, csrf, _) = page_parts(begin).await;
    let login = http_post(
        &app,
        "/coding-tools/oauth/login",
        &cookie,
        form(&[("csrf", &csrf), ("password", PASSWORD)]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(login.status(), 200);
    assert_eq!(login.headers()["referrer-policy"], "strict-origin");
    assert_eq!(login.headers()["cache-control"], "no-store");
}

#[tokio::test]
async fn metadata_errors_and_consent_redirects_keep_no_referrer() {
    let (fixture, _) = setup().await;
    let identity = fixture.store.identity().clone();
    let app = identity_routes(fixture.store);
    for uri in [
        identity.resource_metadata_path(),
        identity.server_metadata_path(),
        "/coding-tools/oauth/authorize".to_owned(),
    ] {
        let response = http_get(&app, &uri).await;
        assert_eq!(response.headers()["referrer-policy"], "no-referrer");
    }
    for decision in ["allow", "deny"] {
        let (cookie, csrf, _) = http_login(&app).await;
        let redirect = http_post(
            &app,
            "/coding-tools/oauth/consent",
            &cookie,
            form(&[("csrf", &csrf), ("decision", decision)]),
            Some("https://gateway.example.invalid"),
        )
        .await;
        assert_eq!(redirect.status(), 303);
        assert_eq!(redirect.headers()["referrer-policy"], "no-referrer");
        assert_eq!(redirect.headers()["cache-control"], "no-store");
    }
}

#[tokio::test]
async fn form_policy_never_authorizes_missing_null_or_foreign_origin() {
    let (fixture, _) = setup().await;
    let app = identity_routes(fixture.store.clone());
    let (cookie, csrf, _) = page_parts(
        http_get(
            &app,
            &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
        )
        .await,
    )
    .await;
    for origin in [None, Some("null"), Some("https://foreign.invalid")] {
        let response = http_post(
            &app,
            "/coding-tools/oauth/login",
            &cookie,
            form(&[("csrf", &csrf), ("password", PASSWORD)]),
            origin,
        )
        .await;
        assert!(response.status().is_client_error());
        assert!(response.headers().get("location").is_none());
        assert_eq!(response.headers()["referrer-policy"], "no-referrer");
    }
    assert_eq!(codes(&fixture).await, 0);
}

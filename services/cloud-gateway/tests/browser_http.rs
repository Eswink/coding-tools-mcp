#[allow(dead_code)]
mod common;
use axum::{body::Body, http::Request};
use common::Fixture;
use tower::ServiceExt;

#[tokio::test]
async fn authorize_route_is_present_without_minting_a_code() {
    let fixture = Fixture::new().await;
    let response = coding_tools_cloud_gateway::http::identity_routes(fixture.store)
        .oneshot(
            Request::builder()
                .uri("/coding-tools/oauth/authorize")
                .header("host", "gateway.example.invalid")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    // The identity library previously advertised a missing authorization endpoint.
    assert_eq!(
        response.status(),
        400,
        "present route must reject malformed input, not 404"
    );
    assert!(response.headers().get("location").is_none());
}

mod browser_support;
use browser_support::*;
use coding_tools_cloud_gateway::{http::identity_routes, Secret};

#[tokio::test]
async fn full_http_owner_flow_exchanges_and_refreshes_while_agent_absent() {
    let (fixture, _) = setup().await;
    let app = identity_routes(fixture.store.clone());
    let (cookie, csrf, html) = http_login(&app).await;
    assert!(html.contains("does not approve any local workspace"));
    assert_eq!(codes(&fixture).await, 0);
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        form(&[("csrf", &csrf), ("decision", "allow")]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 303);
    assert!(r.headers()["set-cookie"]
        .to_str()
        .unwrap()
        .contains("Max-Age=0"));
    let location = Secret::new(r.headers()["location"].to_str().unwrap().into());
    let r = http_post(
        &app,
        "/coding-tools/oauth/token",
        "",
        form(&[
            ("grant_type", "authorization_code"),
            ("client_id", "public-client"),
            ("code", &code(&location)),
            ("code_verifier", &"a".repeat(43)),
            ("redirect_uri", REDIRECT),
            ("resource", &common::identity().resource()),
        ]),
        None,
    )
    .await;
    assert_eq!(r.status(), 200);
    let token: serde_json::Value = serde_json::from_str(&body(r).await).unwrap();
    let p = fixture
        .store
        .authenticate_access(token["access_token"].as_str().unwrap())
        .await
        .unwrap();
    assert_eq!(p.subject, OWNER);
    let r = http_post(
        &app,
        "/coding-tools/oauth/token",
        "",
        form(&[
            ("grant_type", "refresh_token"),
            ("client_id", "public-client"),
            ("refresh_token", token["refresh_token"].as_str().unwrap()),
            ("resource", &common::identity().resource()),
        ]),
        None,
    )
    .await;
    assert_eq!(r.status(), 200);
    assert_eq!(codes(&fixture).await, 1);
}
#[tokio::test]
async fn secure_cookie_headers_and_fixed_form_are_present() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store);
    let r = http_get(
        &app,
        &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
    )
    .await;
    let c = r.headers()["set-cookie"].to_str().unwrap();
    for flag in [
        "__Host-ctm-browser=",
        "Secure",
        "HttpOnly",
        "SameSite=Lax",
        "Path=/",
        "Max-Age=300",
    ] {
        assert!(c.contains(flag));
    }
    assert!(!c.contains("Domain="));
    assert_eq!(r.headers()["cache-control"], "no-store");
    assert_eq!(r.headers()["referrer-policy"], "no-referrer");
    assert_eq!(r.headers()["x-frame-options"], "DENY");
    let csp = r.headers()["content-security-policy"].to_str().unwrap();
    assert!(csp.contains("default-src 'none'"));
    assert!(csp.contains("form-action 'self' https://client.example.invalid"));
    let text = body(r).await;
    assert!(!text.contains("<script"));
    assert!(!text.contains(&request().state));
}
#[tokio::test]
async fn consent_requires_origin_csrf_and_current_rotated_browser_cookie() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = http_login(&app).await;
    for origin in [None, Some("https://foreign.invalid"), Some("null")] {
        let r = http_post(
            &app,
            "/coding-tools/oauth/consent",
            &cookie,
            form(&[("csrf", &csrf), ("decision", "allow")]),
            origin,
        )
        .await;
        assert!(r.status().is_client_error());
        assert!(r.headers().get("location").is_none());
    }
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        form(&[("csrf", "wrong"), ("decision", "allow")]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn login_itself_is_csrf_protected_and_does_not_issue_a_code() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = page_parts(
        http_get(
            &app,
            &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
        )
        .await,
    )
    .await;
    for origin in [None, Some("https://foreign.invalid")] {
        let r = http_post(
            &app,
            "/coding-tools/oauth/login",
            &cookie,
            form(&[("csrf", &csrf), ("password", PASSWORD)]),
            origin,
        )
        .await;
        assert!(r.status().is_client_error());
        assert!(r.headers().get("location").is_none());
    }
    let r = http_post(
        &app,
        "/coding-tools/oauth/login",
        &cookie,
        form(&[("csrf", "wrong"), ("password", PASSWORD)]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn duplicates_unknown_fields_and_invalid_encoding_are_rejected() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = http_login(&app).await;
    let good = form(&[("csrf", &csrf), ("decision", "allow")]);
    for raw in [
        format!("{good}&decision=deny"),
        format!("{good}&subject=attacker"),
        format!("{good}&csrf=other"),
        "csrf=%ZZ&decision=allow".into(),
        "csrf=%FF&decision=allow".into(),
        "csrf=%00&decision=allow".into(),
    ] {
        let r = http_post(
            &app,
            "/coding-tools/oauth/consent",
            &cookie,
            raw,
            Some("https://gateway.example.invalid"),
        )
        .await;
        assert_eq!(r.status(), 400);
    }
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &format!("{cookie}; {cookie}"),
        good,
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn duplicate_cookie_headers_and_cross_site_metadata_are_rejected() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = http_login(&app).await;
    for duplicate_cookie in [true, false] {
        let mut b = Request::builder()
            .method("POST")
            .uri("/coding-tools/oauth/consent")
            .header("host", "gateway.example.invalid")
            .header("origin", "https://gateway.example.invalid")
            .header("content-type", "application/x-www-form-urlencoded")
            .header("cookie", &cookie);
        if duplicate_cookie {
            b = b.header("cookie", &cookie);
        } else {
            b = b.header("sec-fetch-site", "cross-site");
        }
        let r = app
            .clone()
            .oneshot(
                b.body(Body::from(form(&[("csrf", &csrf), ("decision", "allow")])))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(r.status(), 400);
    }
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn bad_redirect_or_unknown_client_never_causes_external_redirect() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    for q in [
        authorize_query().replace("public-client", "unknown-client"),
        authorize_query().replace("client.example.invalid", "evil.example.invalid"),
        format!("{}&client_id=public-client", authorize_query()),
        authorize_query().replace("S256", "plain"),
    ] {
        let r = http_get(&app, &format!("/coding-tools/oauth/authorize?{q}")).await;
        assert_eq!(r.status(), 400);
        assert!(r.headers().get("location").is_none());
    }
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn denial_and_replayed_submission_never_create_a_code() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = http_login(&app).await;
    let raw = form(&[("csrf", &csrf), ("decision", "deny")]);
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        raw.clone(),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 303);
    let loc = url::Url::parse(r.headers()["location"].to_str().unwrap()).unwrap();
    assert!(loc
        .query_pairs()
        .any(|(k, v)| k == "error" && v == "access_denied"));
    assert!(!loc.query_pairs().any(|(k, _)| k == "code"));
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        raw,
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn consent_post_query_and_oversized_body_are_rejected() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = http_login(&app).await;
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent?decision=allow",
        &cookie,
        form(&[("csrf", &csrf), ("decision", "allow")]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        "x".repeat(9000),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 413);
    assert_eq!(codes(&f).await, 0);
}
#[tokio::test]
async fn owner_absence_is_not_silent_signup() {
    let f = Fixture::new().await;
    let app = identity_routes(f.store.clone());
    let r = http_get(
        &app,
        &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
    )
    .await;
    assert_eq!(r.status(), 503);
    assert!(r.headers().get("location").is_none());
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_owner")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(n, 0);
}

#[tokio::test]
async fn registered_display_values_are_html_escaped() {
    let (f, _) = setup().await;
    let redirect = "https://client.example.invalid/callback?hint=<svg/onload=alert(1)>";
    f.store
        .register_client("display-client", redirect, None)
        .await
        .unwrap();
    let app = identity_routes(f.store);
    let r = request();
    let q = form(&[
        ("response_type", "code"),
        ("scope", "mcp"),
        ("client_id", "display-client"),
        ("redirect_uri", redirect),
        ("resource", &r.resource),
        ("code_challenge", &r.code_challenge),
        ("code_challenge_method", "S256"),
        ("state", &r.state),
    ]);
    let response = http_get(&app, &format!("/coding-tools/oauth/authorize?{q}")).await;
    assert_eq!(response.status(), 200);
    let text = body(response).await;
    assert!(!text.contains("<svg"));
    assert!(text.contains("&lt;svg"));
}
#[tokio::test]
async fn preauth_cookie_is_unusable_after_successful_login() {
    let (f, _) = setup().await;
    let app = identity_routes(f.store.clone());
    let (cookie, csrf, _) = page_parts(
        http_get(
            &app,
            &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
        )
        .await,
    )
    .await;
    let (new_cookie, new_csrf, _) = page_parts(
        http_post(
            &app,
            "/coding-tools/oauth/login",
            &cookie,
            form(&[("csrf", &csrf), ("password", PASSWORD)]),
            Some("https://gateway.example.invalid"),
        )
        .await,
    )
    .await;
    assert!(cookie != new_cookie);
    assert!(csrf != new_csrf);
    let r = http_post(
        &app,
        "/coding-tools/oauth/consent",
        &cookie,
        form(&[("csrf", &csrf), ("decision", "allow")]),
        Some("https://gateway.example.invalid"),
    )
    .await;
    assert_eq!(r.status(), 400);
    assert_eq!(codes(&f).await, 0);
}

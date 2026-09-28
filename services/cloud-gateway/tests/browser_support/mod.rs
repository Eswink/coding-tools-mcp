#![allow(dead_code)]
use coding_tools_cloud_gateway::{
    browser::{BrowserAuth, BrowserPage, BrowserRequest},
    crypto::pkce_challenge,
    Secret,
};
use uuid::Uuid;
pub const PASSWORD: &str = "owner-password-canary-not-production";
pub const REDIRECT: &str = "https://client.example.invalid/callback";
pub const OWNER: Uuid = Uuid::from_u128(2);
pub fn request() -> BrowserRequest {
    BrowserRequest {
        client_id: "public-client".into(),
        redirect_uri: REDIRECT.into(),
        resource: crate::common::identity().resource(),
        code_challenge: pkce_challenge(&"a".repeat(43)).unwrap(),
        state: "state + / & 中文 <private>".into(),
    }
}
pub async fn setup() -> (crate::common::Fixture, BrowserAuth) {
    let fixture = crate::common::Fixture::new().await;
    let auth = BrowserAuth::new(fixture.store.clone());
    auth.provision_owner(OWNER, Secret::new(PASSWORD.into()))
        .await
        .unwrap();
    (fixture, auth)
}
pub async fn logged_in(auth: &BrowserAuth) -> BrowserPage {
    let p = auth.begin(request()).await.unwrap();
    auth.login(
        p.cookie.expose(),
        p.csrf.expose(),
        Secret::new(PASSWORD.into()),
    )
    .await
    .unwrap()
}
pub fn code(location: &Secret) -> String {
    url::Url::parse(location.expose())
        .unwrap()
        .query_pairs()
        .find(|(k, _)| k == "code")
        .unwrap()
        .1
        .into_owned()
}
pub async fn codes(f: &crate::common::Fixture) -> i64 {
    sqlx::query_scalar("SELECT count(*) FROM ctm_codes")
        .fetch_one(&f.pool)
        .await
        .unwrap()
}

pub fn form(pairs: &[(&str, &str)]) -> String {
    url::form_urlencoded::Serializer::new(String::new())
        .extend_pairs(pairs.iter().copied())
        .finish()
}
pub fn authorize_query() -> String {
    let r = request();
    form(&[
        ("response_type", "code"),
        ("scope", "mcp"),
        ("client_id", &r.client_id),
        ("redirect_uri", &r.redirect_uri),
        ("resource", &r.resource),
        ("code_challenge", &r.code_challenge),
        ("code_challenge_method", "S256"),
        ("state", &r.state),
    ])
}
pub async fn http_get(app: &axum::Router, uri: &str) -> axum::response::Response {
    use tower::ServiceExt;
    app.clone()
        .oneshot(
            axum::http::Request::builder()
                .uri(uri)
                .header("host", "gateway.example.invalid")
                .body(axum::body::Body::empty())
                .unwrap(),
        )
        .await
        .unwrap()
}
pub async fn http_post(
    app: &axum::Router,
    path: &str,
    cookie: &str,
    body: String,
    origin: Option<&str>,
) -> axum::response::Response {
    use tower::ServiceExt;
    let mut b = axum::http::Request::builder()
        .method("POST")
        .uri(path)
        .header("host", "gateway.example.invalid")
        .header("content-type", "application/x-www-form-urlencoded");
    if !cookie.is_empty() {
        b = b.header("cookie", cookie);
    }
    if let Some(origin) = origin {
        b = b.header("origin", origin);
    }
    app.clone()
        .oneshot(b.body(axum::body::Body::from(body)).unwrap())
        .await
        .unwrap()
}
pub async fn body(response: axum::response::Response) -> String {
    use http_body_util::BodyExt;
    String::from_utf8(
        response
            .into_body()
            .collect()
            .await
            .unwrap()
            .to_bytes()
            .to_vec(),
    )
    .unwrap()
}
pub async fn page_parts(response: axum::response::Response) -> (String, String, String) {
    assert_eq!(response.status(), 200);
    let cookie = response.headers()["set-cookie"]
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_owned();
    let html = body(response).await;
    let csrf = html
        .split("name=csrf value=\"")
        .nth(1)
        .unwrap()
        .split('"')
        .next()
        .unwrap()
        .to_owned();
    (cookie, csrf, html)
}
pub async fn http_login(app: &axum::Router) -> (String, String, String) {
    let (cookie, csrf, _) = page_parts(
        http_get(
            app,
            &format!("/coding-tools/oauth/authorize?{}", authorize_query()),
        )
        .await,
    )
    .await;
    page_parts(
        http_post(
            app,
            "/coding-tools/oauth/login",
            &cookie,
            form(&[("csrf", &csrf), ("password", PASSWORD)]),
            Some("https://gateway.example.invalid"),
        )
        .await,
    )
    .await
}

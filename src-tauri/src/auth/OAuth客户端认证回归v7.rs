//! Real token-exchange implementation; no production token or external callback.
use super::*;
use axum::body::to_bytes;
use base64::engine::general_purpose::STANDARD;
use serde_json::Value;

const ORIGIN: &str = "https://client-auth.example";
const CALLBACK: &str = "https://chatgpt.com/connector/oauth/test";
const VERIFIER: &str = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";
fn runtime() -> OAuthRuntime {
    OAuthRuntime::new(ORIGIN.into(), "client".into(), Some("secret".into()),
        "password".into(), "test-only-client-auth-v7-signing-key".into())
        .with_redirect_uri(CALLBACK.into())
}
fn code(oauth: &OAuthRuntime) -> String {
    let response = authorize_post(oauth, AuthorizeForm {
        client_id: oauth.client_id.clone(), redirect_uri: CALLBACK.into(),
        code_challenge: URL_SAFE_NO_PAD.encode(Sha256::digest(VERIFIER.as_bytes())),
        code_challenge_method: "S256".into(), state: "test-state".into(),
        resource: ORIGIN.into(), scope: "mcp".into(), password: "password".into(),
    }, ORIGIN);
    assert_eq!(response.status(), StatusCode::SEE_OTHER);
    oauth.pending.lock().unwrap().keys().next().unwrap().clone()
}
fn form(code: &str) -> TokenForm {
    TokenForm { grant_type: "authorization_code".into(), code: code.into(),
        redirect_uri: CALLBACK.into(), code_verifier: VERIFIER.into(), resource: ORIGIN.into(),
        ..Default::default() }
}
fn basic(text: &str) -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(AUTHORIZATION, format!("Basic {}", STANDARD.encode(text)).parse().unwrap());
    headers
}
async fn body(response: Response) -> Value {
    serde_json::from_slice(&to_bytes(response.into_body(), 32768).await.unwrap()).unwrap()
}

#[tokio::test]
async fn basic_only_client_id_can_be_absent_from_form() {
    let oauth = runtime(); let code = code(&oauth);
    let parsed: TokenForm = serde_json::from_value(json!({
        "grant_type":"authorization_code", "code":code, "redirect_uri":CALLBACK,
        "code_verifier":VERIFIER, "resource":ORIGIN,
    })).unwrap();
    assert!(parsed.client_id.is_empty());
    let response = token_exchange(&oauth, &basic("client:secret"), parsed, ORIGIN);
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()[axum::http::header::CACHE_CONTROL], "no-store");
    let token = body(response).await["access_token"].as_str().unwrap().to_string();
    assert!(oauth.verify_access_token(&token, ORIGIN));
    assert_eq!(token_exchange(&oauth, &basic("client:secret"), form(&code), ORIGIN).status(), StatusCode::BAD_REQUEST);
}

#[test]
fn post_and_public_pkce_clients_remain_supported() {
    let oauth = runtime(); let code = code(&oauth);
    let mut form = form(&code); form.client_id = "client".into(); form.client_secret = "secret".into();
    assert_eq!(token_exchange(&oauth, &HeaderMap::new(), form, ORIGIN).status(), StatusCode::OK);
    let mut oauth = runtime(); oauth.client_secret = None; let code = self::code(&oauth);
    let mut form = self::form(&code); form.client_id = "client".into();
    assert_eq!(token_exchange(&oauth, &HeaderMap::new(), form, ORIGIN).status(), StatusCode::OK);
}

#[tokio::test]
async fn mixed_methods_conflicting_identity_and_bad_headers_never_fall_back() {
    let oauth = runtime(); let code = code(&oauth);
    for bad in ["Bearer wrong", "Basic ???", "Basic Y2xpZW50", "", "Basic "] {
        let mut headers = HeaderMap::new(); headers.insert(AUTHORIZATION, bad.parse().unwrap());
        let mut form = form(&code); form.client_id = "client".into(); form.client_secret = "secret".into();
        let response = token_exchange(&oauth, &headers, form, ORIGIN);
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(response.headers()[axum::http::header::CACHE_CONTROL], "no-store");
        assert!(response.headers().contains_key(axum::http::header::WWW_AUTHENTICATE));
        assert_eq!(body(response).await["error"], "invalid_client");
    }
    for (id, secret) in [("different", ""), ("client", "secret")] {
        let mut form = form(&code); form.client_id = id.into(); form.client_secret = secret.into();
        assert_eq!(token_exchange(&oauth, &basic("client:secret"), form, ORIGIN).status(), StatusCode::UNAUTHORIZED);
    }
    let mut headers = basic("client:secret"); headers.append(AUTHORIZATION, headers[AUTHORIZATION].clone());
    assert_eq!(token_exchange(&oauth, &headers, form(&code), ORIGIN).status(), StatusCode::UNAUTHORIZED);
    // Client authentication fails before a valid authorization code is consumed.
    assert_eq!(token_exchange(&oauth, &basic("client:wrong"), form(&code), ORIGIN).status(), StatusCode::UNAUTHORIZED);
    assert_eq!(token_exchange(&oauth, &basic("client:secret"), form(&code), ORIGIN).status(), StatusCode::OK);
}

#[test]
fn basic_decodes_form_components_and_case_insensitive_scheme() {
    let mut headers = basic("client%3Aid:secret%2Bwith+space%3A%E4%B8%AD");
    let value = headers[AUTHORIZATION].to_str().unwrap().replacen("Basic", "bAsIc", 1);
    headers.insert(AUTHORIZATION, value.parse().unwrap());
    let mut form = TokenForm::default(); client_auth::resolve(&headers, &mut form).unwrap();
    assert_eq!(form.client_id, "client:id"); assert_eq!(form.client_secret, "secret+with space:中");
    // Duplicate identity, unlike a second authentication method, is unambiguous.
    let mut form = TokenForm { client_id:"client:id".into(), ..Default::default() };
    assert!(client_auth::resolve(&headers, &mut form).is_ok());
}

#[test]
fn malformed_encoding_controls_and_oversized_credentials_are_rejected() {
    for header in ["Basic ???", "Basic Y2xpZW50", "Bearer wrong", "", "Basic "] {
        let mut headers = HeaderMap::new(); headers.insert(AUTHORIZATION, header.parse().unwrap());
        assert!(client_auth::resolve(&headers, &mut TokenForm::default()).is_err());
    }
    for value in ["client:bad%", "client:bad%ZZ", "client:%FF", "client:%00", "client:%0A", ":secret"] {
        assert!(client_auth::resolve(&basic(value), &mut TokenForm::default()).is_err(), "{value}");
    }
    for value in [format!("{}:secret", "x".repeat(257)), format!("client:{}", "x".repeat(2049)), "x".repeat(9000)] {
        assert!(client_auth::resolve(&basic(&value), &mut TokenForm::default()).is_err());
    }
    for (id, secret) in [("client\0", "secret"), ("client", "secret\n")] {
        let mut form = TokenForm { client_id:id.into(),client_secret:secret.into(),..Default::default() };
        assert!(client_auth::resolve(&HeaderMap::new(), &mut form).is_err());
    }
}

#[test]
fn concurrent_exchange_can_consume_code_only_once() {
    let oauth = runtime(); let code = code(&oauth);
    let barrier = Arc::new(std::sync::Barrier::new(8));
    let threads: Vec<_> = (0..8).map(|_| {
        let oauth = oauth.clone(); let code = code.clone(); let barrier = barrier.clone();
        std::thread::spawn(move || { barrier.wait(); token_exchange(&oauth, &basic("client:secret"), form(&code), ORIGIN).status() })
    }).collect();
    let statuses: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert_eq!(statuses.iter().filter(|&&v| v == StatusCode::OK).count(), 1);
    assert_eq!(statuses.iter().filter(|&&v| v == StatusCode::BAD_REQUEST).count(), 7);
}

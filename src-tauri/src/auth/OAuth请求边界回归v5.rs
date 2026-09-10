//! Synthetic protocol regression; not a substitute for real ChatGPT interoperability.
use super::*;
use axum::body::to_bytes;
use serde_json::Value;

const ORIGIN: &str = "https://resource.example";
const CALLBACK: &str = "https://chatgpt.com/connector/oauth/test";
const VERIFIER: &str = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";
const SECRET: &str = "test-only-oauth-request-boundary-secret";

fn runtime() -> OAuthRuntime {
    OAuthRuntime::new(ORIGIN.into(), "client".into(), None, "password".into(), SECRET.into())
        .with_redirect_uri(CALLBACK.into())
}
fn authorization() -> AuthorizeForm {
    AuthorizeForm { client_id: "client".into(), redirect_uri: CALLBACK.into(),
        code_challenge: URL_SAFE_NO_PAD.encode(Sha256::digest(VERIFIER.as_bytes())),
        code_challenge_method: "S256".into(), resource: ORIGIN.into(), scope: "mcp".into(),
        password: "password".into(), state: "opaque-client-state".into() }
}
fn code(oauth: &OAuthRuntime) -> String {
    assert_eq!(authorize_post(oauth, authorization(), ORIGIN).status(), StatusCode::SEE_OTHER);
    oauth.pending.lock().unwrap().keys().next().unwrap().clone()
}
fn exchange_form(code: &str) -> TokenForm {
    TokenForm { grant_type: "authorization_code".into(), code: code.into(),
        redirect_uri: CALLBACK.into(), code_verifier: VERIFIER.into(), client_id: "client".into(),
        resource: ORIGIN.into(), ..Default::default() }
}
async fn json_body(response: Response) -> Value {
    serde_json::from_slice(&to_bytes(response.into_body(), 32768).await.unwrap()).unwrap()
}

#[test]
fn resource_and_challenge_validators_reject_ambiguous_inputs() {
    for resource in [ORIGIN, "http://127.0.0.1:8000", "http://[::1]:8000"] {
        assert!(valid_resource(resource), "{resource}");
    }
    for resource in ["", "relative", " https://resource.example", "https://u:p@resource.example",
        "https://resource.example#fragment", "https://resource.example?token=x", "http://public.example"] {
        assert!(!valid_resource(resource), "{resource}");
    }
    assert!(valid_challenge(&authorization().code_challenge));
    for challenge in ["".to_string(), "a".repeat(42), "a".repeat(44), "!".repeat(43), "a".repeat(43)] {
        assert!(!valid_challenge(&challenge), "{challenge}");
    }
}

#[test]
fn authorization_requires_explicit_resource_and_rejects_scope_expansion() {
    for resource in ["", "https://other.example", "https://resource.example/", "https://resource.example/mcp"] {
        let oauth = runtime(); let mut form = authorization(); form.resource = resource.into();
        assert_eq!(authorize_post(&oauth, form, ORIGIN).status(), StatusCode::BAD_REQUEST);
        assert!(oauth.pending.lock().unwrap().is_empty());
    }
    let oauth = runtime(); let mut form = authorization(); form.scope = "mcp admin".into();
    assert_eq!(authorize_post(&oauth, form, ORIGIN).status(), StatusCode::BAD_REQUEST);
    assert!(oauth.pending.lock().unwrap().is_empty());
}

#[tokio::test]
async fn authorization_page_never_discloses_workspace_path() {
    let oauth = runtime(); let form = authorization();
    let params = AuthorizeParams { response_type: "code".into(), client_id: form.client_id,
        redirect_uri: form.redirect_uri, code_challenge: form.code_challenge,
        code_challenge_method: form.code_challenge_method, resource: form.resource,
        scope: form.scope, state: form.state };
    let response = authorize_get(&oauth, params, Some("private-workspace-canary-v5"));
    assert_eq!(response.status(), StatusCode::OK);
    let body = String::from_utf8(to_bytes(response.into_body(), 32768).await.unwrap().to_vec()).unwrap();
    assert!(!body.contains("private-workspace-canary-v5"));
    assert!(!body.contains(SECRET));
    assert!(body.contains(ORIGIN));
}

#[tokio::test]
async fn token_exchange_binds_the_authorized_resource_and_rejects_replay() {
    let oauth = runtime(); let authorization_code = code(&oauth);
    assert_eq!(oauth.pending.lock().unwrap()[&authorization_code].resource, ORIGIN);
    let response = token_exchange(&oauth, &HeaderMap::new(), exchange_form(&authorization_code), ORIGIN);
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()[axum::http::header::CACHE_CONTROL], "no-store");
    let body = json_body(response).await;
    let token = body["access_token"].as_str().unwrap();
    assert!(oauth.verify_access_token(token, ORIGIN));
    assert!(!oauth.verify_access_token(token, "https://other.example"));
    assert_eq!(body["scope"], "mcp");
    let repeated = token_exchange(&oauth, &HeaderMap::new(), exchange_form(&authorization_code), ORIGIN);
    assert_eq!(json_body(repeated).await["error"], "invalid_grant");
}

#[tokio::test]
async fn token_exchange_cannot_omit_or_replace_the_authorized_resource() {
    for resource in ["", "https://other.example", "https://resource.example/", "https://resource.example/mcp"] {
        let oauth = runtime(); let authorization_code = code(&oauth);
        let mut form = exchange_form(&authorization_code); form.resource = resource.into();
        let response = token_exchange(&oauth, &HeaderMap::new(), form, ORIGIN);
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(response).await["error"], "invalid_target");
        assert!(oauth.pending.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn origin_change_expired_code_and_wrong_pkce_fail_closed() {
    let oauth = runtime(); let authorization_code = code(&oauth);
    let response = token_exchange(&oauth, &HeaderMap::new(), exchange_form(&authorization_code), "https://changed.example");
    assert_eq!(json_body(response).await["error"], "invalid_target");
    let oauth = runtime(); let authorization_code = code(&oauth);
    oauth.pending.lock().unwrap().get_mut(&authorization_code).unwrap().expires_at = 0;
    let response = token_exchange(&oauth, &HeaderMap::new(), exchange_form(&authorization_code), ORIGIN);
    assert_eq!(json_body(response).await["error"], "invalid_grant");
    let oauth = runtime(); let authorization_code = code(&oauth);
    let mut form = exchange_form(&authorization_code); form.code_verifier = "x".repeat(43);
    let response = token_exchange(&oauth, &HeaderMap::new(), form, ORIGIN);
    assert_eq!(json_body(response).await["error"], "invalid_grant");
}

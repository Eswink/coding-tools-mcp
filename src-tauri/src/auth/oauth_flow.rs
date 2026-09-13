use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{Html, IntoResponse, Redirect, Response};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::Deserialize;
use serde_json::json;
use sha2::{Digest, Sha256};

use super::bearer::constant_time_eq_str;
use super::{oauth_refresh::{RefreshContext, RefreshStore}, session_policy::SessionPolicy};
#[path = "oauth_token.rs"]
mod token;
pub use token::token_exchange;

#[path = "OAuth请求边界v5.rs"]
mod request_boundary;
use request_boundary::{valid_challenge, valid_resource};

#[path = "OAuth客户端认证v7.rs"]
mod client_auth;

pub const OAUTH_CODE_TTL_SECONDS: u64 = 300;
pub const OAUTH_TOKEN_TTL_SECONDS: i64 = 8 * 60 * 60;
#[allow(dead_code)]
pub const OAUTH_MAX_BODY_BYTES: usize = 8_192;

#[derive(Clone)]
pub struct OAuthRuntime {
    pub client_id: String,
    pub client_secret: Option<String>,
    pub password: String,
    pub token_secret: String,
    redirect_uri: String,
    // Issuer and audience are separate; Actions keeps its origin resource.
    resource_path: &'static str,
    refresh: Option<Arc<RefreshStore>>,
    session_policy: SessionPolicy,
    attempts: Arc<Mutex<(u64, u32)>>,
    pending: Arc<Mutex<HashMap<String, PendingCode>>>,
}

#[derive(Clone)]
#[allow(dead_code)]
struct PendingCode {
    scope: String,
    code_challenge: String,
    client_id: String,
    redirect_uri: String,
    state: String,
    expires_at: u64,
    server_url: String,
    resource: String,
}

impl OAuthRuntime {
    pub fn new(
        _base_url: String,
        client_id: String,
        client_secret: Option<String>,
        password: String,
        token_secret: String,
    ) -> Self {
        Self {
            client_id,
            client_secret,
            password,
            token_secret,
            redirect_uri: "https://chatgpt.com/connector_platform_oauth_redirect".into(),
            resource_path: "",
            refresh: None,
            session_policy: SessionPolicy::default(),
            attempts: Arc::new(Mutex::new((0, 0))),
            pending: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn with_redirect_uri(mut self, uri: String) -> Self { self.redirect_uri = uri; self }
    pub fn with_mcp_resource(mut self) -> Self { self.resource_path = "/mcp"; self }
    pub(crate) fn with_refresh_store(mut self, policy: SessionPolicy, root: std::path::PathBuf) -> Result<Self,String> {
        policy.validate()?;
        self.session_policy=policy;
        self.refresh=Some(RefreshStore::shared(root));
        Ok(self)
    }
    pub(crate) fn refresh_enabled(&self) -> bool { self.refresh.is_some() }
    fn refresh_context(&self, client: &str, issuer: &str) -> RefreshContext {
        RefreshContext::new(client,issuer,&self.resource_url(issuer),&self.token_secret,
            &self.password,self.client_secret.as_deref(),&self.session_policy)
    }
    pub fn resource_url(&self, issuer: &str) -> String {
        format!("{}{}", issuer.trim_end_matches('/'), self.resource_path)
    }
    fn resource_metadata_url(&self, issuer: &str) -> String {
        format!("{}/.well-known/oauth-protected-resource{}", issuer.trim_end_matches('/'), self.resource_path)
    }
    fn redirect_allowed(&self, uri: &str) -> bool {
        if uri != self.redirect_uri || uri.len() > 2048 { return false; }
        reqwest::Url::parse(uri).ok().is_some_and(|u| u.scheme() == "https"
            && u.host_str().is_some() && u.username().is_empty() && u.password().is_none() && u.fragment().is_none())
    }
    fn allow_login_attempt(&self) -> bool {
        let mut attempts = self.attempts.lock().expect("oauth login attempts");
        let bucket = unix_now() / 60;
        if attempts.0 != bucket { *attempts = (bucket, 0); }
        if attempts.1 >= 10 { return false; } attempts.1 += 1; true
    }
    pub fn client_id_allowed(&self, client_id: &str) -> bool {
        if client_id.is_empty() || client_id.len() > 256 {
            return false;
        }
        if self.client_id.is_empty() {
            return true;
        }
        constant_time_eq_str(client_id, &self.client_id)
    }

    pub fn verify_access_token(&self, token: &str, server_url: &str) -> bool {
        self.principal(token, server_url).is_some()
    }
    pub(crate) fn principal(&self, token: &str, server_url: &str) -> Option<super::principal::VerifiedPrincipal> {
        let principal = super::principal::verify(token, &self.token_secret, server_url, &self.resource_url(server_url))?;
        if !self.client_id_allowed(&principal.client_id) { return None; }
        if let Some(family) = principal.family_id.as_deref() {
            let store=self.refresh.as_ref()?;
            if !store.valid_family(&self.refresh_context(&principal.client_id,server_url),family) { return None; }
        }
        Some(principal)
    }

}

pub fn verify_oauth_bearer_header(
    headers: &HeaderMap,
    oauth: &OAuthRuntime,
    server_url: &str,
) -> Option<Response> {
    let token = headers.get(AUTHORIZATION).and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer ")).map(str::trim).unwrap_or("");
    if oauth.verify_access_token(token, server_url) { return None; }
    let challenge = format!("Bearer resource_metadata=\"{}\", scope=\"mcp\"", oauth.resource_metadata_url(server_url));
    let mut response = (StatusCode::UNAUTHORIZED, "OAuth authentication required").into_response();
    if let Ok(value) = challenge.parse() { response.headers_mut().insert(axum::http::header::WWW_AUTHENTICATE, value); }
    response.headers_mut().insert(axum::http::header::CACHE_CONTROL, axum::http::HeaderValue::from_static("no-store"));
    Some(response)

}

#[derive(Debug, Deserialize, Default)]
pub struct AuthorizeParams {
    pub response_type: String,
    pub client_id: String,
    pub redirect_uri: String,
    pub code_challenge: String,
    pub code_challenge_method: String,
    #[serde(default)]
    pub state: String,
    #[serde(default)]
    pub resource: String,
    #[serde(default)]
    pub scope: String,
}

#[derive(Debug, Deserialize, Default)]
pub struct AuthorizeForm {
    pub client_id: String,
    pub redirect_uri: String,
    pub code_challenge: String,
    pub code_challenge_method: String,
    #[serde(default)]
    pub state: String,
    #[serde(default)]
    pub resource: String,
    #[serde(default)]
    pub scope: String,
    pub password: String,
}

#[derive(Debug, Deserialize, Default)]
pub struct TokenForm {
    pub grant_type: String,
    #[serde(default)]
    pub code: String,
    #[serde(default)]
    pub redirect_uri: String,
    #[serde(default)]
    pub code_verifier: String,
    #[serde(default)]
    pub refresh_token: String,
    #[serde(default)]
    pub scope: String,
    #[serde(default)]
    pub client_id: String,
    #[serde(default)]
    pub client_secret: String,
    #[serde(default)]
    pub resource: String,
}

pub fn authorize_get(
    oauth: &OAuthRuntime,
    params: AuthorizeParams,
    _workspace_path: Option<&str>,
) -> Response {
    let scope=super::oauth_scope::normalize(&params.scope,oauth.refresh_enabled());
    if !oauth.redirect_allowed(&params.redirect_uri) || !valid_resource(&params.resource)
        || scope.is_err() {
        return html_error("Invalid redirect_uri or scope", StatusCode::BAD_REQUEST);
    }
    if params.response_type != "code" {
        return html_error("response_type must be 'code'", StatusCode::BAD_REQUEST);
    }
    if !oauth.client_id_allowed(&params.client_id) {
        return html_error("Unknown client_id", StatusCode::BAD_REQUEST);
    }
    if params.code_challenge_method != "S256" || !valid_challenge(&params.code_challenge) {
        return html_error(
            "code_challenge_method must be S256 and code_challenge is required",
            StatusCode::BAD_REQUEST,
        );
    }
    Html(login_page(
        &params.client_id,
        &params.redirect_uri,
        &params.code_challenge,
        &params.code_challenge_method,
        &params.state,
        &params.resource,
        scope.as_deref().unwrap_or("mcp"),
        "",
        None,
    ))
    .into_response()
}

pub fn authorize_post(oauth: &OAuthRuntime, form: AuthorizeForm, server_url: &str) -> Response {
    let scope=super::oauth_scope::normalize(&form.scope,oauth.refresh_enabled());
    if !oauth.redirect_allowed(&form.redirect_uri) || scope.is_err()
        || !valid_resource(&form.resource) || form.resource != oauth.resource_url(server_url) {
        return html_error("Invalid redirect_uri, resource or scope", StatusCode::BAD_REQUEST);
    }
    if !oauth.allow_login_attempt() { return html_error("Too many login attempts", StatusCode::TOO_MANY_REQUESTS); }
    if !oauth.client_id_allowed(&form.client_id) {
        return Html(login_page(
            &form.client_id,
            &form.redirect_uri,
            &form.code_challenge,
            &form.code_challenge_method,
            &form.state,
            &form.resource,
            scope.as_deref().unwrap_or("mcp"),
            "Invalid client",
            None,
        ))
        .into_response();
    }
    if form.code_challenge_method != "S256" || !valid_challenge(&form.code_challenge) {
        return Html(login_page(
            &form.client_id,
            &form.redirect_uri,
            &form.code_challenge,
            &form.code_challenge_method,
            &form.state,
            &form.resource,
            scope.as_deref().unwrap_or("mcp"),
            "Invalid PKCE parameters",
            None,
        ))
        .into_response();
    }
    if oauth.password.is_empty() || oauth.token_secret.is_empty() || !constant_time_eq_str(&form.password, &oauth.password) {
        return (
            StatusCode::UNAUTHORIZED,
            Html(login_page(
                &form.client_id,
                &form.redirect_uri,
                &form.code_challenge,
                &form.code_challenge_method,
                &form.state,
                &form.resource,
                scope.as_deref().unwrap_or("mcp"),
                "Invalid password",
                None,
            )),
        )
            .into_response();
    }

    let server_url = server_url.trim_end_matches('/').to_string();
    let code = uuid::Uuid::new_v4().to_string().replace('-', "");
    let now = unix_now();
    {
        let mut pending = oauth.pending.lock().expect("oauth pending lock");
        pending.retain(|_, v| v.expires_at > now);
        if pending.len() >= 128 { return html_error("Too many pending authorizations", StatusCode::TOO_MANY_REQUESTS); }
        pending.insert(
            code.clone(),
            PendingCode {
                scope: scope.unwrap(),
                code_challenge: form.code_challenge.clone(),
                client_id: form.client_id.clone(),
                redirect_uri: form.redirect_uri.clone(),
                state: form.state.clone(),
                expires_at: now + OAUTH_CODE_TTL_SECONDS,
                server_url: server_url.clone(),
                resource: form.resource.clone(),
            },
        );
    }

    let mut qs = format!("code={}", urlencoding_encode(&code));
    if !form.state.is_empty() {
        qs.push_str(&format!("&state={}", urlencoding_encode(&form.state)));
    }
    let sep = if form.redirect_uri.contains('?') { '&' } else { '?' };
    // 授权页面通过 POST 表单提交，但客户端回调必须使用 GET。
    // 307 会保留 POST 并把表单体转发到 ChatGPT connector，导致 Bad Request。
    Redirect::to(&format!("{}{}{}", form.redirect_uri, sep, qs)).into_response()
}


fn verify_pkce(code_verifier: &str, code_challenge: &str) -> bool {
    let digest = Sha256::digest(code_verifier.as_bytes());
    let expected = URL_SAFE_NO_PAD.encode(digest);
    constant_time_eq_str(&expected, code_challenge)
}

fn valid_code_verifier(verifier: &str) -> bool {
    (43..=128).contains(&verifier.len())
        && verifier
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '.' | '_' | '~'))
}

fn token_error(error: &str, description: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        [(axum::http::header::CACHE_CONTROL, "no-store")],
        axum::Json(json!({
            "error": error,
            "error_description": description
        })),
    )
        .into_response()
}

fn html_error(message: &str, status: StatusCode) -> Response {
    (status, Html(format!("<h2>Error</h2><p>{message}</p>"))).into_response()
}

#[allow(clippy::too_many_arguments)]
fn login_page(
    client_id: &str,
    redirect_uri: &str,
    code_challenge: &str,
    code_challenge_method: &str,
    state: &str,
    resource: &str,
    scope: &str,
    error: &str,
    workspace_path: Option<&str>,
) -> String {
    let offline_notice = if scope.split_whitespace().any(|s|s=="offline_access") {
        "<p>Offline access requested: this client may refresh its connection until the configured refresh-session deadline. Local conversation approval is still required and is never renewed by token refresh.</p>"
    } else { "" };
    let error_block = if error.is_empty() {
        String::new()
    } else {
        format!("<p style=\"color:red\">{}</p>", html_escape(error))
    };
    let workspace_block = workspace_path
        .filter(|path| !path.is_empty())
        .map(|path| format!("<p>Workspace: <code>{}</code></p>", html_escape(path)))
        .unwrap_or_default();
    format!(
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>\
        <title>Authorize MCP Server</title>\
        <style>body{{font-family:sans-serif;max-width:380px;margin:4rem auto;padding:1rem}}\
        input{{width:100%;padding:.5rem;margin:.4rem 0;box-sizing:border-box}}\
        button{{width:100%;padding:.7rem;background:#0066cc;color:#fff;border:none;cursor:pointer}}</style>\
        </head><body>\
        <h2>Authorize Coding Tools MCP</h2>\
        {workspace_block}\
        <p>Client: <strong>{}</strong></p>\
        <p>Redirect URI: <code>{}</code></p>\
        {error_block}{offline_notice}\
        <form method='POST' action='/oauth/authorize'>\
        <input type='hidden' name='client_id' value='{}'>\
        <input type='hidden' name='redirect_uri' value='{}'>\
        <input type='hidden' name='code_challenge' value='{}'>\
        <input type='hidden' name='code_challenge_method' value='{}'>\
        <input type='hidden' name='state' value='{}'>\
        <input type='hidden' name='scope' value='{}'>\
        <input type='hidden' name='resource' value='{}'>\
        <label>Password<input type='password' name='password' autocomplete='current-password' required></label>\
        <button type='submit'>Authorize</button>\
        </form></body></html>",
        html_escape(client_id),
        html_escape(redirect_uri),
        html_escape(client_id),
        html_escape(redirect_uri),
        html_escape(code_challenge),
        html_escape(code_challenge_method),
        html_escape(state),
        html_escape(scope),
        html_escape(resource),
    )
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('\"', "&quot;")
        .replace('\'', "&#39;")
}

fn urlencoding_encode(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (byte as char).to_string()
            }
            _ => format!("%{byte:02X}"),
        })
        .collect()
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_exchange_without_client_secret() {
        use axum::http::HeaderMap;

        let oauth = OAuthRuntime::new(
            "https://lb.example.com".into(),
            "chatgpt-client-test".into(),
            None,
            "test-password".into(),
            "token-signing-secret".into(),
        );
        let oauth = oauth.with_redirect_uri("https://chatgpt.com/connector/oauth/test".into());
        let verifier = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";
        let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
        let redirect_uri = "https://chatgpt.com/connector/oauth/test";
        let redirect = authorize_post(
            &oauth,
            AuthorizeForm {
                client_id: "chatgpt-client-test".into(),
                redirect_uri: redirect_uri.into(),
                code_challenge: challenge,
                code_challenge_method: "S256".into(),
                state: "state".into(),
                resource: "https://lb.example.com".into(),
                password: "test-password".into(),
                ..Default::default()
            },
            "https://lb.example.com",
        );
        assert_eq!(redirect.status(), StatusCode::SEE_OTHER);
        let code = {
            let pending = oauth.pending.lock().expect("lock");
            pending.keys().next().cloned().unwrap()
        };

        let response = token_exchange(
            &oauth,
            &HeaderMap::new(),
            TokenForm {
                grant_type: "authorization_code".into(),
                code,
                redirect_uri: redirect_uri.into(),
                code_verifier: verifier.into(),
                client_id: "chatgpt-client-test".into(),
                client_secret: String::new(),
                resource: "https://lb.example.com".into(),
                ..Default::default()
            },
            "https://lb.example.com",
        );
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[test]
    fn pkce_round_trip() {
        let verifier = "dBjftJeZ4CVP-mB92Kpru-AEJvkQlLgi3ThpmQ45N_Xyo";
        let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
        assert!(verify_pkce(verifier, &challenge));
    }
}

#[cfg(test)]
#[path = "OAuth请求边界回归v5.rs"]
mod request_boundary_tests;

#[cfg(test)]
#[path = "OAuth客户端认证回归v7.rs"]
mod client_auth_tests;

//! Credential-free, bounded probes. Response contents never become UI/log text.
use std::time::Duration;

use reqwest::{header, Client, Response, Url};
use serde_json::{json, Value};

pub(super) const MAX_METADATA_BYTES: usize = 64 * 1024;
const MAX_SCHEMA_BYTES: usize = 2 * 1024 * 1024;
pub(super) const TIMEOUT: Duration = Duration::from_secs(4);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum Contract {
    Mcp,
    ActionsHealth,
    OpenApi,
    AuthorizationServer,
    ProtectedResource,
    Challenge,
}

#[derive(Debug, Clone)]
pub(super) struct Probe {
    pub ok: bool,
    pub code: &'static str,
    pub status: Option<u16>,
}

impl Probe {
    pub fn fail(code: &'static str, status: Option<u16>) -> Self {
        Self { ok: false, code, status }
    }
    fn pass(status: u16) -> Self {
        Self { ok: true, code: "verified", status: Some(status) }
    }
    pub fn detail(&self) -> String {
        match self.status {
            Some(status) => format!("HTTP {status}; {}", self.code),
            None => self.code.into(),
        }
    }
}

pub(super) fn client() -> Result<Client, reqwest::Error> {
    Client::builder()
        .timeout(TIMEOUT)
        .connect_timeout(TIMEOUT)
        .redirect(reqwest::redirect::Policy::none())
        // A direct loopback/public-route check must not silently hit an env proxy.
        .no_proxy()
        .build()
}

fn network_error(error: &reqwest::Error) -> Probe {
    Probe::fail(if error.is_timeout() { "timeout" } else { "network_or_tls_error" }, None)
}

/// Only configured origins are requested. Never follow a URL from remote metadata.
/// HTTP is accepted for numeric loopback fixtures/local listeners only.
pub(super) fn valid_origin(origin: &str) -> bool {
    let Ok(url) = Url::parse(origin) else { return false; };
    url.host_str().is_some() && url.username().is_empty() && url.password().is_none()
        && url.query().is_none() && url.fragment().is_none() && url.path() == "/"
        && (url.scheme() == "https" || (url.scheme() == "http"
            && url.host_str().is_some_and(|host| {
                host.trim_matches(['[', ']']).parse::<std::net::IpAddr>()
                    .is_ok_and(|address| address.is_loopback())
            })))
}

async fn bounded_body(response: &mut Response, limit: usize) -> Result<Vec<u8>, &'static str> {
    if response.content_length().is_some_and(|size| size > limit as u64) {
        return Err("response_too_large");
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|e| {
        if e.is_timeout() { "timeout" } else { "response_read_error" }
    })? {
        if chunk.len() > limit.saturating_sub(body.len()) { return Err("response_too_large"); }
        body.extend_from_slice(&chunk);
    }
    Ok(body)
}

fn is_json(content_type: &str) -> bool {
    let mime = content_type.split(';').next().unwrap_or("").trim().to_ascii_lowercase();
    mime == "application/json" || (mime.starts_with("application/") && mime.ends_with("+json"))
}

fn contains_string(value: &Value, field: &str, expected: &str) -> bool {
    value.get(field).and_then(Value::as_array).is_some_and(|items| {
        !items.is_empty() && items.iter().all(Value::is_string)
            && items.iter().any(|item| item.as_str() == Some(expected))
    })
}

pub(super) fn validate_json(contract: Contract, value: &Value, issuer: &str, resource: &str) -> bool {
    if !value.is_object() { return false; }
    match contract {
        Contract::Mcp => value["name"] == "coding-tools-mcp"
            && value["version"] == env!("CARGO_PKG_VERSION")
            && value["protocolVersion"] == "2025-06-18",
        Contract::ActionsHealth => value["ok"] == true && value["service"] == "coding-tools-actions"
            && value["tools_loaded"].as_u64().is_some_and(|count| count > 0),
        Contract::OpenApi => value["openapi"].as_str().is_some_and(|v| v.starts_with("3."))
            && value["paths"].as_object().is_some_and(|paths| !paths.is_empty())
            && value["servers"].as_array().is_some_and(|servers| {
                servers.len() == 1 && servers[0]["url"].as_str() == Some(issuer)
            }),
        Contract::AuthorizationServer => value["issuer"].as_str() == Some(issuer)
            && value["authorization_endpoint"] == format!("{issuer}/oauth/authorize")
            && value["token_endpoint"] == format!("{issuer}/oauth/token")
            && contains_string(value, "response_types_supported", "code")
            && contains_string(value, "grant_types_supported", "authorization_code")
            && contains_string(value, "code_challenge_methods_supported", "S256")
            && value["token_endpoint_auth_methods_supported"].as_array().is_some_and(|methods| {
                !methods.is_empty() && methods.iter().all(|v| matches!(v.as_str(),
                    Some("none" | "client_secret_post" | "client_secret_basic")))
            }),
        Contract::ProtectedResource => value["resource"].as_str() == Some(resource)
            && value["authorization_servers"].as_array().is_some_and(|servers| {
                servers.len() == 1 && servers[0].as_str() == Some(issuer)
            }) && contains_string(value, "bearer_methods_supported", "header"),
        Contract::Challenge => false,
    }
}

/// Validate this server's deliberately narrow challenge contract, not substrings.
/// Ambiguous/duplicated parameters, controls and extra challenges fail closed.
pub(super) fn valid_challenge(value: &str, metadata_url: &str) -> bool {
    if value.len() > 4096 || value.chars().any(char::is_control) { return false; }
    let Some((scheme, parameters)) = value.split_once(' ') else { return false; };
    if !scheme.eq_ignore_ascii_case("Bearer") { return false; }
    let mut metadata = None;
    let mut scope = None;
    for parameter in parameters.split(',') {
        let Some((key, value)) = parameter.trim().split_once('=') else { return false; };
        let Some(value) = value.trim().strip_prefix('"').and_then(|v| v.strip_suffix('"')) else { return false; };
        if value.contains(['"', '\\']) { return false; }
        match key.trim() {
            "resource_metadata" if metadata.is_none() => metadata = Some(value),
            "scope" if scope.is_none() => scope = Some(value),
            _ => return false,
        }
    }
    metadata == Some(metadata_url) && scope == Some("mcp")
}

pub(super) async fn check(
    client: &Client, transport: &str, path: &str, contract: Contract,
    issuer: &str, resource: &str,
) -> Probe {
    if !valid_origin(transport) || !valid_origin(issuer) {
        return Probe::fail("invalid_or_missing_origin", None);
    }
    let url = format!("{}{path}", transport.trim_end_matches('/'));
    let request = if contract == Contract::Challenge {
        client.post(&url).json(&json!({
            "jsonrpc":"2.0", "id":"health-discovery", "method":"initialize", "params":{}
        }))
    } else { client.get(&url) };
    let mut response = match request.send().await {
        Ok(response) => response,
        Err(error) => return network_error(&error),
    };
    let status = response.status().as_u16();
    if response.status().is_redirection() { return Probe::fail("redirect_rejected", Some(status)); }
    if contract == Contract::Challenge {
        let metadata_url = format!("{issuer}/.well-known/oauth-protected-resource/mcp");
        let headers = response.headers().get_all(header::WWW_AUTHENTICATE).iter().collect::<Vec<_>>();
        return if status == 401 && headers.len() == 1
            && headers[0].to_str().is_ok_and(|value| valid_challenge(value, &metadata_url)) {
            Probe::pass(status)
        } else { Probe::fail("invalid_401_challenge", Some(status)) };
    }
    let content_type = response.headers().get(header::CONTENT_TYPE)
        .and_then(|h| h.to_str().ok()).unwrap_or("").to_string();
    // The Server header is a diagnostic hint, never a trusted backend identity.
    let nginx_hint = response.headers().get(header::SERVER)
        .and_then(|h| h.to_str().ok()).is_some_and(|v| {
            let product = v.split_whitespace().next().unwrap_or("");
            product.eq_ignore_ascii_case("nginx")
                || product.get(..6).is_some_and(|v| v.eq_ignore_ascii_case("nginx/"))
        });
    let discovery_path = matches!(path, "/.well-known/oauth-authorization-server"
        | "/.well-known/oauth-protected-resource" | "/.well-known/oauth-protected-resource/mcp")
        && matches!(contract, Contract::AuthorizationServer | Contract::ProtectedResource);
    let limit = if contract == Contract::OpenApi { MAX_SCHEMA_BYTES } else { MAX_METADATA_BYTES };
    let bytes = match bounded_body(&mut response, limit).await {
        Ok(body) => body,
        Err(code) => return Probe::fail(code, Some(status)),
    };
    // Only known classifications leave this function, never remote error strings.
    let json = serde_json::from_slice::<Value>(&bytes).ok();
    if status == 404 && is_json(&content_type) && json.as_ref().is_some_and(|v| v["error"] == "OAuth not configured") {
        return Probe::fail("oauth_not_configured", Some(status));
    }
    if !is_json(&content_type) {
        let text = String::from_utf8_lossy(&bytes).to_ascii_lowercase();
        let code = if text.contains("frp") && (text.contains("powered by") || text.contains("not found")) {
            "frp_route_not_found"
        } else if status == 404 && discovery_path {
            if nginx_hint { "nginx_discovery_route_not_found" } else { "discovery_route_not_found" }
        } else { "non_json_response" };
        return Probe::fail(code, Some(status));
    }
    if status != 200 { return Probe::fail("http_error", Some(status)); }
    let Some(json) = json else { return Probe::fail("invalid_json", Some(status)); };
    if validate_json(contract, &json, issuer, resource) { Probe::pass(status) }
    else { Probe::fail("metadata_or_identity_mismatch", Some(status)) }
}

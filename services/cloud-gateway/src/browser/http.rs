use super::{html, BrowserAuth, BrowserError, BrowserRequest, COOKIE_NAME};
use crate::{crypto::valid_digest, Secret};
use axum::{
    body::Bytes,
    extract::{RawQuery, State},
    http::{header, HeaderMap, StatusCode, Uri},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use std::collections::BTreeMap;

pub(crate) fn routes(auth: BrowserAuth) -> Router {
    let p = auth.store.identity.prefix();
    Router::new()
        .route(&format!("{p}/oauth/authorize"), get(authorize))
        .route(&format!("{p}/oauth/login"), post(login))
        .route(&format!("{p}/oauth/consent"), post(consent))
        .with_state(auth)
}
fn decode(raw: &[u8]) -> super::Result<String> {
    let mut bytes = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        match raw[i] {
            b'+' => bytes.push(b' '),
            b'%' => {
                let pair = raw.get(i + 1..i + 3).ok_or(BrowserError::Rejected)?;
                let value = std::str::from_utf8(pair)
                    .ok()
                    .and_then(|s| u8::from_str_radix(s, 16).ok())
                    .ok_or(BrowserError::Rejected)?;
                bytes.push(value);
                i += 2;
            }
            b => bytes.push(b),
        }
        i += 1;
    }
    let value = String::from_utf8(bytes).map_err(|_| BrowserError::Rejected)?;
    if value.chars().any(char::is_control) {
        return Err(BrowserError::Rejected);
    }
    Ok(value)
}
fn fields(raw: &[u8], allowed: &[&str]) -> super::Result<BTreeMap<String, String>> {
    if raw.is_empty() || raw.len() > 8192 || !raw.is_ascii() {
        return Err(BrowserError::Rejected);
    }
    let mut fields = BTreeMap::new();
    for part in raw.split(|&b| b == b'&') {
        let eq = part
            .iter()
            .position(|&b| b == b'=')
            .ok_or(BrowserError::Rejected)?;
        let key = decode(&part[..eq])?;
        let value = decode(&part[eq + 1..])?;
        if !allowed.contains(&key.as_str())
            || value.is_empty()
            || fields.insert(key, value).is_some()
        {
            return Err(BrowserError::Rejected);
        }
    }
    if fields.len() != allowed.len() {
        return Err(BrowserError::Rejected);
    }
    Ok(fields)
}
fn cookie(headers: &HeaderMap) -> super::Result<String> {
    if headers.get_all(header::COOKIE).iter().count() != 1 {
        return Err(BrowserError::Rejected);
    }
    let raw = headers
        .get(header::COOKIE)
        .and_then(|h| h.to_str().ok())
        .ok_or(BrowserError::Rejected)?;
    if raw.len() > 4096 {
        return Err(BrowserError::Rejected);
    }
    let mut found = None;
    for part in raw.split(';') {
        if let Some((name, value)) = part.trim().split_once('=') {
            if name == COOKIE_NAME {
                if found.is_some() || !valid_digest(value) {
                    return Err(BrowserError::Rejected);
                }
                found = Some(value.to_owned());
            }
        }
    }
    found.ok_or(BrowserError::Rejected)
}
fn browser_post(auth: &BrowserAuth, h: &HeaderMap, uri: &Uri) -> super::Result<String> {
    if uri.query().is_some()
        || h.get_all(header::ORIGIN).iter().count() != 1
        || !h
            .get(header::ORIGIN)
            .and_then(|x| x.to_str().ok())
            .is_some_and(|s| auth.store.identity.allow_origin(s))
        || h.get_all("sec-fetch-site").iter().count() > 1
        || h.get("sec-fetch-site")
            .is_some_and(|x| x.to_str().ok() != Some("same-origin"))
        || h.get_all(header::CONTENT_TYPE).iter().count() != 1
        || h.get(header::CONTENT_TYPE)
            .and_then(|x| x.to_str().ok())
            .and_then(|s| s.split(';').next())
            .map(str::trim)
            != Some("application/x-www-form-urlencoded")
        || h.contains_key(header::AUTHORIZATION)
    {
        return Err(BrowserError::Rejected);
    }
    cookie(h)
}
fn error(error: BrowserError) -> Response {
    let status = match error {
        BrowserError::RateLimited => StatusCode::TOO_MANY_REQUESTS,
        BrowserError::StoreUnavailable | BrowserError::InvalidConfig => {
            StatusCode::SERVICE_UNAVAILABLE
        }
        _ => StatusCode::BAD_REQUEST,
    };
    let mut r = html::secure(
        (status, Json(json!({"error":error.to_string()}))).into_response(),
        None,
    );
    if error == BrowserError::RateLimited {
        r.headers_mut()
            .insert(header::RETRY_AFTER, header::HeaderValue::from_static("60"));
    }
    r
}
async fn authorize(State(auth): State<BrowserAuth>, RawQuery(query): RawQuery) -> Response {
    let result = async {
        let f = fields(
            query.as_deref().unwrap_or("").as_bytes(),
            &[
                "response_type",
                "client_id",
                "redirect_uri",
                "resource",
                "scope",
                "code_challenge",
                "code_challenge_method",
                "state",
            ],
        )?;
        if f["response_type"] != "code"
            || f["scope"] != "mcp"
            || f["code_challenge_method"] != "S256"
        {
            return Err(BrowserError::Rejected);
        }
        auth.begin(BrowserRequest {
            client_id: f["client_id"].clone(),
            redirect_uri: f["redirect_uri"].clone(),
            resource: f["resource"].clone(),
            code_challenge: f["code_challenge"].clone(),
            state: f["state"].clone(),
        })
        .await
    }
    .await;
    match result {
        Ok(page) => html::page(auth.store.identity.prefix(), page),
        Err(e) => error(e),
    }
}
async fn login(State(auth): State<BrowserAuth>, h: HeaderMap, uri: Uri, raw: Bytes) -> Response {
    let result = async {
        let cookie = browser_post(&auth, &h, &uri)?;
        let mut f = fields(&raw, &["csrf", "password"])?;
        let password = Secret::new(f.remove("password").ok_or(BrowserError::Rejected)?);
        auth.login(&cookie, &f["csrf"], password).await
    }
    .await;
    match result {
        Ok(page) => html::page(auth.store.identity.prefix(), page),
        Err(e) => error(e),
    }
}
async fn consent(State(auth): State<BrowserAuth>, h: HeaderMap, uri: Uri, raw: Bytes) -> Response {
    let result = async {
        let cookie = browser_post(&auth, &h, &uri)?;
        let f = fields(&raw, &["csrf", "decision"])?;
        let allow = match f["decision"].as_str() {
            "allow" => true,
            "deny" => false,
            _ => return Err(BrowserError::Rejected),
        };
        auth.decide(&cookie, &f["csrf"], allow).await
    }
    .await;
    match result {
        Ok(location) => html::redirect(location.expose()),
        Err(e) => error(e),
    }
}

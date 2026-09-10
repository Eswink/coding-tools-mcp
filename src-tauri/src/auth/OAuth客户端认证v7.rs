//! RFC 6749 section 2.3.1: one client authentication method per request.
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use base64::{engine::general_purpose::STANDARD, Engine};
use super::TokenForm;

fn form_component(value: &str, maximum: usize) -> Result<String, ()> {
    let mut out = Vec::with_capacity(value.len().min(maximum));
    let mut bytes = value.bytes();
    while let Some(byte) = bytes.next() {
        let decoded = match byte {
            b'+' => b' ',
            b'%' => {
                let hi = bytes.next().and_then(|v| (v as char).to_digit(16)).ok_or(())?;
                let lo = bytes.next().and_then(|v| (v as char).to_digit(16)).ok_or(())?;
                ((hi << 4) | lo) as u8
            }
            value => value,
        };
        if out.len() >= maximum { return Err(()); }
        out.push(decoded);
    }
    let text = String::from_utf8(out).map_err(|_| ())?;
    if text.chars().any(char::is_control) { return Err(()); }
    Ok(text)
}

pub(super) fn resolve(headers: &HeaderMap, form: &mut TokenForm) -> Result<(), ()> {
    let mut values = headers.get_all(header::AUTHORIZATION).iter();
    if let Some(value) = values.next() {
        if values.next().is_some() || !form.client_secret.is_empty() { return Err(()); }
        let value = value.to_str().map_err(|_| ())?;
        if value.len() > 8192 { return Err(()); }
        let (scheme, encoded) = value.split_once(' ').ok_or(())?;
        if !scheme.eq_ignore_ascii_case("Basic") { return Err(()); }
        let decoded = STANDARD.decode(encoded).map_err(|_| ())?;
        let text = String::from_utf8(decoded).map_err(|_| ())?;
        let (id, secret) = text.split_once(':').ok_or(())?;
        let id = form_component(id, 256)?;
        let secret = form_component(secret, 2048)?;
        // A duplicated client_id may identify the client, but must not change it.
        if !form.client_id.is_empty() && !super::constant_time_eq_str(&form.client_id, &id) {
            return Err(());
        }
        form.client_id = id;
        form.client_secret = secret;
    }
    if form.client_id.is_empty() || form.client_id.len() > 256 || form.client_secret.len() > 2048
        || form.client_id.chars().any(char::is_control)
        || form.client_secret.chars().any(char::is_control) { return Err(()); }
    Ok(())
}

pub(super) fn invalid_client() -> Response {
    (
        StatusCode::UNAUTHORIZED,
        [(header::WWW_AUTHENTICATE, "Basic realm=\"oauth\""),
         (header::CACHE_CONTROL, "no-store"), (header::PRAGMA, "no-cache")],
        axum::Json(serde_json::json!({
            "error": "invalid_client", "error_description": "Client authentication failed"
        })),
    ).into_response()
}

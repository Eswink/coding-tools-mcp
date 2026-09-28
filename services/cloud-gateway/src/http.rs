//! Identity HTTP adapter, NOT a standalone public service. Owner login/consent,
//! agent transport and MCP dispatch must be wired and audited before publication.
use crate::{ClientCredential, IdentityError, IdentityStore};
use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, State},
    http::{header, HeaderMap, Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use std::{collections::BTreeMap, time::Duration};

pub fn identity_routes(store: IdentityStore) -> Router {
    Router::new()
        .route(
            &store.identity().resource_metadata_path(),
            get(resource_metadata),
        )
        .route(
            &store.identity().server_metadata_path(),
            get(server_metadata),
        )
        .route(&store.identity().token_path(), post(token))
        .with_state(store.clone())
        .merge(crate::browser::http::routes(
            crate::browser::BrowserAuth::new(store.clone()),
        ))
        .layer(DefaultBodyLimit::max(8192))
        .layer(middleware::from_fn_with_state(store.clone(), boundary))
}
async fn resource_metadata(State(s): State<IdentityStore>) -> Response {
    Json(s.identity().resource_metadata()).into_response()
}
async fn server_metadata(State(s): State<IdentityStore>) -> Response {
    Json(s.identity().server_metadata()).into_response()
}
async fn boundary(
    State(s): State<IdentityStore>,
    req: Request<axum::body::Body>,
    next: Next,
) -> Response {
    let headers = req.headers();
    let single = |name: &str| headers.get_all(name).iter().count() <= 1;
    let valid = [
        "host",
        "origin",
        "authorization",
        "content-type",
        "content-length",
        "transfer-encoding",
    ]
    .into_iter()
    .all(single)
        && headers.get(header::HOST).and_then(|v| v.to_str().ok())
            == Some(s.identity().authority())
        && headers
            .get(header::ORIGIN)
            .is_none_or(|v| v.to_str().is_ok_and(|v| s.identity().allow_origin(v)))
        && !(headers.contains_key(header::CONTENT_LENGTH)
            && headers.contains_key(header::TRANSFER_ENCODING));
    let mut response = if !valid {
        (
            StatusCode::FORBIDDEN,
            Json(json!({"error":"request_rejected"})),
        )
            .into_response()
    } else {
        match tokio::time::timeout(Duration::from_secs(5), next.run(req)).await {
            Ok(r) => r,
            Err(_) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error":"temporarily_unavailable"})),
            )
                .into_response(),
        }
    };
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        header::HeaderValue::from_static("no-store"),
    );
    response
        .headers_mut()
        .insert(header::PRAGMA, header::HeaderValue::from_static("no-cache"));
    // Trusted form pages deliberately use strict-origin. Do not turn their POST
    // Origin into null by overwriting that policy; APIs/errors default to no-referrer.
    response
        .headers_mut()
        .entry(header::REFERRER_POLICY)
        .or_insert(header::HeaderValue::from_static("no-referrer"));
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        header::HeaderValue::from_static("nosniff"),
    );
    response
}
fn fields(raw: &[u8]) -> crate::Result<BTreeMap<String, String>> {
    if raw.len() > 8192 || !raw.is_ascii() {
        return Err(IdentityError::InvalidRequest);
    }
    for (i, b) in raw.iter().enumerate() {
        if *b == b'%'
            && !(raw.get(i + 1).is_some_and(u8::is_ascii_hexdigit)
                && raw.get(i + 2).is_some_and(u8::is_ascii_hexdigit))
        {
            return Err(IdentityError::InvalidRequest);
        }
    }
    let mut result = BTreeMap::new();
    for (k, v) in url::form_urlencoded::parse(raw) {
        if result.len() >= 10
            || ![
                "grant_type",
                "client_id",
                "client_secret",
                "resource",
                "code",
                "redirect_uri",
                "code_verifier",
                "refresh_token",
                "scope",
            ]
            .contains(&k.as_ref())
            || result.insert(k.into_owned(), v.into_owned()).is_some()
        {
            return Err(IdentityError::InvalidRequest);
        }
    }
    Ok(result)
}
async fn token(State(s): State<IdentityStore>, headers: HeaderMap, body: Bytes) -> Response {
    let content_type = headers
        .get(header::CONTENT_TYPE)
        .and_then(|x| x.to_str().ok())
        .unwrap_or("");
    if content_type.split(';').next().unwrap_or("").trim() != "application/x-www-form-urlencoded" {
        return (
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            Json(json!({"error":"invalid_request"})),
        )
            .into_response();
    }
    // Do not silently ignore or reinterpret unsupported HTTP Basic authentication.
    if headers.contains_key(header::AUTHORIZATION) {
        return oauth_error(IdentityError::InvalidClient);
    }
    let f = match fields(&body) {
        Ok(f) => f,
        Err(e) => return oauth_error(e),
    };
    let required = |key: &str| {
        f.get(key)
            .map(String::as_str)
            .filter(|v| !v.is_empty())
            .ok_or(IdentityError::InvalidRequest)
    };
    if f.get("scope").is_some_and(|s| s != "mcp") {
        return oauth_error(IdentityError::InvalidRequest);
    }
    let result = async {
        let client = ClientCredential {
            client_id: required("client_id")?,
            secret: f.get("client_secret").map(String::as_str),
        };
        let resource = required("resource")?;
        match required("grant_type")? {
            "authorization_code" if !f.contains_key("refresh_token") => {
                s.exchange_code(
                    client,
                    required("code")?,
                    required("code_verifier")?,
                    required("redirect_uri")?,
                    resource,
                )
                .await
            }
            "refresh_token"
                if !["code", "code_verifier", "redirect_uri"]
                    .iter()
                    .any(|k| f.contains_key(*k)) =>
            {
                s.refresh(client, required("refresh_token")?, resource)
                    .await
            }
            _ => Err(IdentityError::InvalidRequest),
        }
    }
    .await;
    match result {
        Ok(t) => Json(
            json!({"access_token":t.access_token.expose(),"refresh_token":t.refresh_token.expose(),
            "token_type":"Bearer","expires_in":t.expires_in,"scope":"mcp"}),
        )
        .into_response(),
        Err(e) => oauth_error(e),
    }
}
fn oauth_error(e: IdentityError) -> Response {
    let (status, code) = match e {
        IdentityError::StoreUnavailable => {
            (StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable")
        }
        IdentityError::InvalidClient => (StatusCode::BAD_REQUEST, "invalid_client"),
        IdentityError::InvalidGrant | IdentityError::InvalidToken => {
            (StatusCode::BAD_REQUEST, "invalid_grant")
        }
        _ => (StatusCode::BAD_REQUEST, "invalid_request"),
    };
    (status, Json(json!({"error":code}))).into_response()
}

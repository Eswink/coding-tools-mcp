//! OAuth grant dispatch kept separate from the browser consent page.
use super::*;
use crate::auth::oauth_refresh::{RefreshError, RefreshPair};

pub fn token_exchange(oauth: &OAuthRuntime, headers: &HeaderMap, mut form: TokenForm, server_url: &str) -> Response {
    if form.grant_type != "authorization_code" && !(form.grant_type=="refresh_token" && oauth.refresh_enabled()) {
        return token_error("unsupported_grant_type","Unsupported grant type");
    }
    if client_auth::resolve(headers,&mut form).is_err() || !oauth.client_id_allowed(&form.client_id) {
        return client_auth::invalid_client();
    }
    if let Some(expected)=oauth.client_secret.as_deref() {
        if !constant_time_eq_str(&form.client_secret,expected) { return client_auth::invalid_client(); }
    }
    if form.grant_type=="refresh_token" {
        let ctx=oauth.refresh_context(&form.client_id,server_url);
        return match oauth.refresh.as_ref().unwrap().rotate(&ctx,&form.refresh_token,&form.resource,&form.scope) {
            Ok(pair)=>access_response(oauth,&form.client_id,server_url,Some(pair)),
            Err(e)=>refresh_error(e),
        };
    }
    if form.code.is_empty() || !valid_code_verifier(&form.code_verifier) {
        return token_error("invalid_grant","Missing code or invalid code_verifier");
    }
    let code_data=oauth.pending.lock().expect("oauth pending lock").remove(&form.code);
    let Some(code_data)=code_data else {return token_error("invalid_grant","Unknown or already-used authorization code")};
    if unix_now()>=code_data.expires_at || !constant_time_eq_str(&code_data.client_id,&form.client_id)
        || !constant_time_eq_str(&code_data.redirect_uri,&form.redirect_uri)
        || !verify_pkce(&form.code_verifier,&code_data.code_challenge) {
        return token_error("invalid_grant","Authorization code validation failed");
    }
    let issuer=code_data.server_url.trim_end_matches('/');
    if issuer!=server_url.trim_end_matches('/') || form.resource!=code_data.resource || code_data.resource!=oauth.resource_url(issuer) {
        return token_error("invalid_target","Resource identity changed or mismatched");
    }
    let refresh=if code_data.scope=="mcp offline_access" {
        let Some(store)=oauth.refresh.as_ref() else {return token_error("invalid_scope","Offline access is unavailable")};
        match store.issue(&oauth.refresh_context(&form.client_id,issuer)) {Ok(pair)=>Some(pair),Err(e)=>return refresh_error(e)}
    } else {None};
    access_response(oauth,&form.client_id,issuer,refresh)
}
fn access_response(oauth: &OAuthRuntime, client: &str, issuer: &str, refresh: Option<RefreshPair>) -> Response {
    let mut ttl=if oauth.refresh_enabled(){oauth.session_policy.access_token_ttl_seconds as i64}else{OAUTH_TOKEN_TTL_SECONDS};
    if let Some(pair)=&refresh {ttl=ttl.min(pair.expires_at.saturating_sub(unix_now()) as i64);}
    let family=refresh.as_ref().map(|p|p.family_id.as_str());
    let result=if family.is_none() {
        crate::auth::principal::issue(issuer,&oauth.resource_url(issuer),&oauth.token_secret,client,ttl)
    } else {
        crate::auth::principal::issue_with_family(issuer,&oauth.resource_url(issuer),&oauth.token_secret,client,ttl,family)
    };
    match result {
        Ok(access_token)=> {
            let mut result=json!({"access_token":access_token,"token_type":"Bearer","expires_in":ttl,"scope":"mcp"});
            if let Some(pair)=refresh {
                result["refresh_token"]=json!(&*pair.token);result["scope"]=json!(pair.scopes);
                result["refresh_token_expires_in"]=json!(pair.expires_at.saturating_sub(unix_now()));
            }
            (StatusCode::OK,[(axum::http::header::CACHE_CONTROL,"no-store"),(axum::http::header::PRAGMA,"no-cache")],axum::Json(result)).into_response()
        }
        Err(_)=>token_error("server_error","Failed to issue access token"),
    }
}
fn refresh_error(error: RefreshError) -> Response {
    match error {
        RefreshError::InvalidGrant=>token_error("invalid_grant","Refresh token expired, revoked, mismatched or already used"),
        RefreshError::InvalidTarget=>token_error("invalid_target","Resource does not match the original grant"),
        RefreshError::InvalidScope=>token_error("invalid_scope","Requested scopes exceed or mismatch the grant"),
        RefreshError::Unavailable|RefreshError::Capacity=> (
            StatusCode::SERVICE_UNAVAILABLE,[(axum::http::header::CACHE_CONTROL,"no-store"),(axum::http::header::PRAGMA,"no-cache")],
            axum::Json(json!({"error":"temporarily_unavailable","error_description":"Refresh storage or capacity unavailable. Do not blindly repeat a rotation; inspect the desktop status."})),
        ).into_response(),
    }
}

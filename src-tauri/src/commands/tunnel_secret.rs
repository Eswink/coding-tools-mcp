//! Validated, write-only credential accompanying a workspace configuration transaction.
use crate::error::{AppError, AppResult};
use crate::runtime::ServiceKind;
use crate::workspace::WorkspaceProfile;

#[derive(Clone, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TunnelSecretUpdate {
    pub key: String,
    pub value: String,
}

pub(super) fn selected_service(profile: &WorkspaceProfile, key: &str) -> Option<ServiceKind> {
    match key {
        "cloudflare_token" if profile.tunnel.tunnel_type == "cloudflare"
            && profile.tunnel.cloudflare_mode == "named" => Some(ServiceKind::Mcp),
        "frp_token" if profile.tunnel.tunnel_type == "frp"
            && profile.tunnel.frp_profile_id.trim().is_empty() => Some(ServiceKind::Mcp),
        "actions_cloudflare_token" if profile.actions.tunnel_type == "cloudflare"
            && profile.actions.cloudflare_mode == "named" => Some(ServiceKind::Actions),
        "actions_frp_token" if profile.actions.tunnel_type == "frp"
            && profile.actions.frp_profile_id.trim().is_empty() => Some(ServiceKind::Actions),
        _ => None,
    }
}

pub(super) fn validate(profile: &WorkspaceProfile, update: &TunnelSecretUpdate) -> AppResult<ServiceKind> {
    // No Debug/Serialize implementation: secret values must not enter diagnostics.
    if update.value.trim().is_empty() || update.value.len() > 16 * 1024
        || update.value.chars().any(char::is_control) {
        return Err(AppError::Message("隧道凭据为空、过长或包含控制字符。".into()));
    }
    selected_service(profile, &update.key)
        .ok_or_else(|| AppError::Message("隧道凭据与所选服务、提供方或凭据来源不匹配。".into()))
}

//! Privileged local UI only: these commands are never registered as MCP tools.
use serde_json::Value;
use tauri::State;
use crate::app_state::AppState;
use crate::error::{AppError, AppResult};
#[tauri::command]
pub fn chat_authorization_control(state: State<'_, AppState>, id: String, action: String,
    request_id: Option<String>, scopes: Option<Vec<String>>, exclusive: Option<bool>) -> AppResult<Value> {
    let profile = state.with_workspaces(|store| store.get(&id).cloned()
        .ok_or_else(|| AppError::Message("工作区不存在".into())))?;
    let service = crate::auth::chat::service();
    match action.as_str() {
        "status" => (),
        "approve" | "deny" => {
            if profile.auth.auth_type != "oauth" { return Err(AppError::Message("聊天授权要求 OAuth，请先更新认证配置".into())); }
            service.decide(&id, request_id.as_deref().ok_or_else(|| AppError::Message("缺少授权请求 ID".into()))?,
                action == "approve", &scopes.unwrap_or_default()).map_err(AppError::Message)?;
        }
        "revoke" => service.revoke(&id,Some(request_id.as_deref().ok_or_else(|| AppError::Message("缺少授权 ID".into()))?)),
        "revoke_all" => service.revoke(&id,None),
        "exclusive" => service.set_exclusive(&id,exclusive.ok_or_else(|| AppError::Message("缺少独占模式设置".into()))?),
        _ => return Err(AppError::Message("未知授权操作".into())),
    }
    let mut result = service.snapshot(&id);
    result["oauth_ready"] = (profile.auth.auth_type == "oauth").into();
    Ok(result)
}

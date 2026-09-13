//! Privileged local UI only: these commands are never registered as MCP tools.
use serde_json::Value;
use tauri::{AppHandle, Manager};
use crate::app_state::AppState;
use crate::error::{AppError, AppResult};
#[tauri::command]
pub async fn chat_authorization_control(app: AppHandle, id: String, action: String,
    request_id: Option<String>, scopes: Option<Vec<String>>, exclusive: Option<bool>) -> AppResult<Value> {
    tauri::async_runtime::spawn_blocking(move || {
    let state = app.state::<AppState>();
    let profile = state.with_workspaces(|store| store.get(&id).cloned()
        .ok_or_else(|| AppError::Message("工作区不存在".into())))?;
    let service = crate::auth::chat::service();
    match action.as_str() {
        "status" => (),
        "acknowledge_recovery" => service.acknowledge_recovery(&id,request_id.as_deref().ok_or_else(||AppError::Message("缺少恢复确认版本".into()))?).map_err(AppError::Message)?,
        "cancel_sessions" => service.cancel_local_sessions(&id),
        "approve" | "deny" => {
            if profile.auth.auth_type != "oauth" { return Err(AppError::Message("聊天授权要求 OAuth，请先更新认证配置".into())); }
            service.decide(&id, request_id.as_deref().ok_or_else(|| AppError::Message("缺少授权请求 ID".into()))?,
                action == "approve", &scopes.unwrap_or_default()).map_err(AppError::Message)?;
        }
        "revoke" => service.revoke(&id,Some(request_id.as_deref().ok_or_else(|| AppError::Message("缺少授权 ID".into()))?)),
        "revoke_all" => service.revoke(&id,None),
        "exclusive" => {
            let _=exclusive;
            return Err(AppError::Message("请在远程会话安全设置中保存独占模式；临时开关不再覆盖持久配置".into()));
        },
        _ => return Err(AppError::Message("未知授权操作".into())),
    }
    let mut result = service.snapshot(&id);
    result["oauth_ready"] = (profile.auth.auth_type == "oauth").into();
    Ok(result)
    }).await.map_err(|_| AppError::Message("本机授权控制失败".into()))?
}

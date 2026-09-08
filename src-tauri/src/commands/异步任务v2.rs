//! Trusted desktop task controls; execution remains confined to the MCP/Actions
//! dispatcher. The UI can only list, inspect or cancel, never submit a command.
use serde_json::Value;
use tauri::State;
use crate::app_state::AppState;
use crate::error::{AppError, AppResult};
use crate::tools::{ToolContext, Workspace, PolicySettings};
use crate::workspace::WorkspaceProfile;

pub(crate) fn context(profile: &WorkspaceProfile, channel: &str) -> AppResult<ToolContext> {
    let (policy, auth) = match channel {
        "mcp" => (PolicySettings::from_runtime(&profile.runtime), profile.auth.clone()),
        "actions" => (PolicySettings::from_actions_config(&profile.actions), crate::workspace::AuthConfig {
            auth_type: profile.actions.auth_type.clone(), ..Default::default()
        }),
        _ => return Err(AppError::Message("服务通道必须是 mcp 或 actions。".into())),
    };
    let workspace = Workspace::new(profile.path.clone().into()).map_err(|e| AppError::Message(e.message()))?;
    // A local operator may stop jobs even after a remote profile becomes read-only.
    // The operation whitelist below never exposes arbitrary execution to this IPC.
    let mut ctx = ToolContext::from_workspace(workspace, auth, policy.clone(), "full".into(), policy.permission_mode.clone());
    ctx.enable_durable_tasks(&profile.id, channel);
    ctx.local_task_control = true;
    Ok(ctx)
}

#[tauri::command]
pub async fn control_exec_tasks(state: State<'_, AppState>, id: String, channel: String, action: String, args: Value) -> AppResult<Value> {
    let tool = match action.as_str() {
        "list" => "list_exec_tasks", "get" => "get_exec_task", "cancel" => "cancel_exec_task",
        _ => return Err(AppError::Message("不支持的任务管理操作。".into())),
    };
    let profile = state.with_workspaces(|store| store.get(&id).cloned()
        .ok_or_else(|| AppError::Message("工作区不存在。".into())))?;
    tauri::async_runtime::spawn_blocking(move || {
        let ctx = context(&profile, &channel)?;
        Ok(crate::tools::call_tool(&ctx, tool, &args))
    }).await.map_err(|_| AppError::Message("任务管理线程异常；请重新查询，不要重跑命令。".into()))?
}

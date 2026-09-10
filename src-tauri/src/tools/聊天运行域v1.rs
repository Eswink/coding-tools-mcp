//! Per-conversation runtime state; physical workspace files remain deliberately shared.
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use serde_json::{json, Value};
use crate::auth::chat::RemoteRequest;
use crate::harness::Harness;
use super::{ToolContext, session::SessionStore, exec_tasks::ExecTaskStore};
#[derive(Default)]
pub(crate) struct ChatDomains(Mutex<HashMap<String, Resources>>);
#[derive(Clone)]
struct Resources {
    cwd: Arc<Mutex<PathBuf>>, sessions: Arc<SessionStore>, tasks: Arc<ExecTaskStore>, harness: Harness,
}
impl ChatDomains {
    pub fn scoped(&self, ctx: &ToolContext, req: &RemoteRequest) -> Result<ToolContext, String> {
        let key = req.identity()?;
        let mut domains = self.0.lock().map_err(|_| "会话运行域不可用")?;
        if !domains.contains_key(key) {
            if domains.len() >= 64 { return Err("会话运行域已达到容量上限，请在所有任务终止后重启应用".into()); }
            let root = ctx.harness.store_root().join("chat-v1").join(key);
            let harness = Harness::new(ctx.workspace.root().to_path_buf(), root.clone()).map_err(|e| e.to_string())?;
            let tasks = ExecTaskStore::shared(root.join("exec-tasks-v1")); tasks.bind_profile(&req.profile);
            domains.insert(key.into(), Resources { cwd: Arc::new(Mutex::new(ctx.workspace.root().to_path_buf())),
                sessions: Arc::new(SessionStore::new()), tasks, harness });
        }
        let r = domains.get(key).unwrap();
        let mut copy = ctx.background_snapshot();
        copy.default_cwd = r.cwd.clone(); copy.sessions = r.sessions.clone();
        copy.exec_tasks = r.tasks.clone(); copy.harness = r.harness.clone(); copy.chat_scoped = true;
        Ok(copy)
    }
}
fn required(name: &str, args: &Value) -> Option<&'static [&'static str]> {
    Some(match name {
        "server_info" | "check_exec_environment" | "get_default_cwd" | "set_default_cwd" |
        "git_status" | "git_diff" | "git_log" | "git_show" | "git_blame" | "harness_status" | "operation_log" |
        "project_state" | "task_context" | "list_task_events" | "change_summary" => &["workspace.read"],
        "read_file" | "list_dir" | "list_files" | "search_text" | "grep_text" | "grep" | "view_image" | "patch_check" => &["files.read"],
        "apply_patch" => &["files.write"],
        "exec_command" | "exec_health_check" | "start_exec_task" => &["exec.run"],
        "get_exec_task" | "list_exec_tasks" | "read_output" => &["task.read"],
        "cancel_exec_task" | "kill_session" => &["task.manage"],
        "write_stdin" => &["task.manage", "exec.run"],
        "history_session_read" | "history_session_search" => &["history.read"],
        "history_session_validate" if !args.get("repair").and_then(Value::as_bool).unwrap_or(false) => &["history.read"],
        "history_session_bootstrap" | "history_session_checkpoint" | "history_session_validate" => &["history.write"],
        "start_task" | "update_task" | "pause_task" | "resume_task" | "finish_task" => &["harness.write"],
        // request_permissions is intentionally not capable of granting remote scopes.
        _ => return None,
    })
}
fn denied(code: &str) -> Value { super::workspace::tool_err_code("CHAT_AUTHORIZATION_REQUIRED", code, "permission") }
/// This hook precedes policy, cwd, Harness and every dispatch branch, including async workers.
pub(crate) fn intercept(ctx: &ToolContext, name: &str, args: &Value) -> Option<Value> {
    let req = ctx.remote_request.as_ref()?;
    if name == "auth_status" { return Some(req.service.status(req)); }
    if name == "request_chat_authorization" { return Some(req.service.request(req,args)); }
    let scopes = match required(name,args) { Some(s) => s, None => return Some(denied("REMOTE_TOOL_NOT_PERMITTED")) };
    if let Err(e) = req.service.permit(req,scopes) { return Some(denied(e)); }
    if ctx.chat_scoped { return None; }
    let domain = match ctx.chat_domains.scoped(ctx,req) { Ok(v) => v, Err(_) => return Some(denied("CHAT_RUNTIME_UNAVAILABLE")) };
    let mut scoped_args = args.clone();
    if name.starts_with("history_session_") {
        let Some(obj) = scoped_args.as_object_mut() else { return Some(denied("INVALID_ARGUMENT")); };
        let key = req.binding.as_deref().unwrap();
        let dir = format!("docs/history-session/chat-v1/{key}");
        if obj.get("history_dir").is_some_and(|v| v.as_str() != Some(&dir)) { return Some(denied("HISTORY_SCOPE_MISMATCH")); }
        obj.remove("workspace_root");
        obj.insert("history_dir".into(),json!(dir));
        obj.insert("session_key".into(),json!(key));
        obj.insert("_host_session_key".into(),json!(key));
    }
    Some(super::call_tool(&domain,name,&scoped_args))
}
pub(crate) fn auth_tools() -> Vec<Value> {
    [("auth_status", "Return only this authenticated conversation's authorization status; no workspace data."),
     ("request_chat_authorization", "Only on explicit user request, ask the LOCAL DESKTOP owner to approve this conversation. Never request passwords in chat; retries do not extend pending requests.")]
        .into_iter().map(|(name,description)| json!({
            "name":name,"description":description,
            "inputSchema":{"type":"object","properties":if name == "auth_status" { json!({}) } else {
                json!({"scopes":{"type":"array","minItems":1,"maxItems":9,"items":{"type":"string","enum":crate::auth::chat::SCOPES}}})
            },"additionalProperties":false},
            "securitySchemes":[{"type":"oauth2","scopes":["mcp"]}],
            "annotations":{"readOnlyHint":name == "auth_status","destructiveHint":false,"openWorldHint":false}
        })).collect()
}

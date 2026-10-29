//! Host-owned worktree authority. Remote arguments never supply a root or Git option.
use crate::{
    harness::worktree::{WorktreeError, WorktreeManager},
    tools::{
        workspace::{tool_ok, WorkspaceError},
        ToolContext,
    },
};
use serde_json::{json, Value};

fn error(value: WorktreeError) -> WorkspaceError {
    WorkspaceError::Tool {
        code: value.code(),
        message: value.to_string(),
        category: "security",
        retryable: false,
    }
}
fn invalid() -> WorkspaceError {
    WorkspaceError::Tool {
        code: "INVALID_ARGUMENT",
        message: "Only the managed worktree identifier is accepted.".into(),
        category: "validation",
        retryable: false,
    }
}
pub(crate) fn call(ctx: &ToolContext, name: &str, args: &Value) -> Result<Value, WorkspaceError> {
    // Root authority is supplied only by the already-admitted native request chain.
    // Hold exclusivity before any repository/ODB metadata read until all effects finish.
    let _source_root =
        crate::tools::root_work::exclusive_context(ctx).map_err(|_| WorkspaceError::Tool {
            code: "NATIVE_ROOT_UNAVAILABLE",
            message:
                "Source workspace writers are not proven quiescent; no worktree operation started."
                    .into(),
            category: "availability",
            retryable: false,
        })?;
    let args = args.as_object().ok_or_else(invalid)?;
    let id = if name == "worktree_remove" {
        if args.len() != 1 {
            return Err(invalid());
        }
        let id = args.get("id").and_then(Value::as_str).ok_or_else(invalid)?;
        if id.len() != 32
            || !id
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        {
            return Err(invalid());
        }
        Some(id)
    } else {
        if !args.is_empty() {
            return Err(invalid());
        }
        None
    };
    let manager = WorktreeManager::new(
        ctx.workspace.root(),
        ctx.harness.store_root(),
        ctx.harness.workspace_id(),
    )
    .map_err(error)?;
    let value = match name {
        "worktree_create" => json!({"worktree": manager.create_detached().map_err(error)?}),
        "worktree_list" => json!({"worktrees": manager.list().map_err(error)?}),
        "worktree_remove" => {
            manager
                .remove_clean(id.ok_or_else(invalid)?)
                .map_err(error)?;
            json!({"removed": true})
        }
        _ => return Err(invalid()),
    };
    Ok(tool_ok(value))
}

#[cfg(test)]
#[path = "worktree_tools_tests.rs"]
mod tests;

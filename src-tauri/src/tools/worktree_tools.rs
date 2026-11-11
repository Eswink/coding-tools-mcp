//! Host-owned worktree authority. Remote arguments never supply a root or Git option.
use crate::{
    harness::worktree::WorktreeError,
    tools::{
        workspace::{tool_ok, WorkspaceError},
        ToolContext,
    },
};
use serde_json::{json, Value};

fn error(value: WorktreeError) -> WorkspaceError {
    if let Some(slots) = value.legacy_slots() {
        // A1 C2-ad (N2, v5 §1.7): legacy trees alone hold all eight slots.
        return WorkspaceError::ToolDetails {
            code: value.code(),
            message: value.to_string(),
            category: "security",
            retryable: false,
            details: workers::legacy_capacity_details(slots),
        };
    }
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
    // A1 C2b (C1-b): always the main-root manager (ctx.host), never a remote
    // session's chat-v1 harness root, so every session and every worker share
    // the one device-level pool of 8 slots.
    let manager = workers::manager(ctx).map_err(|e| WorkspaceError::Tool {
        code: e.code(),
        message: e.message().into(),
        category: "security",
        retryable: false,
    })?;
    // A1 C1: worker-owned trees are managed only through the worker lifecycle.
    let owned = || {
        workers::owned_worktrees(ctx).map_err(|e| WorkspaceError::Tool {
            code: e.code(),
            message: e.message().into(),
            category: "availability",
            retryable: false,
        })
    };
    let value = match name {
        "worktree_create" => json!({"worktree": manager.create_detached().map_err(error)?}),
        "worktree_list" => {
            let owned = owned()?;
            // A1 C3: legacy chat-v1 trees are listed (marked) next to managed ones.
            let mut items = manager.list_with_legacy().map_err(error)?;
            items.retain(|item| !owned.contains(&item.id));
            json!({"worktrees": items})
        }
        "worktree_remove" => {
            let id = id.ok_or_else(invalid)?;
            // A1 C12b D2: "no worker record owns this id" is the owner proof, so
            // a marker from an interrupted fresh delete is resumed here instead of
            // leaking metadata and a slot. A1 C14 (n2): that proof and the remove
            // now share one store lock (store → native).
            match workers::remove_unowned_worktree(ctx, &manager, id).map_err(|e| {
                WorkspaceError::Tool {
                    code: e.code(),
                    message: e.message().into(),
                    category: "availability",
                    retryable: false,
                }
            })? {
                workers::UnownedRemove::Owned => {
                    return Err(WorkspaceError::Tool {
                        code: "WORKER_OWNED",
                        message: "This worktree belongs to a worker; discard the worker instead."
                            .into(),
                        category: "security",
                        retryable: false,
                    })
                }
                workers::UnownedRemove::Removed(result) => result.map_err(error)?,
            }
            json!({"removed": true})
        }
        _ => return Err(invalid()),
    };
    Ok(tool_ok(value))
}

#[cfg(test)]
#[path = "worktree_tools_tests.rs"]
mod tests;

// A1 C1: native-internal worker core, declared here so the pinned tools/mod.rs
// stays byte-identical. No MCP tool registers it yet (SPEC-A1 v4 §7.4).
#[path = "workers.rs"]
pub(crate) mod workers;

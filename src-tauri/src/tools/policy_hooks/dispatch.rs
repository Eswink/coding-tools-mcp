use super::*;
use std::{cell::Cell, time::Duration};
thread_local! {static RUNNING:Cell<bool>=const{Cell::new(false)};}
struct RecursionGuard;
impl Drop for RecursionGuard {
    fn drop(&mut self) {
        RUNNING.with(|r| r.set(false));
    }
}
fn failure(code: &'static str, before: bool, primary: Option<Value>) -> Value {
    let mut result = json!({"ok":false,"error":{"code":code,"category":"hook","retryable":false,
        "message":"A required locally configured hook did not complete successfully. Do not automatically retry."},
        "primary_started":!before,"rolled_back":false,"hook_effects_may_have_occurred":true});
    if let Some(primary) = primary {
        result["primary_result"] = primary;
    }
    result
}
/// Called only after the existing conversation interceptor and parent policy.
pub(crate) fn run<F>(ctx: &ToolContext, name: &str, args: &Value, primary: F) -> Value
where
    F: FnOnce(&ToolContext, &Value) -> Value,
{
    // Async start owns the durable logical-job reservation before any hook.
    if name == "start_exec_task" {
        return primary(ctx, args);
    }
    run_inner(ctx, name, args, primary)
}
pub(crate) fn run_reserved_async<F>(ctx: &ToolContext, args: &Value, primary: F) -> Value
where
    F: FnOnce(&ToolContext, &Value) -> Value,
{
    run_inner(ctx, "start_exec_task", args, primary)
}
fn run_inner<F>(ctx: &ToolContext, name: &str, args: &Value, primary: F) -> Value
where
    F: FnOnce(&ToolContext, &Value) -> Value,
{
    if ctx.hook_nested {
        return primary(ctx, args);
    }
    if RUNNING.with(Cell::get) {
        return failure("HOOK_RECURSION_REJECTED", true, None);
    }
    let registry = &ctx.policy_hooks;
    let (generation, hooks) = match registry.state.lock() {
        Ok(s) => {
            let hooks = s
                .hooks
                .iter()
                .filter(|h| h.spec.tool == name)
                .cloned()
                .collect::<Vec<_>>();
            if s.quarantined {
                return failure("HOOK_RECOVERY_REQUIRED", true, None);
            }
            (s.generation, hooks)
        }
        Err(_) => return failure("HOOK_RECOVERY_REQUIRED", true, None),
    };
    if hooks.is_empty() {
        return primary(ctx, args);
    }
    let Ok(_slot) = registry.invocation.try_lock() else {
        return failure("HOOK_BACKPRESSURE", true, None);
    };
    RUNNING.with(|r| r.set(true));
    let _recursion = RecursionGuard;
    let Some(request) = ctx.remote_request.as_ref() else {
        return failure("HOOK_LOCAL_AUTHORITY_REQUIRED", true, None);
    };
    let authority = match request
        .service
        .local_authority_snapshot(request, &ctx.execution_gate)
    {
        Ok(a) => a,
        Err(_) => return failure("HOOK_LOCAL_AUTHORITY_REQUIRED", true, None),
    };
    let parent_budget = Duration::from_millis(
        args.get("timeout_ms")
            .and_then(Value::as_u64)
            .unwrap_or(30000)
            .min(600000),
    );
    let deadline = ctx
        .hook_deadline
        .unwrap_or_else(|| Instant::now() + parent_budget + Duration::from_secs(16));
    let invocation = Invocation {
        ctx,
        registry,
        generation,
        deadline,
        authority,
    };
    for hook in hooks
        .iter()
        .filter(|h| h.spec.event == HookEvent::BeforeTool)
    {
        if let Err(code) = execution::execute(&invocation, hook) {
            return failure(code, true, None);
        }
    }
    if let Err(code) = invocation.current() {
        return failure(code, true, None);
    }
    let mut bounded = args.clone();
    if let Some(deadline) = ctx.hook_deadline {
        let remaining = deadline
            .saturating_duration_since(Instant::now())
            .as_millis()
            .min(u64::MAX as u128) as u64;
        if remaining == 0 {
            return failure("HOOK_CANCELLED_OR_EXPIRED", true, None);
        }
        let requested = bounded
            .get("timeout_ms")
            .and_then(Value::as_u64)
            .unwrap_or(remaining);
        // A before hook consumes admission time, not an accepted async job
        // budget. The async primary checks this deadline before durable reserve.
        if name == "exec_command" {
            bounded["timeout_ms"] = json!(requested.min(remaining));
        }
    }
    // Primary dispatch itself is not a hook and may call ordinary helpers. Any
    // nested public tool trigger while this invocation is active is rejected.
    let mut nested = ctx.background_snapshot();
    nested.hook_nested = true;
    let result = primary(&nested, &bounded);
    for hook in hooks
        .iter()
        .filter(|h| h.spec.event == HookEvent::AfterTool)
    {
        if let Err(code) = execution::execute(&invocation, hook) {
            return failure(code, false, Some(result));
        }
    }
    result
}

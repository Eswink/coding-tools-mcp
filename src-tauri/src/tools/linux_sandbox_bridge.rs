//! Mandatory isolation for Linux desktop remote command entrypoints.
//! Low-level library mechanisms are not used to manufacture local authority.
use crate::auth::chat::RuntimeAdmission;
use crate::tools::context::ToolContext;
use crate::tools::workspace::{tool_ok, WorkspaceError};
use coding_tools_local_agent::{
    Command as PolicyCommand, ExecDecision, ExecPolicy, HostExecutable, LinuxSandbox,
    PrefixRule, SandboxError, TokenPattern,
};
use serde_json::{json, Value};
use std::fmt;
use std::path::{Component, Path};
use std::sync::Arc;
use tokio::process::Command;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

const REQUIRED_SCOPES: &[&str] = &["exec.run", "files.read", "files.write"];
const MAX_ACTIVE: usize = 8;
const MAX_INPUT: usize = 64 * 1024;
const MAX_OUTPUT: u64 = 1024 * 1024;
const MAX_TIMEOUT_MS: u64 = 86_400_000;

pub(crate) struct LinuxExecutionBoundary {
    sandbox: Result<LinuxSandbox, SandboxError>,
    slots: Arc<Semaphore>,
}

impl LinuxExecutionBoundary {
    pub(crate) fn new(root: &Path) -> Self {
        Self {
            sandbox: LinuxSandbox::new(root),
            slots: Arc::new(Semaphore::new(MAX_ACTIVE)),
        }
    }
}

impl fmt::Debug for LinuxExecutionBoundary {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("LinuxExecutionBoundary(<pinned-workspace>, isolation=required)")
    }
}

pub(crate) struct SandboxExecutionGuard {
    admission: RuntimeAdmission,
    _slot: OwnedSemaphorePermit,
}

impl SandboxExecutionGuard {
    pub(crate) fn authorization_ended(&self) -> bool {
        self.admission.authorization_ended()
    }
}

impl fmt::Debug for SandboxExecutionGuard {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("SandboxExecutionGuard(<local-authority-and-capacity>)")
    }
}

pub(crate) fn required(ctx: &ToolContext) -> bool {
    ctx.remote_request.is_some()
}

fn reject(code: &'static str, category: &'static str, message: &'static str) -> WorkspaceError {
    WorkspaceError::Tool {
        code,
        message: message.into(),
        category,
        retryable: false,
    }
}

fn invalid() -> WorkspaceError {
    reject("INVALID_ARGUMENT", "validation", "Invalid sandboxed execution arguments.")
}

fn policy_error() -> WorkspaceError {
    reject("POLICY_REJECTED", "policy", "The local execution policy rejected this command.")
}

fn authority_error(code: &'static str) -> WorkspaceError {
    let category = if matches!(code, "WORKSPACE_OFFLINE" | "WORKSPACE_EXECUTION_CHANGED") {
        "availability"
    } else {
        "permission"
    };
    reject(code, category, "The current local execution admission was rejected.")
}

fn isolation_error() -> WorkspaceError {
    reject("SANDBOX_UNAVAILABLE", "security", "Required workspace isolation is unavailable; no unsandboxed retry is permitted.")
}

/// Called before builtin handling as well: model-supplied bypass fields must
/// never be silently accepted even when a particular invocation has no child.
pub(crate) fn validate_arguments(ctx: &ToolContext, args: &Value) -> Result<(), WorkspaceError> {
    if !required(ctx) {
        return Ok(());
    }
    let object = args.as_object().ok_or_else(invalid)?;
    const ALLOWED: &[&str] = &[
        "cmd", "workdir", "cwd", "filesystem_scope", "timeout_ms", "max_output_bytes",
        "yield_time_ms", "tty", "stdin", "reason", "confirm",
    ];
    if object.keys().any(|key| !ALLOWED.contains(&key.as_str()))
        || serde_json::to_vec(args).map_err(|_| invalid())?.len() > MAX_INPUT
    {
        return Err(invalid());
    }
    let command = args.get("cmd").and_then(Value::as_str).ok_or_else(invalid)?;
    if command.trim().is_empty() || command.len() > 4000 {
        return Err(invalid());
    }
    for key in ["workdir", "cwd", "filesystem_scope", "stdin", "reason"] {
        if args.get(key).is_some_and(|value| !value.is_string()) {
            return Err(invalid());
        }
    }
    for key in ["tty", "confirm"] {
        if args.get(key).is_some_and(|value| !value.is_boolean()) {
            return Err(invalid());
        }
    }
    for (key, min, max) in [
        ("timeout_ms", 1, ctx.policy.max_exec_timeout_ms.min(MAX_TIMEOUT_MS)),
        ("max_output_bytes", 1, MAX_OUTPUT),
        ("yield_time_ms", 0, 30_000),
    ] {
        if let Some(value) = args.get(key) {
            let number = value.as_u64().ok_or_else(invalid)?;
            if number < min || number > max {
                return Err(invalid());
            }
        }
    }
    if args.get("filesystem_scope").is_some_and(|value| value.as_str() != Some("workspace")) {
        return Err(invalid());
    }
    if let (Some(workdir), Some(cwd)) = (args.get("workdir"), args.get("cwd")) {
        if workdir != cwd {
            return Err(invalid());
        }
    }
    for key in ["workdir", "cwd"] {
        if let Some(value) = args.get(key).and_then(Value::as_str) {
            if Path::new(value).components().any(|part| !matches!(part, Component::Normal(_) | Component::CurDir)) {
                return Err(invalid());
            }
        }
    }
    if args.get("reason").and_then(Value::as_str).is_some_and(|value| value.len() > 512) {
        return Err(invalid());
    }
    Ok(())
}

fn host_policy(ctx: &ToolContext, program: &str) -> Result<ExecPolicy, WorkspaceError> {
    let path = Path::new(program);
    if !path.is_absolute() {
        return Err(policy_error());
    }
    let (pattern, hosts, resolve) = if path.starts_with(ctx.workspace.root()) {
        let canonical = path.canonicalize().map_err(|_| policy_error())?;
        let extension = canonical.extension().and_then(|value| value.to_str())
            .map(|value| format!(".{}", value.to_ascii_lowercase())).unwrap_or_default();
        if !ctx.policy.workspace_local_entries
            || !canonical.starts_with(ctx.workspace.root())
            || (!extension.is_empty() && !ctx.policy.workspace_script_extensions.contains(&extension))
        {
            return Err(policy_error());
        }
        (program.to_owned(), Vec::new(), false)
    } else {
        let name = path.file_name().and_then(|value| value.to_str()).ok_or_else(policy_error)?;
        if !ctx.policy.allowed_commands.contains(name) {
            return Err(policy_error());
        }
        let executable = HostExecutable::new(name, [program.to_owned()]).map_err(|_| policy_error())?;
        (name.to_owned(), vec![executable], true)
    };
    let token = TokenPattern::exact(pattern).map_err(|_| policy_error())?;
    let rule = PrefixRule::new(vec![token], ExecDecision::Allow).map_err(|_| policy_error())?;
    ExecPolicy::new(vec![rule], hosts, resolve).map_err(|_| policy_error())
}

/// Prepare the exact command object; after return only process-supervision
/// attributes may change. The final opaque admission happens after all path,
/// policy, environment and sandbox preparation, immediately before spawn.
pub(crate) fn prepare(
    ctx: &ToolContext,
    command: &mut Command,
) -> Result<Option<SandboxExecutionGuard>, WorkspaceError> {
    let Some(request) = ctx.remote_request.as_ref() else {
        return Ok(None);
    };
    if !ctx.chat_scoped {
        return Err(authority_error("LOCAL_ADMISSION_REQUIRED"));
    }
    let ticket = request.service.issue_local_admission_ticket(
        request, REQUIRED_SCOPES, &ctx.execution_gate,
    ).map_err(authority_error)?;
    let argv = std::iter::once(command.as_std().get_program())
        .chain(command.as_std().get_args())
        .map(|value| value.to_str().map(str::to_owned).ok_or_else(policy_error))
        .collect::<Result<Vec<_>, _>>()?;
    let policy = host_policy(ctx, &argv[0])?;
    let requested = PolicyCommand::new(argv).map_err(|_| policy_error())?;
    // This bridge owns the desktop permit, not a forged library invocation.
    // Only an unconditional Allow is accepted; no prompt approval is minted.
    if policy.evaluate(&requested).decision != Some(ExecDecision::Allow) {
        return Err(policy_error());
    }
    let slot = ctx.linux_execution.slots.clone().try_acquire_owned().map_err(|_| {
        reject("EXECUTION_CAPACITY_REACHED", "runtime", "Workspace execution capacity is exhausted.")
    })?;
    let sandbox = ctx.linux_execution.sandbox.as_ref().map_err(|_| isolation_error())?;
    sandbox.attach_to_command(command).map_err(|_| isolation_error())?;
    command.env("PATH", "/usr/bin:/bin")
        .env("HOME", ctx.workspace.root())
        .env("TMPDIR", ctx.workspace.root())
        .env("LANG", "C.UTF-8");
    let admission = request.service.commit_runtime_admission(
        request, &ctx.execution_gate, ticket,
    ).map_err(authority_error)?;
    if admission.authorization_ended() {
        return Err(authority_error("LOCAL_AUTHORITY_CHANGED"));
    }
    Ok(Some(SandboxExecutionGuard { admission, _slot: slot }))
}

/// This is a policy/environment report, not a claim that a probe process ran.
pub(crate) fn environment(ctx: &ToolContext) -> Result<Value, WorkspaceError> {
    let root_pinned = ctx.linux_execution.sandbox.is_ok();
    Ok(tool_ok(json!({
        "workspace": ctx.workspace.root_display(),
        "permission_mode": ctx.permission_mode,
        "network_allowed": false,
        "policy_network_allowed": ctx.policy.network_allowed(),
        "landlock_enabled": null,
        "filesystem_sandbox": {
            "required": true, "available": null, "enforced": false,
            "root_pinned": root_pinned, "validation": "checked_on_each_child_start",
            "default_scope": "workspace", "host_scope_available": false
        },
        "global_tmp_write": "denied",
        "workspace_exec_available": root_pinned,
        "workspace_exec_sandbox_enforced": false,
        "workspace_exec_boundary": "landlock_seccomp_required",
        "max_active_sandboxed_commands": MAX_ACTIVE,
        "system_command_allowlist": ctx.policy.allowed_commands.iter().cloned().collect::<Vec<_>>(),
        "allowed_commands": ctx.policy.allowed_commands.iter().cloned().collect::<Vec<_>>(),
        "workspace_local_entries": {
            "enabled": ctx.policy.workspace_local_entries,
            "script_extensions": ctx.policy.workspace_script_extensions.iter().cloned().collect::<Vec<_>>(),
            "resolution": "workdir_first"
        },
        "warnings": [
            "This report does not execute a kernel probe. Each child must establish isolation or fail closed.",
            "Workspace read/write/exec approval is required. Network is denied even in trusted permission mode.",
            "The existing desktop interactive pipe mode is not a native PTY."
        ]
    })))
}

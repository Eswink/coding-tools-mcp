//! Mandatory sandbox dispatch for a trusted host with existing local admission.
//!
//! This module does not mint admission, mount a cloud route, or restore grants.
//! Legacy low-level managers remain available to trusted code, not this surface.
mod execute;

use crate::{
    parse_arguments, Capability, Command, ExecPolicy, ExecutionAuthorization, LinuxSandbox,
    LocalAdmission, ToolCall, ToolError, ToolErrorKind, ToolExecutor, ToolFuture, ToolName,
    ToolRegistry, ToolSpec, VerifiedInvocation,
};
use serde::Deserialize;
use serde_json::json;
use std::{
    collections::BTreeSet,
    fmt,
    path::{Component, Path, PathBuf},
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::{oneshot, watch, Mutex, Semaphore};

const MAX_ACTIVE: u32 = 8;
const STREAM_LIMIT: usize = 4096;
const MAX_INPUT: usize = 64 * 1024;
const MAX_TIMEOUT_MS: u64 = 30_000;

struct Core {
    conversation: String,
    workspace: String,
    generation: u64,
    expires: u64,
    capabilities: BTreeSet<Capability>,
    root: PathBuf,
    sandbox: LinuxSandbox,
    policy: ExecPolicy,
    open: Mutex<bool>,
    stop: watch::Sender<bool>,
    slots: Arc<Semaphore>,
    processes: crate::ProcessManager,
    ptys: crate::PtyManager,
}

/// A host-owned registry in which Process/PTY isolation cannot be omitted.
///
/// Construction requires already-issued local authority; it does not create
/// authority from configuration or model arguments. Revoke is irreversible.
pub struct SandboxedDispatch {
    core: Arc<Core>,
    registry: ToolRegistry,
}

impl SandboxedDispatch {
    pub fn new(
        admission: &LocalAdmission,
        approved_workspace: impl AsRef<Path>,
        policy: ExecPolicy,
    ) -> Result<Self, ToolError> {
        let required = required_capabilities();
        if admission.conversation_id.is_empty()
            || admission.workspace_id.is_empty()
            || admission.generation == 0
            || now()? >= admission.expires_at_unix_ms
            || !required.is_subset(&admission.capabilities)
        {
            return Err(denied());
        }
        let root = std::fs::canonicalize(approved_workspace).map_err(|_| invalid())?;
        let sandbox = LinuxSandbox::new(&root).map_err(|_| execution_error())?;
        let (stop, _) = watch::channel(false);
        let core = Arc::new(Core {
            conversation: admission.conversation_id.clone(),
            workspace: admission.workspace_id.clone(),
            generation: admission.generation,
            expires: admission.expires_at_unix_ms,
            capabilities: admission.capabilities.clone(),
            root,
            sandbox,
            policy,
            open: Mutex::new(true),
            stop,
            slots: Arc::new(Semaphore::new(MAX_ACTIVE as usize)),
            processes: crate::ProcessManager::new(MAX_ACTIVE as usize)
                .map_err(|_| execution_error())?,
            ptys: crate::PtyManager::new(MAX_ACTIVE as usize).map_err(|_| execution_error())?,
        });
        let mut registry = ToolRegistry::new();
        for pty in [false, true] {
            registry.register(Arc::new(Executor {
                core: core.clone(),
                pty,
            }))?;
        }
        Ok(Self { core, registry })
    }

    pub fn invoke<'a>(
        &'a self,
        call: &'a ToolCall,
        admission: &'a LocalAdmission,
    ) -> ToolFuture<'a> {
        Box::pin(async move {
            if *self.core.stop.borrow()
                || call.conversation_id != self.core.conversation
                || call.workspace_id != self.core.workspace
                || admission.generation != self.core.generation
                || !admission.capabilities.is_subset(&self.core.capabilities)
                || now()? >= self.core.expires.min(admission.expires_at_unix_ms)
            {
                return Err(denied());
            }
            self.registry.invoke(call, admission, now()?).await
        })
    }

    /// Close admission, cancel committed work, and await bounded cleanup.
    /// A cleanup timeout is explicit uncertainty, never proof of no execution.
    pub async fn revoke(&self) -> Result<(), ToolError> {
        self.revoke_bounded(Duration::from_secs(15)).await
    }

    async fn revoke_bounded(&self, timeout: Duration) -> Result<(), ToolError> {
        // Publish the permanent fence before waiting for an in-progress start.
        // A start that already passed its locked check is in flight, not a new
        // post-revocation admission; its owner still completes and cancels it.
        self.core.stop.send_replace(true);
        tokio::time::timeout(timeout, async {
            {
                let mut open = self.core.open.lock().await;
                *open = false;
            }
            let _drained = self.core.slots.clone().acquire_many_owned(MAX_ACTIVE)
                .await.map_err(|_| execution_error())?;
            Ok(())
        })
        .await
        .map_err(|_| ToolError::new(ToolErrorKind::Execution, "sandbox cleanup uncertain"))?
    }

}

impl Drop for SandboxedDispatch {
    fn drop(&mut self) {
        // Workers retain ownership through any spawn_blocking operation, then
        // observe this signal and close their sessions. No abort of a PTY start.
        self.core.stop.send_replace(true);
    }
}

impl fmt::Debug for SandboxedDispatch {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("SandboxedDispatch(<local-binding>, isolation=required)")
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Arguments {
    argv: Vec<String>,
    #[serde(default = "default_cwd")]
    cwd: PathBuf,
    #[serde(default)]
    stdin: String,
    #[serde(default = "default_timeout")]
    timeout_ms: u64,
    #[serde(default)]
    columns: Option<u16>,
    #[serde(default)]
    rows: Option<u16>,
}
fn default_cwd() -> PathBuf {
    PathBuf::from(".")
}
fn default_timeout() -> u64 {
    MAX_TIMEOUT_MS
}

struct Executor {
    core: Arc<Core>,
    pty: bool,
}

impl ToolExecutor for Executor {
    fn tool_name(&self) -> ToolName {
        ToolName::parse(if self.pty { "sandbox_pty" } else { "sandbox_exec" })
            .expect("constant tool name")
    }
    fn spec(&self) -> ToolSpec {
        ToolSpec::new(
            self.tool_name(),
            "Execute under existing local authority and mandatory workspace isolation",
            json!({"type":"object","additionalProperties":false,"required":["argv"],
                "properties":{"argv":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":128},
                "cwd":{"type":"string"},"stdin":{"type":"string"},
                "timeout_ms":{"type":"integer","minimum":1,"maximum":30000},
                "columns":{"type":"integer","minimum":1,"maximum":500},
                "rows":{"type":"integer","minimum":1,"maximum":500}}}),
        )
        .expect("constant tool spec")
        .require(Capability::ProcessExec)
        .require(Capability::WorkspaceRead)
        .require(Capability::WorkspaceWrite)
    }
    fn execute<'a>(
        &'a self,
        call: &'a ToolCall,
        verified: VerifiedInvocation<'a>,
    ) -> ToolFuture<'a> {
        Box::pin(async move {
            let args: Arguments = parse_arguments(&call.arguments, MAX_INPUT)?;
            if args.cwd.is_absolute()
                || args.cwd.components().any(|part| {
                    !matches!(part, Component::Normal(_) | Component::CurDir)
                })
                || args.timeout_ms == 0
                || args.timeout_ms > MAX_TIMEOUT_MS
                || args.stdin.len() > 4096
                || args.columns.is_some_and(|value| value == 0 || value > 500)
                || args.rows.is_some_and(|value| value == 0 || value > 500)
                || (!self.pty && (args.columns.is_some() || args.rows.is_some()))
            {
                return Err(invalid());
            }
            let command = Command::new(args.argv.clone()).map_err(|_| invalid())?;
            let time = now()?;
            let expires = self.core.expires.min(verified.expires_at_unix_ms());
            if time >= expires || verified.generation() != self.core.generation {
                return Err(denied());
            }
            match self.core.policy.authorize(&command, call, &verified, None, time) {
                ExecutionAuthorization::Allowed => {}
                ExecutionAuthorization::Forbidden => {
                    return Err(ToolError::new(ToolErrorKind::CapabilityDenied, "execution policy forbids command"));
                }
                ExecutionAuthorization::ApprovalRequired => return Err(denied()),
                ExecutionAuthorization::NoMatchingRule => return Err(denied()),
            }
            let slot = self.core.slots.clone().try_acquire_owned().map_err(|_| {
                ToolError::new(ToolErrorKind::Execution, "local execution capacity exhausted")
            })?;
            let (reply, receive) = oneshot::channel();
            let core = self.core.clone();
            let pty = self.pty;
            // This owned supervisor, not the caller's cancellable future, owns
            // a possibly blocking PTY launch and the resulting child session.
            tokio::spawn(async move {
                execute::run(core, pty, args, expires, reply, slot).await;
            });
            receive.await.map_err(|_| execution_error())?
        })
    }
}

fn required_capabilities() -> BTreeSet<Capability> {
    [Capability::ProcessExec, Capability::WorkspaceRead, Capability::WorkspaceWrite]
        .into_iter().collect()
}
fn now() -> Result<u64, ToolError> {
    SystemTime::now().duration_since(UNIX_EPOCH)
        .ok().and_then(|duration| u64::try_from(duration.as_millis()).ok())
        .ok_or_else(denied)
}
fn denied() -> ToolError {
    ToolError::new(ToolErrorKind::Unauthorized, "local sandbox admission rejected")
}
fn invalid() -> ToolError {
    ToolError::new(ToolErrorKind::InvalidInput, "invalid sandboxed command")
}
fn execution_error() -> ToolError {
    ToolError::new(ToolErrorKind::Execution, "sandboxed execution unavailable")
}

#[cfg(all(test, target_arch = "x86_64"))]
mod tests;

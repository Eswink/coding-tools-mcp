//! Native-approved hooks are bounded operations, never authorization sources.
use super::ToolContext;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
    time::Instant,
};
use uuid::Uuid;
mod artifacts;
mod dispatch;
mod execution;
pub(crate) use dispatch::{run, run_reserved_async};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum HookEvent {
    BeforeTool,
    AfterTool,
}
fn default_cwd() -> String {
    ".".into()
}
fn default_timeout() -> u64 {
    1000
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct HookSpec {
    pub id: String,
    pub event: HookEvent,
    pub tool: String,
    pub executable: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default = "default_cwd")]
    pub cwd: String,
    #[serde(default)]
    pub script: Option<String>,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
    #[serde(default)]
    pub workspace_write: bool,
}
pub(super) struct RegisteredHook {
    spec: HookSpec,
    executable: artifacts::Artifact,
    script: Option<artifacts::Script>,
    #[cfg(target_os = "linux")]
    argv: Vec<String>,
    #[cfg(target_os = "linux")]
    policy_argv: Vec<String>,
    #[cfg(target_os = "linux")]
    cwd: PathBuf,
    #[cfg(target_os = "linux")]
    policy: coding_tools_local_agent::ExecPolicy,
}
impl RegisteredHook {
    fn recheck(&self) -> Result<(), &'static str> {
        self.executable.recheck()?;
        if let Some(script) = &self.script {
            script.recheck()?;
        }
        Ok(())
    }
}
/// Preview only. Not cloneable/deserializable and confers no execution authority.
pub(crate) struct PreparedHooks {
    registry: Uuid,
    root: PathBuf,
    generation: u64,
    validated: Option<Instant>,
    digest: String,
    hooks: Vec<Arc<RegisteredHook>>,
}
impl PreparedHooks {
    pub(crate) fn revalidate(&mut self) -> Result<(), &'static str> {
        self.validated = None;
        for hook in &self.hooks {
            hook.recheck()?;
        }
        self.validated = Some(Instant::now());
        Ok(())
    }
    pub(crate) fn digest(&self) -> &str {
        &self.digest
    }
    pub(crate) fn preview(&self) -> Value {
        json!({"digest":self.digest,"hooks":self.hooks.iter().map(|hook|json!({
            "manifest":hook.spec,"executable_sha256":hook.executable.digest,
            "script_sha256":hook.script.as_ref().map(|s|&s.digest),
            "script_source":hook.script.as_ref().map(|s|String::from_utf8_lossy(&s.bytes))
        })).collect::<Vec<_>>(),"runtime_only":true,"network_allowed":false,"required_parent_scope":"exec.run","requires_local_conversation_authority":true})
    }
}
struct State {
    generation: u64,
    hooks: Vec<Arc<RegisteredHook>>,
    quarantined: bool,
    uncertain_admissions: Vec<crate::auth::LocalAdmissionPermit>,
}
pub(crate) struct HookRegistry {
    id: Uuid,
    root: PathBuf,
    state: Mutex<State>,
    invocation: Mutex<()>,
}
impl HookRegistry {
    pub(crate) fn new(root: PathBuf) -> Self {
        Self {
            id: Uuid::new_v4(),
            root,
            state: Mutex::new(State {
                generation: 1,
                hooks: Vec::new(),
                quarantined: false,
                uncertain_admissions: Vec::new(),
            }),
            invocation: Mutex::new(()),
        }
    }
    pub(crate) fn prepare(
        &self,
        ctx: &ToolContext,
        specs: Vec<HookSpec>,
    ) -> Result<PreparedHooks, &'static str> {
        if ctx.workspace.root() != self.root
            || specs.len() > 8
            || serde_json::to_vec(&specs).map_or(true, |v| v.len() > 8192)
        {
            return Err("HOOK_MANIFEST_INVALID");
        }
        let mut ids = std::collections::BTreeSet::new();
        let mut hooks = Vec::new();
        for spec in specs {
            if spec.id.is_empty()
                || spec.id.len() > 64
                || !spec
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
                || !ids.insert(spec.id.clone())
                || !matches!(spec.tool.as_str(), "exec_command" | "start_exec_task")
                || !(1..=2000).contains(&spec.timeout_ms)
                || spec.args.len() > 16
                || spec
                    .args
                    .iter()
                    .any(|s| s.is_empty() || s.len() > 1024 || s.chars().any(char::is_control))
            {
                return Err("HOOK_MANIFEST_INVALID");
            }
            hooks.push(Arc::new(artifacts::prepare(ctx, spec)?));
        }
        hooks.sort_by(|a, b| a.spec.id.cmp(&b.spec.id));
        let generation = self
            .state
            .lock()
            .map_err(|_| "HOOK_RECOVERY_REQUIRED")?
            .generation;
        let mut prepared = PreparedHooks {
            registry: self.id,
            root: self.root.clone(),
            generation,
            validated: None,
            digest: String::new(),
            hooks,
        };
        prepared.digest = artifacts::hash(
            &serde_json::to_vec(
                &json!({"registry":self.id,"root":self.root,"manifest":prepared.preview()}),
            )
            .map_err(|_| "HOOK_MANIFEST_INVALID")?,
        );
        Ok(prepared)
    }
    /// Only the native owner-confirmed live-listener path may consume a preview.
    #[cfg(test)]
    pub(crate) fn install(&self, mut prepared: PreparedHooks) -> Result<Value, &'static str> {
        prepared.revalidate()?;
        self.install_prevalidated(prepared)
    }
    /// Pure state commit for the short native listener lease callback. All file
    /// I/O precedes this callback; every execution independently revalidates.
    pub(crate) fn install_prevalidated(
        &self,
        prepared: PreparedHooks,
    ) -> Result<Value, &'static str> {
        if prepared.registry != self.id
            || prepared.root != self.root
            || prepared
                .validated
                .is_none_or(|at| at.elapsed() > std::time::Duration::from_secs(5))
        {
            return Err("HOOK_CONTEXT_CHANGED");
        }
        let mut state = self.state.lock().map_err(|_| "HOOK_RECOVERY_REQUIRED")?;
        if state.quarantined {
            return Err("HOOK_RECOVERY_REQUIRED");
        }
        if state.generation != prepared.generation {
            return Err("HOOK_CONTEXT_CHANGED");
        }
        state.generation = state
            .generation
            .checked_add(1)
            .ok_or("HOOK_RECOVERY_REQUIRED")?;
        state.hooks = prepared.hooks;
        Ok(
            json!({"enabled":!state.hooks.is_empty(),"count":state.hooks.len(),"generation":state.generation,"runtime_only":true}),
        )
    }
    pub(crate) fn disable(&self) -> Result<Value, &'static str> {
        let mut state = self.state.lock().map_err(|_| "HOOK_RECOVERY_REQUIRED")?;
        state.generation = state
            .generation
            .checked_add(1)
            .ok_or("HOOK_RECOVERY_REQUIRED")?;
        state.hooks.clear();
        Ok(
            json!({"enabled":false,"generation":state.generation,"recovery_required":state.quarantined}),
        )
    }
    pub(crate) fn status(&self) -> Value {
        match self.state.lock() {
            Ok(s) => {
                json!({"enabled":!s.hooks.is_empty(),"count":s.hooks.len(),"generation":s.generation,"recovery_required":s.quarantined})
            }
            Err(_) => json!({"enabled":false,"recovery_required":true}),
        }
    }
    #[cfg(target_os = "linux")]
    fn retain_uncertain(&self, permit: crate::auth::LocalAdmissionPermit) {
        let mut state = self
            .state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        state.quarantined = true;
        // Only one serialized invocation can reach uncertainty; subsequent
        // invocations/configuration are rejected, so this collection is bounded.
        state.uncertain_admissions.push(permit);
    }
    #[cfg(target_os = "linux")]
    fn quarantine(&self) {
        if let Ok(mut state) = self.state.lock() {
            state.quarantined = true;
        }
    }
}
impl Drop for HookRegistry {
    fn drop(&mut self) {
        let state = self
            .state
            .get_mut()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        // Losing a context is not a termination receipt. Preserve native
        // occupancy through this process lifetime rather than granting a new
        // owner on an uncertain child. Restart uses existing native recovery.
        for permit in state.uncertain_admissions.drain(..) {
            std::mem::forget(permit);
        }
    }
}
#[cfg(all(test, target_os = "linux"))]
pub(crate) use execution::simulate_uncertain_retirement;

struct Invocation<'a> {
    ctx: &'a ToolContext,
    registry: &'a HookRegistry,
    generation: u64,
    deadline: Instant,
    authority: crate::auth::LocalAuthoritySnapshot,
}
impl Invocation<'_> {
    fn current(&self) -> Result<(), &'static str> {
        if self.ctx.workspace.root() != self.registry.root {
            return Err("HOOK_CONTEXT_CHANGED");
        }
        if Instant::now() >= self.deadline
            || self
                .ctx
                .hook_cancel
                .as_ref()
                .is_some_and(|c| *c.borrow() || c.has_changed().is_err())
        {
            return Err("HOOK_CANCELLED_OR_EXPIRED");
        }
        let state = self
            .registry
            .state
            .lock()
            .map_err(|_| "HOOK_RECOVERY_REQUIRED")?;
        if state.quarantined || state.generation != self.generation {
            return Err("HOOK_CONTEXT_CHANGED");
        }
        drop(state);
        let req = self
            .ctx
            .remote_request
            .as_ref()
            .ok_or("HOOK_LOCAL_AUTHORITY_REQUIRED")?;
        req.identity()?;
        req.service.permit(req, &["exec.run"])?;
        let current = req
            .service
            .local_authority_snapshot(req, &self.ctx.execution_gate)?;
        if !self.authority.same_authority(&current)
            || current.phase() != crate::auth::LocalAuthorityPhase::Active
            || current.execution_state() != crate::auth::LocalExecutionState::Online
        {
            return Err("HOOK_LOCAL_AUTHORITY_CHANGED");
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests;

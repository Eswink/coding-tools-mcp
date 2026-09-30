//! Native-owned final admission adapter for an authenticated cloud conversation.
//!
//! This module exposes no HTTP approval or process spawning entry. The owner
//! supplies the existing workspace runtime context and authorizer. The outer
//! HostAgent journal must durably claim a request before calling execute;
//! PreparedCall alone is process-local, not a durable exactly-once guarantee.
pub(crate) mod live;
use super::{chat_domain, ToolContext};
use crate::auth::{
    chat::{ChatAuthorizer, RemoteRequest},
    cloud_context::CloudTransport,
    LocalAdmissionTicket, LocalAuthorityPhase, LocalAuthoritySnapshot, LocalExecutionState,
};
use serde_json::{json, Value};
use std::{
    sync::Arc,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use uuid::Uuid;

const MAX_ARGUMENT_BYTES: usize = 4096;
const MAX_OUTPUT_BYTES: usize = 8192;
const MAX_DEADLINE_SECONDS: u64 = 300;

/// Native-created and non-deserializable. It cannot be supplied as tool args.
#[derive(Clone)]
pub(crate) struct NativeAuthority {
    host: Uuid,
    conversation: String,
    view: LocalAuthoritySnapshot,
}
impl std::fmt::Debug for NativeAuthority {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("NativeAuthority([REDACTED])")
    }
}

/// Owns immutable arguments and an opaque, non-cloneable native ticket.
pub(crate) struct PreparedCall {
    host: Uuid,
    authority: NativeAuthority,
    request: RemoteRequest,
    ticket: LocalAdmissionTicket,
    tool: String,
    args: Value,
    deadline: Instant,
    deadline_epoch: u64,
}
impl std::fmt::Debug for PreparedCall {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("PreparedCall([REDACTED])")
    }
}

/// This must use the workspace's CURRENT runtime context, not construct a new
/// gate. Creating an unrelated ToolContext would miss the native Pause control.
pub(crate) struct NativeToolHost {
    id: Uuid,
    profile: String,
    context: Arc<ToolContext>,
    link: CloudTransport,
    authorizer: Arc<ChatAuthorizer>,
}
fn now() -> Result<u64, &'static str> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|x| x.as_secs())
        .map_err(|_| "LOCAL_CLOCK_UNAVAILABLE")
}
fn fixed_error(code: &'static str) -> Value {
    json!({"ok":false,"error":{"code":code,"category":"permission","retryable":false,
        "message":"The locally approved execution boundary rejected this request."}})
}
impl NativeToolHost {
    pub(crate) fn new(
        profile: &str,
        context: Arc<ToolContext>,
        link: CloudTransport,
        authorizer: Arc<ChatAuthorizer>,
    ) -> Result<Self, &'static str> {
        if context.remote_request.is_some()
            || !link.for_workspace(profile, context.workspace.root())
        {
            return Err("CLOUD_HOST_CONTEXT_REJECTED");
        }
        Ok(Self {
            id: Uuid::new_v4(),
            profile: profile.into(),
            context,
            link,
            authorizer,
        })
    }

    fn request(&self, conversation: &str) -> Result<RemoteRequest, &'static str> {
        self.link.request(conversation, self.authorizer.clone())
    }

    /// At most an existing-authorizer pending request; never native approval.
    /// Pause/foreign/recovery/exclusivity and pending limits remain in the
    /// existing call_tool interceptor. Link expiry is checked first.
    pub(crate) fn request_authorization(&self, conversation: &str, args: &Value) -> Value {
        let req = match self.request(conversation) {
            Ok(req) => req,
            Err(code) => return fixed_error(code),
        };
        if serde_json::to_vec(args).map_or(true, |x| x.len() > MAX_ARGUMENT_BYTES) {
            return fixed_error("CLOUD_ARGUMENTS_REJECTED");
        }
        let mut context = self.context.background_snapshot();
        context.remote_request = Some(req);
        super::call_tool(&context, "request_chat_authorization", args)
    }

    pub(crate) fn authority(&self, conversation: &str) -> Result<NativeAuthority, &'static str> {
        let req = self.request(conversation)?;
        let view = self
            .authorizer
            .local_authority_snapshot(&req, &self.context.execution_gate)?;
        Ok(NativeAuthority {
            host: self.id,
            conversation: conversation.into(),
            view,
        })
    }

    fn current(&self, authority: &NativeAuthority) -> Result<LocalAuthoritySnapshot, &'static str> {
        if authority.host != self.id {
            return Err("CLOUD_HOST_CONTEXT_REJECTED");
        }
        let req = self.request(&authority.conversation)?;
        let current = self
            .authorizer
            .local_authority_snapshot(&req, &self.context.execution_gate)?;
        if !authority.view.same_authority(&current)
            || current.phase() != LocalAuthorityPhase::Active
            || current.execution_state() != LocalExecutionState::Online
            || current.deadline() <= now()?
            || authority.view.deadline() <= now()?
        {
            return Err("LOCAL_AUTHORITY_CHANGED");
        }
        Ok(current)
    }

    pub(crate) fn prepare(
        &self,
        authority: &NativeAuthority,
        tool: &str,
        args: &Value,
        deadline: u64,
    ) -> Result<PreparedCall, &'static str> {
        self.current(authority)?;
        let started = Instant::now();
        let timestamp = now()?;
        if deadline <= timestamp
            || deadline - timestamp > MAX_DEADLINE_SECONDS
            || deadline > authority.view.deadline()
        {
            return Err("CLOUD_DEADLINE_REJECTED");
        }
        let obj = args.as_object().ok_or("CLOUD_ARGUMENTS_REJECTED")?;
        if serde_json::to_vec(args).map_or(true, |x| x.len() > MAX_ARGUMENT_BYTES)
            || obj.keys().any(|key| {
                matches!(
                    key.as_str(),
                    "sandbox"
                        | "disable_sandbox"
                        | "env"
                        | "environment"
                        | "authorized"
                        | "workspace_root"
                        | "_host_session_key"
                        | "_meta"
                        | "cloud"
                )
            })
            || obj
                .get("filesystem_scope")
                .is_some_and(|v| v != "workspace")
        {
            return Err("CLOUD_ARGUMENTS_REJECTED");
        }
        // Native file-reading APIs may accept explicitly external paths for
        // trusted local use. A cloud caller never inherits that local feature.
        for key in ["path", "workdir", "directory", "cwd", "history_dir"] {
            if let Some(value) = obj.get(key) {
                let text = value.as_str().ok_or("CLOUD_ARGUMENTS_REJECTED")?;
                self.context
                    .workspace
                    .reject_unsafe_text(text)
                    .map_err(|_| "CLOUD_ARGUMENTS_REJECTED")?;
                // Existing paths must also survive canonical containment.
                let candidate = self.context.workspace.root().join(text);
                if (candidate.exists() || candidate.is_symlink())
                    && self.context.workspace.resolve_existing(text).is_err()
                {
                    return Err("CLOUD_ARGUMENTS_REJECTED");
                }
            }
        }
        let scopes = chat_domain::required(tool, args).ok_or("REMOTE_TOOL_NOT_PERMITTED")?;
        if scopes.iter().any(|s| !authority.view.scopes().contains(*s)) {
            return Err("INSUFFICIENT_CHAT_SCOPE");
        }
        // Windows native sandbox remains an unmet full-release gate. Do not
        // expose the legacy Windows policy-only process path as cloud isolation.
        if scopes.contains(&"exec.run") && !cfg!(target_os = "linux") {
            return Err("SANDBOX_REQUIRED");
        }
        let request = self.request(&authority.conversation)?;
        let ticket = self.authorizer.issue_local_admission_ticket(
            &request,
            scopes,
            &self.context.execution_gate,
        )?;
        Ok(PreparedCall {
            host: self.id,
            authority: authority.clone(),
            request,
            ticket,
            tool: tool.into(),
            args: args.clone(),
            deadline: started + Duration::from_secs(deadline - timestamp),
            deadline_epoch: deadline,
        })
    }

    /// The outer durable claim must happen before this consumes its ticket.
    /// A cancellation/transport failure after this point is UNKNOWN, not a
    /// signal to replay. The caller must retain this work until it terminates.
    pub(crate) fn execute(&self, call: PreparedCall) -> Result<Value, &'static str> {
        self.execute_scoped(call, None)
    }

    fn execute_scoped(&self, call: PreparedCall,
        work: Option<coding_tools_cloud_agent::work::WorkScope>) -> Result<Value, &'static str> {
        if call.host != self.id || call.request.profile != self.profile {
            return Err("CLOUD_HOST_CONTEXT_REJECTED");
        }
        if Instant::now() >= call.deadline || now()? >= call.deadline_epoch {
            return Err("CLOUD_DEADLINE_REJECTED");
        }
        self.current(&call.authority)?;
        // Do not replace the request with a newly authenticated generation.
        call.request.identity()?;
        let _permit = self.authorizer.commit_local_admission(
            &call.request,
            &self.context.execution_gate,
            call.ticket,
        )?;
        // The final ticket may have waited on the authorizer/gate mutexes.
        if Instant::now() >= call.deadline || now()? >= call.deadline_epoch {
            return Err("CLOUD_DEADLINE_REJECTED");
        }
        let mut context = self.context.background_snapshot();
        context.remote_request = Some(call.request);
        context.native_work = work.clone();
        let _thread = super::native_drain::enter(work);
        let mut args = call.args;
        if matches!(call.tool.as_str(), "exec_command" | "start_exec_task") {
            let remaining = call
                .deadline
                .saturating_duration_since(Instant::now())
                .as_millis()
                .min(u64::MAX as u128) as u64;
            if remaining == 0 {
                return Err("CLOUD_DEADLINE_REJECTED");
            }
            let requested = args
                .get("timeout_ms")
                .and_then(Value::as_u64)
                .unwrap_or(remaining);
            args["timeout_ms"] = json!(remaining.min(requested));
        }
        let result = super::call_tool(&context, &call.tool, &args);
        // Revocation/connection change after an operation may hide its result;
        // it cannot erase the durable outer claim or assert non-execution.
        if Instant::now() >= call.deadline
            || now()? >= call.deadline_epoch
            || context
                .remote_request
                .as_ref()
                .is_none_or(|req| req.identity().is_err())
            || self.current(&call.authority).is_err()
        {
            return Err("CLOUD_EXECUTION_UNKNOWN");
        }
        if serde_json::to_vec(&result).map_or(true, |x| x.len() > MAX_OUTPUT_BYTES) {
            return Err("CLOUD_EXECUTION_UNKNOWN");
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests;

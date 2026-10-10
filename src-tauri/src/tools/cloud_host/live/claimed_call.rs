//! Concrete actual HostAgent caller. No public mint and no workspace/VM seal.
use super::{now, rejected, NativeLivePermit, NativePrepared, NativeToolHost};
use coding_tools_cloud_agent::{
    agent::{host::ClaimedDispatch, AgentError},
    execution::ExecutionRequest,
    work::WorkScope,
};
use serde_json::{json, Value};
use std::sync::Arc;
use tokio::sync::watch;

/// Own the actual native prepared ticket, real durable claim and work scope in
/// one callback. A plain WorkScope is deliberately not an alternate constructor.
pub(super) struct ClaimedNativeCall {
    permit: NativeLivePermit,
    request: ExecutionRequest,
    claimed: ClaimedDispatch,
    work: WorkScope,
}
impl ClaimedNativeCall {
    pub(super) fn new(
        permit: NativeLivePermit,
        request: ExecutionRequest,
        claimed: ClaimedDispatch,
        work: WorkScope,
        cancelled: &watch::Receiver<bool>,
    ) -> Result<Self, AgentError> {
        if permit.binding != request.binding || *cancelled.borrow() {
            return Err(AgentError::ExecutionUnknown);
        }
        claimed.verify_request(
            &request,
            i64::try_from(now().map_err(rejected)?).map_err(rejected)?,
        )?;
        Ok(Self {
            permit,
            request,
            claimed,
            work,
        })
    }
    pub(super) fn execute(
        self,
        tools: Arc<NativeToolHost>,
        cancelled: watch::Receiver<bool>,
    ) -> Result<Value, AgentError> {
        let Self {
            permit,
            request,
            claimed,
            work,
        } = self;
        claimed.verify_request(
            &request,
            i64::try_from(now().map_err(rejected)?).map_err(rejected)?,
        )?;
        if *cancelled.borrow() {
            return Err(AgentError::ExecutionUnknown);
        }
        match permit.prepared {
            #[cfg(windows)]
            NativePrepared::Workspace(admission) => tools
                .execute_claimed_windows_workspace(admission, request, claimed, work, cancelled)
                .map_err(|_| AgentError::ExecutionUnknown),
            NativePrepared::Tool(prepared) => {
                let probe = request.binding.tool == "workspace_probe";
                let result = tools
                    .execute_scoped(prepared, Some(work), Some(cancelled.clone()))
                    .map_err(|_| AgentError::ExecutionUnknown)?;
                if *cancelled.borrow() {
                    return Err(AgentError::ExecutionUnknown);
                }
                claimed.verify_request(
                    &request,
                    i64::try_from(now().map_err(rejected)?).map_err(rejected)?,
                )?;
                if probe && result["ok"] == true {
                    Ok(
                        json!({"ok":true,"workspace_available":true,"execution":"native_tool_dispatch"}),
                    )
                } else {
                    Ok(result)
                }
            }
        }
    }
}

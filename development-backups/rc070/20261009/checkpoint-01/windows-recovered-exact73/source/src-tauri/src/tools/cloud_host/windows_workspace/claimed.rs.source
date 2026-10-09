//! Only the actual claimed native callback can consume this real local ticket.
use super::{owned_run, WorkspaceRunGrant, SCOPES};
use crate::{
    auth::{chat::RemoteRequest, cloud_context::CloudPeer, LocalAdmissionTicket},
    tools::cloud_host::{now, NativeAuthority, NativeToolHost, MAX_DEADLINE_SECONDS},
};
use coding_tools_cloud_agent::{
    agent::host::ClaimedDispatch, catalog::WorkspaceIo, execution::ExecutionRequest,
    work::WorkScope,
};
use serde_json::{json, Value};
use std::time::{Duration, Instant};
use tokio::sync::watch;

/// Actual admission data/ticket, not Clone/Deserialize and not a VM seal.
pub(crate) struct WorkspaceAdmission {
    host: uuid::Uuid,
    authority: NativeAuthority,
    remote: RemoteRequest,
    ticket: LocalAdmissionTicket,
    request: ExecutionRequest,
    intent: WorkspaceIo,
    deadline: Instant,
    deadline_epoch: u64,
    #[cfg(test)]
    creation_fixture: Option<owned_run::hcs::CreationFixture>,
}
fn peer(request: &ExecutionRequest) -> Result<CloudPeer, &'static str> {
    let p = &request.binding.peer;
    Ok(CloudPeer {
        connector: p.connector,
        device: p.device,
        device_epoch: u64::try_from(p.device_epoch).map_err(|_| "CLOUD_HOST_CONTEXT_REJECTED")?,
        gateway_boot: p.gateway_boot,
        session: p.channel_session,
        generation: u64::try_from(p.channel_generation)
            .map_err(|_| "CLOUD_HOST_CONTEXT_REJECTED")?,
    })
}
impl NativeToolHost {
    pub(crate) fn prepare_claimed_windows_workspace(
        &self,
        authority: &NativeAuthority,
        request: &ExecutionRequest,
    ) -> Result<WorkspaceAdmission, &'static str> {
        self.current(authority)?;
        let spec = coding_tools_cloud_agent::catalog::tool(&request.binding.tool)
            .ok_or("CLOUD_ARGUMENTS_REJECTED")?;
        spec.validate(&request.arguments)
            .map_err(|_| "CLOUD_ARGUMENTS_REJECTED")?;
        let intent = WorkspaceIo::from_arguments(&request.arguments)
            .map_err(|_| "CLOUD_ARGUMENTS_REJECTED")?
            .ok_or("WINDOWS_WORKSPACE_INTENT_REQUIRED")?;
        let timestamp = now()?;
        let deadline_epoch =
            u64::try_from(request.binding.deadline).map_err(|_| "CLOUD_DEADLINE_REJECTED")?;
        if request.binding.tool != "exec_command"
            || request.binding.scope != "exec.run"
            || request.binding.conversation != authority.conversation
            || !self.link.matches(&peer(request)?)
            || deadline_epoch <= timestamp
            || deadline_epoch - timestamp > MAX_DEADLINE_SECONDS
            || deadline_epoch > authority.view.deadline()
            || SCOPES
                .iter()
                .any(|scope| !authority.view.scopes().contains(*scope))
        {
            return Err("CLOUD_WORKSPACE_ADMISSION_REJECTED");
        }
        request
            .validate_at(
                &request.binding.peer,
                i64::try_from(timestamp).map_err(|_| "CLOUD_DEADLINE_REJECTED")?,
            )
            .map_err(|_| "CLOUD_ARGUMENTS_REJECTED")?;
        let remote = self.request(&authority.conversation)?;
        if remote.profile != self.profile || remote.identity()? != request.binding.conversation {
            return Err("CLOUD_HOST_CONTEXT_REJECTED");
        }
        let ticket = self.authorizer.issue_local_admission_ticket(
            &remote,
            &SCOPES,
            &self.context.execution_gate,
        )?;
        Ok(WorkspaceAdmission {
            host: self.id,
            authority: authority.clone(),
            remote,
            ticket,
            request: request.clone(),
            intent,
            deadline: Instant::now() + Duration::from_secs(deadline_epoch - timestamp),
            deadline_epoch,
            #[cfg(test)]
            // Normally absent. Explicit native CI registration is one-shot,
            // exact-host/exact-arguments and still contains no permission.
            creation_fixture: owned_run::hcs::take_creation_fixture(self.id, &request.arguments)?,
        })
    }
    pub(crate) fn execute_claimed_windows_workspace(
        &self,
        call: WorkspaceAdmission,
        request: ExecutionRequest,
        claimed: ClaimedDispatch,
        work: WorkScope,
        cancelled: watch::Receiver<bool>,
    ) -> Result<Value, &'static str> {
        let timestamp = now()?;
        claimed
            .verify_request(
                &request,
                i64::try_from(timestamp).map_err(|_| "CLOUD_DEADLINE_REJECTED")?,
            )
            .map_err(|_| "CLOUD_WORKSPACE_CLAIM_REJECTED")?;
        let intent = WorkspaceIo::from_arguments(&request.arguments)
            .map_err(|_| "CLOUD_ARGUMENTS_REJECTED")?
            .ok_or("WINDOWS_WORKSPACE_INTENT_REQUIRED")?;
        if call.host != self.id
            || call.remote.profile != self.profile
            || call.request.binding != request.binding
            || call.request.arguments != request.arguments
            || call.intent != intent
            || !self.link.matches(&peer(&request)?)
            || Instant::now() >= call.deadline
            || timestamp >= call.deadline_epoch
            || *cancelled.borrow()
        {
            return Err("CLOUD_WORKSPACE_ADMISSION_REJECTED");
        }
        self.current(&call.authority)?;
        if call.remote.identity()? != request.binding.conversation {
            return Err("CLOUD_HOST_CONTEXT_REJECTED");
        }
        let root = self.windows_input.as_ref().map_err(|code| *code)?.clone();
        let source = crate::tools::windows_vm::input::native_source()?;
        let binding = owned_run::RunBinding {
            host: self.id.to_string(),
            profile: self.profile.clone(),
            caller: call.remote.identity()?.into(),
            source: source.into(),
            session: uuid::Uuid::new_v4().to_string(),
            operation: request.binding.request_id.to_string(),
            input_relative: intent.input().into(),
            output_parent: intent.output_parent().into(),
            output_leaf: intent.output_leaf().into(),
        };
        if !binding.valid() {
            return Err("WINDOWS_WORKSPACE_BINDING_REJECTED");
        }
        let permit = self.authorizer.commit_local_admission(
            &call.remote,
            &self.context.execution_gate,
            call.ticket,
        )?;
        self.current(&call.authority)?;
        claimed
            .verify_request(
                &request,
                i64::try_from(now()?).map_err(|_| "CLOUD_DEADLINE_REJECTED")?,
            )
            .map_err(|_| "CLOUD_WORKSPACE_CLAIM_REJECTED")?;
        if Instant::now() >= call.deadline
            || now()? >= call.deadline_epoch
            || *cancelled.borrow()
            || !self.link.matches(&peer(&request)?)
        {
            return Err("CLOUD_DEADLINE_REJECTED");
        }
        // Non-generic actual permission owner BEFORE any input handle/effect.
        let grant = WorkspaceRunGrant {
            binding,
            host: self.id,
            operation: request.binding.request_id,
            _permit: permit,
            _claimed: Some(claimed),
        };
        #[cfg(test)]
        if let Some(fixture) = call.creation_fixture {
            let report = owned_run::hcs::run_claimed_creation_fixture(
                self.context.clone(),
                root,
                grant,
                work,
                call.deadline,
                cancelled.clone(),
                fixture,
            )?;
            if !report.source_handles_closed {
                // Whole concrete claim/journal/permit/root/HCS owner is held;
                // Worker cannot append COMPLETE for the uncertain operation.
                return Err("CLOUD_EXECUTION_UNKNOWN");
            }
            self.current(&call.authority)?;
            if Instant::now() >= call.deadline
                || now()? >= call.deadline_epoch
                || *cancelled.borrow()
            {
                return Err("CLOUD_EXECUTION_UNKNOWN");
            }
            return Ok(json!({"ok":false,"error":{"code":"SANDBOX_REQUIRED",
                "category":"availability","retryable":false,
                "message":"Engineering creation lifecycle has no Guest IO or output issuer."},
                "operation":report.operation,"diagnostic_reason":report.error,
                "source_handles_closed":report.source_handles_closed,
                "creation_attempted":report.creation_attempted,"create_completed":report.create_completed,
                "start_completed":report.start_completed,"whole_exit_observed":report.whole_exit_observed,
                "guest_process_started":false,"output_attempted":false,"production_qualified":false}));
        }
        let report = owned_run::preflight(
            self.context.clone(),
            root,
            grant,
            work,
            call.deadline,
            Some(cancelled.clone()),
            owned_run::Fault::None,
        )?;
        if !report.source_handles_closed {
            // Never let Worker append COMPLETE for an uncertain native owner.
            // The retained concrete grant still owns the actual claim/journal.
            return Err("CLOUD_EXECUTION_UNKNOWN");
        }
        // No byte exposure, VM launch or output issuer. Unknown close keeps the
        // whole grant (including actual claim/journal/host) in recovery storage.
        self.current(&call.authority)?;
        if Instant::now() >= call.deadline || now()? >= call.deadline_epoch || *cancelled.borrow() {
            return Err("CLOUD_EXECUTION_UNKNOWN");
        }
        Ok(
            json!({"ok":false,"error":{"code":"SANDBOX_REQUIRED","category":"availability","retryable":false,
            "message":"The actual VM execution and safe output retirement boundary is unavailable."},"operation":report.operation,
            "input_checked":report.input_checked,"source_handles_closed":report.source_handles_closed,"diagnostic_reason":report.error,
            "vm_started":false,"output_attempted":false,"production_qualified":false,"outcome_unknown":!report.source_handles_closed}),
        )
    }
}

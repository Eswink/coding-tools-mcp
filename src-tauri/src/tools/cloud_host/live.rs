//! Actual native authorizer and tool adapter for the database-free live Agent.
//! Persisted projection receipts never authorize execution. Every active view
//! and every opaque permit is rebuilt from the current native authorizer.
mod projection;
mod application_view;
use super::{now, NativeToolHost, PreparedCall};
use crate::auth::cloud_context::CloudPeer;
use coding_tools_cloud_agent::{
    agent::{AgentError, host::{HostAuthoritySnapshot, HostFuture, LocalHost}},
    execution::{ExecutionBinding, ExecutionRequest, PeerBinding},
    projection::{ExecutionState, LocalLease, ProjectionPhase},
};
use projection::ProjectionJournal;
use serde_json::{json, Value};
use std::{path::Path, sync::{Arc, Mutex}, time::Duration};
use tokio::sync::watch;

#[derive(Clone)]
pub(crate) struct NativeLiveHost {
    work: coding_tools_cloud_agent::work::WorkDrain,
    tools: Arc<NativeToolHost>,
    projection: Arc<Mutex<ProjectionJournal>>,
}
pub(crate) struct NativeLivePermit {
    binding: ExecutionBinding,
    prepared: PreparedCall,
}
fn rejected(_: impl std::fmt::Display) -> AgentError { AgentError::LocalAuthority }
fn peer(value: &PeerBinding) -> Result<CloudPeer, AgentError> {
    Ok(CloudPeer {
        connector: value.connector,
        device: value.device,
        device_epoch: u64::try_from(value.device_epoch).map_err(rejected)?,
        gateway_boot: value.gateway_boot,
        session: value.channel_session,
        generation: u64::try_from(value.channel_generation).map_err(rejected)?,
    })
}
impl NativeLiveHost {
    /// Initialization is an explicit native setup action, never inferred from a
    /// missing/corrupt document after a restart.
    pub(crate) fn open(tools: Arc<NativeToolHost>, storage: &Path, initialize: bool,
                       initial_epoch: i64) -> Result<Self, AgentError> {
        let binding=tools.link.storage_binding();
        let journal=ProjectionJournal::open(storage, &binding, initialize, initial_epoch)?;
        Ok(Self { tools, projection: Arc::new(Mutex::new(journal)), work: Default::default() })
    }

    /// Used only by the live authenticated approval route. The registered
    /// conversation digest is persisted before the existing native pending
    /// request is allocated. This method cannot approve any request.
    pub(crate) fn request_authorization(&self, conversation: &str, args: &Value) -> Value {
        let req=match self.tools.request(conversation) {
            Ok(req)=>req,
            Err(_)=>return super::fixed_error("CLOUD_CONNECTION_REQUIRED"),
        };
        let status=self.tools.authorizer.status(&req);
        if status["ok"]!=true { return status; }
        if self.tools.context.execution_gate.snapshot().availability
            !=crate::runtime::ExecutionAvailability::Online
        {
            return super::fixed_error("CHAT_AUTHORIZATION_UNAVAILABLE");
        }
        if args.as_object().is_none_or(|obj|
            obj.keys().any(|k| k != "scopes")
            || obj.get("scopes").is_some_and(|s| !s.is_array()))
            || serde_json::to_vec(args).map_or(true, |v| v.len()>4096)
        {
            return super::fixed_error("CLOUD_ARGUMENTS_REJECTED");
        }
        let registered=self.projection.lock().map_err(|_|AgentError::Journal)
            .and_then(|mut p|p.register(conversation));
        if registered.is_err() { return super::fixed_error("CLOUD_AUTHORITY_CAPACITY"); }
        self.tools.request_authorization(conversation,args)
    }

    fn current(&self) -> Result<HostAuthoritySnapshot, AgentError> {
        self.tools.link.ensure_connected().map_err(rejected)?;
        let mut journal=self.projection.lock().map_err(|_|AgentError::Journal)?;
        let root=self.tools.authorizer.snapshot(&self.tools.profile);
        if root["exclusive"]!=true { return Err(AgentError::LocalAuthority); }
        let revision=root["revision"].as_u64().and_then(|n|n.checked_add(1))
            .ok_or(AgentError::LocalAuthority)?;
        let gate=self.tools.context.execution_gate.snapshot();
        let recovery=root["recovery"]["required"]!=false;
        let local_free=!recovery && root["lease_state"]=="free";
        let mut found=None;
        let mut owned_pending=false;
        let mut revision=revision;
        let mut generation=gate.generation;
        for conversation in journal.conversations() {
            if let Ok(req)=self.tools.request(conversation) {
                let status=self.tools.authorizer.status(&req);
                owned_pending |= status["ok"]==true && status["authorization"]["status"]=="pending";
            }
            if let Ok(authority)=self.tools.authority(conversation) {
                if authority.view.phase()==crate::auth::LocalAuthorityPhase::Active
                    && authority.view.deadline()>now().map_err(rejected)?
                {
                    if found.is_some() { return Err(AgentError::LocalAuthority); }
                    let v=&authority.view;
                    revision=revision.max(v.source_revision().checked_add(1).ok_or(AgentError::LocalAuthority)?);
                    generation=v.source_generation();
                    let lease=LocalLease {
                        id: uuid::Uuid::parse_str(v.grant_identity()).map_err(rejected)?,
                        conversation: conversation.to_owned(),
                        scopes: v.scopes().iter().cloned().collect(),
                        issued_at:i64::try_from(v.grant_created_at()).map_err(rejected)?,
                        expires_at:i64::try_from(v.grant_hard_deadline()).map_err(rejected)?,
                    };
                    found=Some(projection::ObservedGrant {
                        lease, native_epoch:v.source_epoch(),
                        execution:if v.execution_state()==crate::auth::LocalExecutionState::Online {
                            ExecutionState::Online
                        } else { ExecutionState::Offline },
                    });
                }
            }
        }
        let result=journal.observe(found,local_free||owned_pending,recovery,revision,generation)?;
        self.tools.link.ensure_connected().map_err(rejected)?;
        Ok(result)
    }
    #[cfg(test)]
    fn receipt(&self,view:&HostAuthoritySnapshot)->Result<(),AgentError> {
        self.projection.lock().map_err(|_|AgentError::Journal)?.acknowledge(view)
    }
}
impl LocalHost for NativeLiveHost {
    type Permit=NativeLivePermit;
    fn connected(&self,value:PeerBinding,seconds:u64)->HostFuture<()> {
        let link=self.tools.link.clone();
        super::super::native_drain::blocking(&self.work, move |_| {
            link.activate(peer(&value)?,Duration::from_secs(seconds)).map_err(rejected)
        })
    }
    fn heartbeat(&self,value:PeerBinding,seconds:u64)->HostFuture<()> {
        let link=self.tools.link.clone();
        super::super::native_drain::blocking(&self.work,move |_| {
            link.renew(&peer(&value)?,Duration::from_secs(seconds)).map_err(rejected)
        })
    }
    fn disconnected(&self,value:&PeerBinding) {
        if let Ok(value)=peer(value) { self.tools.link.disconnect(&value); }
    }
    fn projection_applied(&self,view:HostAuthoritySnapshot)->HostFuture<()> {
        let projection=self.projection.clone();
        super::super::native_drain::blocking(&self.work, move |_| {
            projection.lock().map_err(|_|AgentError::Journal)?.acknowledge(&view)
        })
    }
    fn authorization(&self,request:coding_tools_cloud_agent::approval::ApprovalRequest)->HostFuture<Value> {
        let this=self.clone();
        super::super::native_drain::blocking(&self.work, move |_| {
            request.validate_at(&request.binding.peer,
                i64::try_from(now().map_err(rejected)?).map_err(rejected)?).map_err(rejected)?;
            if !this.tools.link.matches(&peer(&request.binding.peer)?) {
                return Err(AgentError::Authentication);
            }
            let result=match request.binding.method {
                coding_tools_cloud_agent::approval::ApprovalMethod::Status=>{
                    let req=this.tools.request(&request.binding.conversation).map_err(rejected)?;
                    this.tools.authorizer.status(&req)
                },
                coding_tools_cloud_agent::approval::ApprovalMethod::Request=>
                    this.request_authorization(&request.binding.conversation,&request.arguments),
            };
            if !this.tools.link.matches(&peer(&request.binding.peer)?)
                || now().map_err(rejected)? as i64>=request.binding.deadline
            {return Err(AgentError::LocalAuthority);}
            Ok(result)
        })
    }
    fn required_scope(&self,tool:&str,args:&Value)->Option<&'static str> {
        coding_tools_cloud_agent::catalog::tool(tool).map(|spec| spec.primary_scope(args))
    }
    fn snapshot(&self)->HostFuture<HostAuthoritySnapshot> {
        let this=self.clone();
        super::super::native_drain::blocking(&self.work,move |_|this.current())
    }
    fn admit(&self,expected:HostAuthoritySnapshot,request:ExecutionRequest)->HostFuture<Self::Permit> {
        let this=self.clone();
        super::super::native_drain::blocking(&self.work,move |_| {
            if !this.tools.link.matches(&peer(&request.binding.peer)?) || this.current()?!=expected
            { return Err(AgentError::LocalAuthority); }
            request.validate_at(&request.binding.peer,
                i64::try_from(now().map_err(rejected)?).map_err(rejected)?).map_err(rejected)?;
            let spec=coding_tools_cloud_agent::catalog::tool(&request.binding.tool)
                .ok_or(AgentError::LocalAuthority)?;
            spec.validate(&request.arguments).map_err(rejected)?;
            let grant=expected.grant().ok_or(AgentError::LocalAuthority)?;
            if spec.scopes_for(&request.arguments).iter().any(|scope| !grant.scopes.contains(scope)) {
                return Err(AgentError::LocalAuthority);
            }
            if expected.phase()!=ProjectionPhase::Active
                || expected.execution()!=ExecutionState::Online
                || expected.epoch()!=request.binding.authority_epoch
                || grant.id!=request.binding.grant_id
                || grant.conversation!=request.binding.conversation
                || !grant.scopes.contains(&request.binding.scope)
                || this.required_scope(&request.binding.tool,&request.arguments)!=Some(request.binding.scope.as_str())
            { return Err(AgentError::LocalAuthority); }
            let native=this.tools.authority(&request.binding.conversation).map_err(rejected)?;
            let (tool,args)=if request.binding.tool=="workspace_probe" {
                ("list_dir",json!({"path":"."}))
            } else { (request.binding.tool.as_str(),request.arguments.clone()) };
            let prepared=this.tools.prepare(&native,tool,&args,
                u64::try_from(request.binding.deadline).map_err(rejected)?).map_err(rejected)?;
            Ok(NativeLivePermit {binding:request.binding,prepared})
        })
    }
    fn execute(&self,permit:Self::Permit,request:ExecutionRequest,
               cancelled:watch::Receiver<bool>)->HostFuture<Value> {
        let tools=self.tools.clone();
        super::super::native_drain::blocking(&self.work,move |work| {
            if permit.binding!=request.binding || *cancelled.borrow() {
                return Err(AgentError::ExecutionUnknown);
            }
            let probe=request.binding.tool=="workspace_probe";
            let result=tools.execute_scoped(permit.prepared,Some(work),Some(cancelled.clone()))
                .map_err(|_|AgentError::ExecutionUnknown)?;
            if *cancelled.borrow() { return Err(AgentError::ExecutionUnknown); }
            if probe && result["ok"]==true {
                Ok(json!({"ok":true,"workspace_available":true,"execution":"native_tool_dispatch"}))
            } else { Ok(result) }
        })
    }
}
impl coding_tools_cloud_agent::managed::ManagedLocalHost for NativeLiveHost {
    fn wait_for_drain(&self)->HostFuture<()> {
        // Seal before returning the future. Unknown callbacks/children never
        // return a successful receipt or release the managed Agent's file lock.
        self.work.seal();
        let work=self.work.clone();
        Box::pin(async move {work.wait().await;Ok(())})
    }
}
#[cfg(test)] mod tests;

#[cfg(all(test,feature="cloud-agent-integration-tests"))]
mod wss_tests;

#[cfg(test)]
mod catalog_tests;

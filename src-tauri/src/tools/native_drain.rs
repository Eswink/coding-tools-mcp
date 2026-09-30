//! Native-owned drain plumbing. Transport cancellation never retires actual
//! blocking work. This module confers no local execution authority.
use super::{session::ExecSession, workspace::WorkspaceError, ToolContext};
use coding_tools_cloud_agent::{
    work::{WorkDrain, WorkGuard, WorkScope},
    AgentError, HostFuture,
};
use std::{cell::RefCell, marker::PhantomData, rc::Rc, sync::Arc, time::Duration};

#[derive(Clone, Default)]
struct NativeScopes {
    cloud: Option<WorkScope>,
    root: Option<super::root_work::RootWorkScope>,
}
thread_local! {static CURRENT:RefCell<NativeScopes>=const{RefCell::new(NativeScopes { cloud: None, root: None })};}
/// Thread-confined scope; never retain this guard across async suspension.
pub(crate) struct ThreadScope { previous: NativeScopes, _thread: PhantomData<Rc<()>> }
pub(crate) fn enter(scope: Option<WorkScope>) -> ThreadScope {
    let previous=CURRENT.with(|current| {
        let mut next=current.borrow().clone();next.cloud=scope;current.replace(next)
    });
    ThreadScope {previous,_thread:PhantomData}
}
pub(crate) fn enter_context(ctx:&ToolContext)->ThreadScope {
    let next=NativeScopes {cloud:ctx.native_work.clone(),root:ctx.root_scope.clone()};
    let previous=CURRENT.with(|current|current.replace(next));ThreadScope{previous,_thread:PhantomData}
}
impl Drop for ThreadScope { fn drop(&mut self) { CURRENT.with(|c|c.replace(std::mem::take(&mut self.previous))); } }
/// Both independent lifetimes must retain the actual descendant. Neither is authority.
pub(crate) struct NativeGuard {cloud:Option<WorkGuard>,root:Option<super::root_work::RootWorkGuard>}
impl From<WorkGuard> for NativeGuard { fn from(cloud:WorkGuard)->Self {Self{cloud:Some(cloud),root:None}} }
impl NativeGuard {
    fn complete(self) {if let Some(g)=self.cloud{g.complete();}if let Some(g)=self.root{g.complete();}}
}
fn fork(scopes:&NativeScopes)->Result<Option<NativeGuard>, &'static str> {
    let cloud=scopes.cloud.as_ref().map(WorkScope::fork).transpose().map_err(|_|"Native drain rejected child")?;
    let root=scopes.root.as_ref().map(super::root_work::RootWorkScope::fork).transpose().map_err(|_|"Native root rejected child")?;
    Ok(if cloud.is_none()&&root.is_none(){None}else{Some(NativeGuard{cloud,root})})
}
pub(crate) fn current_child()->Result<Option<NativeGuard>, &'static str> { CURRENT.with(|c|fork(&c.borrow())) }
fn rejected()->WorkspaceError {WorkspaceError::Tool{code:"CLOUD_HOST_STOPPING",message:"Native work admission is closed.".into(),category:"availability",retryable:false}}
pub(crate) fn child(ctx:&ToolContext)->Result<Option<NativeGuard>,WorkspaceError> {
    fork(&NativeScopes{cloud:ctx.native_work.clone(),root:ctx.root_scope.clone()}).map_err(|_|rejected())
}
pub(crate) fn begin(guard:&mut Option<NativeGuard>)->Result<(),WorkspaceError> {
    if let Some(g)=guard {
        if let Some(cloud)=g.cloud.as_mut(){cloud.begin().map_err(|_|rejected())?;}
        if let Some(root)=g.root.as_mut(){
            if root.begin().is_err(){
                // No caller effects have occurred yet. Retire the already-begun
                // paired cloud registration instead of inventing uncertainty.
                if let Some(cloud)=g.cloud.take(){cloud.complete();}
                return Err(rejected());
            }
        }
    }
    Ok(())
}
pub(crate) fn scope(guard:&Option<NativeGuard>)->Option<WorkScope>{guard.as_ref().and_then(|g|g.cloud.as_ref().map(WorkGuard::scope))}
pub(crate) fn root_scope(guard:&Option<NativeGuard>)->Option<super::root_work::RootWorkScope>{guard.as_ref().and_then(|g|g.root.as_ref().map(super::root_work::RootWorkGuard::scope))}
pub(crate) fn complete(guard:Option<NativeGuard>){if let Some(g)=guard{g.complete();}}

/// Registration is synchronous, before a returned future can be queued or
/// cancelled. The worker owns the guard, not the JoinHandle's waiting future.
pub(crate) fn blocking<T, F>(drain: &WorkDrain, run: F) -> HostFuture<T>
where
    T: Send + 'static,
    F: FnOnce(WorkScope) -> Result<T, AgentError> + Send + 'static,
{
    let registered = drain.register().map_err(|_| AgentError::LocalAuthority);
    Box::pin(async move {
        let mut work = registered?;
        tokio::task::spawn_blocking(move || {
            work.begin().map_err(|_| AgentError::LocalAuthority)?;
            let scope = work.scope();
            let _thread = enter(Some(scope.clone()));
            let result = run(scope);
            work.complete();
            result
        })
        .await
        .map_err(|_| AgentError::ExecutionUnknown)?
    })
}

/// Signal zero only observes the original child-owned process group. Never send
/// another kill using a saved PID: it may already have been recycled. Reuse or
/// observation failure is conservative uncertainty, not a new kill target.
#[cfg(unix)]
fn group_gone(pid: u32) -> bool {
    let Ok(id) = i32::try_from(pid) else {
        return false;
    };
    if id <= 1 {
        return false;
    }
    let result = unsafe { libc::kill(-id, 0) };
    result < 0 && std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
}
#[cfg(not(unix))]
fn group_gone(_pid: u32) -> bool {
    false
} // Windows cloud execution remains fail-closed.

/// Called only after all session readers/initial input have been registered.
/// The monitor retains both the real session and work guard. Cancellation or
/// panic quarantines the drain instead of freeing the Agent's journal lock.
pub(crate) fn track_process<G: Into<NativeGuard>>(session: Arc<ExecSession>, guard: Option<G>, pid: Option<u32>) {
    let Some(guard) = guard else {
        return;
    };
    let guard = guard.into();
    tauri::async_runtime::spawn(async move {
        loop {
            session.refresh_status().await;
            if session.has_exited() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        session.wait_for_readers().await;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
        let owned_tree_gone = || {
            #[cfg(windows)] { session.owned_job_drained() }
            #[cfg(not(windows))] { pid.is_some_and(group_gone) }
        };
        while !owned_tree_gone() && tokio::time::Instant::now() < deadline {
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        if session.has_exited()
            && session.snapshot(0)["process_may_be_running"] != true
            && owned_tree_gone()
        {
            guard.complete();
        }
        // Otherwise the running guard's Drop irreversibly records uncertainty.
    });
}
#[cfg(test)]
mod tests;

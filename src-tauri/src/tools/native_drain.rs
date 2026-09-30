//! Native-owned drain plumbing. Transport cancellation never retires actual
//! blocking work. This module confers no local execution authority.
use super::{session::ExecSession, workspace::WorkspaceError, ToolContext};
use coding_tools_cloud_agent::{
    work::{WorkDrain, WorkGuard, WorkScope},
    AgentError, HostFuture,
};
use std::{cell::RefCell, marker::PhantomData, rc::Rc, sync::Arc, time::Duration};

thread_local! {static CURRENT:RefCell<Option<WorkScope>>=const{RefCell::new(None)};}
/// Thread-confined scope for existing synchronous Git/Harness helpers. It must
/// never cross an async suspension or be copied to a different OS thread.
pub(crate) struct ThreadScope {
    previous: Option<WorkScope>,
    _thread: PhantomData<Rc<()>>,
}
pub(crate) fn enter(scope: Option<WorkScope>) -> ThreadScope {
    let previous = CURRENT.with(|current| current.replace(scope));
    ThreadScope {
        previous,
        _thread: PhantomData,
    }
}
impl Drop for ThreadScope {
    fn drop(&mut self) {
        CURRENT.with(|c| c.replace(self.previous.take()));
    }
}
pub(crate) fn current_child() -> Result<Option<WorkGuard>, &'static str> {
    CURRENT
        .with(|c| c.borrow().as_ref().map(WorkScope::fork).transpose())
        .map_err(|_| "Native work drain rejected child")
}
fn rejected() -> WorkspaceError {
    WorkspaceError::Tool {
        code: "CLOUD_HOST_STOPPING",
        message: "Native work admission is closed.".into(),
        category: "availability",
        retryable: false,
    }
}
pub(crate) fn child(ctx: &ToolContext) -> Result<Option<WorkGuard>, WorkspaceError> {
    ctx.native_work
        .as_ref()
        .map(WorkScope::fork)
        .transpose()
        .map_err(|_| rejected())
}
pub(crate) fn begin(guard: &mut Option<WorkGuard>) -> Result<(), WorkspaceError> {
    if let Some(g) = guard {
        g.begin().map_err(|_| rejected())?;
    }
    Ok(())
}
pub(crate) fn scope(guard: &Option<WorkGuard>) -> Option<WorkScope> {
    guard.as_ref().map(WorkGuard::scope)
}
pub(crate) fn complete(guard: Option<WorkGuard>) {
    if let Some(g) = guard {
        g.complete();
    }
}

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
pub(crate) fn track_process(session: Arc<ExecSession>, guard: Option<WorkGuard>, pid: Option<u32>) {
    let Some(guard) = guard else {
        return;
    };
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
        while !pid.is_some_and(group_gone) && tokio::time::Instant::now() < deadline {
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        if session.has_exited()
            && session.snapshot(0)["process_may_be_running"] != true
            && pid.is_some_and(group_gone)
        {
            guard.complete();
        }
        // Otherwise the running guard's Drop irreversibly records uncertainty.
    });
}
#[cfg(test)]
mod tests;

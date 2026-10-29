//! Native-owned Agent task lifecycle. This is NOT an authorization credential.
//!
//! Registration, start admission, stop, and permanent shutdown share one mutex.
//! A queued task whose stop wins never invokes its factory. Once start admission
//! wins, shutdown must observe its termination; a timeout NEVER frees its slot.
//! A panic or dropped running future is quarantined, because detached/blocking
//! descendants might still exist. Only an explicit drained outcome permits reuse.
use std::{
    collections::HashMap,
    future::Future,
    sync::{Arc, Mutex, Weak},
    time::Duration,
};
use tokio::{runtime::Handle, sync::watch};
use uuid::Uuid;

pub const MAX_MANAGED_AGENTS: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecycleError {
    InvalidWorkspace,
    InvalidCapacity,
    Closed,
    Busy,
    Capacity,
    RuntimeUnavailable,
    StateUnavailable,
    ForeignHandle,
    StaleHandle,
    StopTimedOut,
    TerminationUnconfirmed,
}
impl std::fmt::Display for LifecycleError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Never interpolate workspace paths, keys, arguments, or worker errors.
        write!(f, "agent_lifecycle_{self:?}")
    }
}
impl std::error::Error for LifecycleError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Queued,
    Running,
    Stopping,
    Unconfirmed,
}

/// A worker may report a drained exit ONLY after all work it owns is accounted
/// for. Dropping a JoinHandle or timing out is not proof of child termination.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskExit {
    Drained,
    FailedDrained,
    Unconfirmed,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RunOutcome {
    NotStarted,
    Drained,
    FailedDrained,
    Unconfirmed,
}
impl From<TaskExit> for RunOutcome {
    fn from(value: TaskExit) -> Self {
        match value {
            TaskExit::Drained => Self::Drained,
            TaskExit::FailedDrained => Self::FailedDrained,
            TaskExit::Unconfirmed => Self::Unconfirmed,
        }
    }
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Identity {
    manager: Uuid,
    workspace: Uuid,
    generation: u64,
}

/// Read-only completion and native stop handle. No Deserialize implementation,
/// abort handle, forget operation, or authority-creation API is exposed.
#[derive(Clone)]
pub struct RunHandle {
    identity: Identity,
    inner: Weak<Inner>,
    done: watch::Receiver<Option<RunOutcome>>,
}
impl std::fmt::Debug for RunHandle {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RunHandle")
            .field("generation", &self.identity.generation)
            .field("outcome", &self.outcome())
            .finish_non_exhaustive()
    }
}
impl RunHandle {
    pub fn generation(&self) -> u64 {
        self.identity.generation
    }
    pub fn outcome(&self) -> Option<RunOutcome> {
        *self.done.borrow()
    }
    pub fn phase(&self) -> Result<Option<Phase>, LifecycleError> {
        let Some(inner) = self.inner.upgrade() else {
            return Ok(None);
        };
        let state = inner
            .state
            .lock()
            .map_err(|_| LifecycleError::StateUnavailable)?;
        Ok(state
            .entries
            .get(&self.identity.workspace)
            .filter(|e| e.identity == self.identity)
            .map(|e| e.phase))
    }
    async fn completed(&self) -> Result<RunOutcome, LifecycleError> {
        let mut done = self.done.clone();
        loop {
            // A watch borrow must not survive an await or a lifecycle lock.
            let outcome = *done.borrow_and_update();
            if let Some(outcome) = outcome {
                return if outcome == RunOutcome::Unconfirmed {
                    Err(LifecycleError::TerminationUnconfirmed)
                } else {
                    Ok(outcome)
                };
            }
            done.changed()
                .await
                .map_err(|_| LifecycleError::TerminationUnconfirmed)?;
        }
    }
    pub async fn wait(&self, timeout: Duration) -> Result<RunOutcome, LifecycleError> {
        tokio::time::timeout(timeout, self.completed())
            .await
            .map_err(|_| LifecycleError::StopTimedOut)?
    }
}
struct Entry {
    identity: Identity,
    phase: Phase,
    stop: watch::Sender<bool>,
    done: watch::Receiver<Option<RunOutcome>>,
}
struct State {
    closed: bool,
    generation: u64,
    entries: HashMap<Uuid, Entry>,
}
struct Inner {
    identity: Uuid,
    capacity: usize,
    state: Mutex<State>,
}

/// Keep one application-owned instance (usually inside Arc). Dropping that
/// owner requests permanent shutdown even while worker guards retain Inner.
pub struct AgentLifecycle {
    inner: Arc<Inner>,
}
impl AgentLifecycle {
    pub fn new(capacity: usize) -> Result<Self, LifecycleError> {
        if !(1..=MAX_MANAGED_AGENTS).contains(&capacity) {
            return Err(LifecycleError::InvalidCapacity);
        }
        Ok(Self {
            inner: Arc::new(Inner {
                identity: Uuid::new_v4(),
                capacity,
                state: Mutex::new(State {
                    closed: false,
                    generation: 0,
                    entries: HashMap::new(),
                }),
            }),
        })
    }
    pub fn launch<F, Fut>(&self, workspace: Uuid, factory: F) -> Result<RunHandle, LifecycleError>
    where
        F: FnOnce(watch::Receiver<bool>) -> Fut + Send + 'static,
        Fut: Future<Output = TaskExit> + Send + 'static,
    {
        let runtime = Handle::try_current().map_err(|_| LifecycleError::RuntimeUnavailable)?;
        self.launch_on(&runtime, workspace, factory)
    }
    pub fn launch_on<F, Fut>(
        &self,
        runtime: &Handle,
        workspace: Uuid,
        factory: F,
    ) -> Result<RunHandle, LifecycleError>
    where
        F: FnOnce(watch::Receiver<bool>) -> Fut + Send + 'static,
        Fut: Future<Output = TaskExit> + Send + 'static,
    {
        if workspace.is_nil() {
            return Err(LifecycleError::InvalidWorkspace);
        }
        let (stop, cancelled) = watch::channel(false);
        let (complete, done) = watch::channel(None);
        let mut state = self
            .inner
            .state
            .lock()
            .map_err(|_| LifecycleError::StateUnavailable)?;
        if state.closed {
            return Err(LifecycleError::Closed);
        }
        if state.entries.contains_key(&workspace) {
            return Err(LifecycleError::Busy);
        }
        if state.entries.len() >= self.inner.capacity {
            return Err(LifecycleError::Capacity);
        }
        let generation = state
            .generation
            .checked_add(1)
            .ok_or(LifecycleError::Capacity)?;
        state.generation = generation;
        let identity = Identity {
            manager: self.inner.identity,
            workspace,
            generation,
        };
        state.entries.insert(
            workspace,
            Entry {
                identity,
                phase: Phase::Queued,
                stop,
                done: done.clone(),
            },
        );
        // Construct the drop guard BEFORE spawn. Even a runtime that drops a
        // never-polled future then releases its queued reservation correctly.
        let mut guard = Completion {
            inner: self.inner.clone(),
            identity,
            started: false,
            complete: Some(complete),
        };
        drop(state);
        let handle = RunHandle {
            identity,
            inner: Arc::downgrade(&self.inner),
            done,
        };
        runtime.spawn(async move {
            if !guard.begin() {
                guard.finish(RunOutcome::NotStarted);
                return;
            }
            // Start admission above is the linearization point. Shutdown after
            // that point waits for this factory + future, not just registration.
            let outcome = factory(cancelled).await;
            guard.finish(outcome.into());
        });
        Ok(handle)
    }
    pub fn current(&self, workspace: Uuid) -> Result<Option<RunHandle>, LifecycleError> {
        let state = self
            .inner
            .state
            .lock()
            .map_err(|_| LifecycleError::StateUnavailable)?;
        Ok(state.entries.get(&workspace).map(|e| RunHandle {
            identity: e.identity,
            inner: Arc::downgrade(&self.inner),
            done: e.done.clone(),
        }))
    }
    pub fn is_closed(&self) -> bool {
        self.inner.state.lock().map_or(true, |s| s.closed)
    }
    pub fn request_stop(&self, handle: &RunHandle) -> Result<(), LifecycleError> {
        if handle.identity.manager != self.inner.identity {
            return Err(LifecycleError::ForeignHandle);
        }
        let mut state = self
            .inner
            .state
            .lock()
            .map_err(|_| LifecycleError::StateUnavailable)?;
        let Some(entry) = state.entries.get_mut(&handle.identity.workspace) else {
            return if handle.outcome().is_some() {
                Ok(())
            } else {
                Err(LifecycleError::StaleHandle)
            };
        };
        if entry.identity != handle.identity {
            return Err(LifecycleError::StaleHandle);
        }
        if entry.phase == Phase::Unconfirmed {
            return Err(LifecycleError::TerminationUnconfirmed);
        }
        entry.phase = Phase::Stopping;
        entry.stop.send_replace(true);
        Ok(())
    }
    pub async fn stop(
        &self,
        handle: &RunHandle,
        timeout: Duration,
    ) -> Result<RunOutcome, LifecycleError> {
        self.request_stop(handle)?;
        handle.wait(timeout).await
    }
    /// This only requests shutdown. Use shutdown() to await drain; cancellation
    /// of a waiter never reopens the manager or forgets outstanding workers.
    pub fn request_shutdown(&self) {
        let mut state = self.inner.state.lock().unwrap_or_else(|e| e.into_inner());
        state.closed = true;
        for entry in state.entries.values_mut() {
            if entry.phase != Phase::Unconfirmed {
                entry.phase = Phase::Stopping;
            }
            entry.stop.send_replace(true);
        }
    }
    pub async fn shutdown(&self, timeout: Duration) -> Result<(), LifecycleError> {
        self.request_shutdown();
        let handles = {
            let state = self
                .inner
                .state
                .lock()
                .map_err(|_| LifecycleError::StateUnavailable)?;
            state
                .entries
                .values()
                .map(|e| RunHandle {
                    identity: e.identity,
                    inner: Arc::downgrade(&self.inner),
                    done: e.done.clone(),
                })
                .collect::<Vec<_>>()
        };
        // ONE total budget, not a fresh timeout for every workspace.
        tokio::time::timeout(timeout, async {
            for handle in handles {
                handle.completed().await?;
            }
            Ok(())
        })
        .await
        .map_err(|_| LifecycleError::StopTimedOut)?
    }
}
impl Drop for AgentLifecycle {
    fn drop(&mut self) {
        self.request_shutdown();
    }
}

struct Completion {
    inner: Arc<Inner>,
    identity: Identity,
    started: bool,
    complete: Option<watch::Sender<Option<RunOutcome>>>,
}
impl Completion {
    fn begin(&mut self) -> bool {
        let Ok(mut state) = self.inner.state.lock() else {
            return false;
        };
        if state.closed {
            return false;
        }
        let Some(entry) = state.entries.get_mut(&self.identity.workspace) else {
            return false;
        };
        if entry.identity != self.identity || entry.phase != Phase::Queued {
            return false;
        }
        self.started = true;
        entry.phase = Phase::Running;
        true
    }
    fn finish(&mut self, outcome: RunOutcome) {
        let Some(complete) = self.complete.take() else {
            return;
        };
        let mut state = match self.inner.state.lock() {
            Ok(state) => state,
            Err(error) => {
                let mut state = error.into_inner();
                state.closed = true;
                for entry in state.entries.values() {
                    entry.stop.send_replace(true);
                }
                state
            }
        };
        if state
            .entries
            .get(&self.identity.workspace)
            .is_some_and(|e| e.identity == self.identity)
        {
            if outcome == RunOutcome::Unconfirmed {
                let entry = state
                    .entries
                    .get_mut(&self.identity.workspace)
                    .expect("checked entry");
                entry.phase = Phase::Unconfirmed;
                entry.stop.send_replace(true);
            } else {
                state.entries.remove(&self.identity.workspace);
            }
        }
        // Publish before unlocking: observing completion also means any safe
        // capacity release has occurred. Stale completion cannot remove a new run.
        complete.send_replace(Some(outcome));
    }
}
impl Drop for Completion {
    fn drop(&mut self) {
        self.finish(if self.started {
            RunOutcome::Unconfirmed
        } else {
            RunOutcome::NotStarted
        });
    }
}

#[cfg(test)]
mod tests;

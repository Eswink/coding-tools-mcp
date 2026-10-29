//! Process-local drain accounting. This is not permission, cancellation, or a
//! durable execution receipt. Only the owner of completed work may retire it.
use std::{
    collections::HashMap,
    fmt,
    sync::{Arc, Mutex, MutexGuard},
};
use tokio::sync::watch;

const MAX_WORK: usize = 512;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkError {
    Closed,
    Capacity,
    Stale,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WorkStatus {
    pub sealed: bool,
    pub outstanding: usize,
    pub unconfirmed: bool,
}
#[derive(Clone, Copy)]
struct Entry {
    running: bool,
    descendant: bool,
}
#[derive(Default)]
struct State {
    sealed: bool,
    unconfirmed: bool,
    next: u64,
    entries: HashMap<u64, Entry>,
}
struct Inner {
    state: Mutex<State>,
    changed: watch::Sender<()>,
}
/// Kept by the native host for one managed Agent lifetime. Sealing is permanent.
#[derive(Clone)]
pub struct WorkDrain(Arc<Inner>);
/// A scope permits only children of a still-running operation, even after seal.
/// Cloning a scope does not manufacture a live operation or increment capacity.
#[derive(Clone)]
pub struct WorkScope {
    inner: Arc<Inner>,
    parent: u64,
}
/// Non-cloneable registration. Dropping queued work proves it never began;
/// dropping running work without `complete` permanently quarantines the drain.
pub struct WorkGuard {
    inner: Arc<Inner>,
    id: u64,
    retired: bool,
}
macro_rules! redacted_debug {
    ($t:ty,$text:literal) => {
        impl fmt::Debug for $t {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str($text)
            }
        }
    };
}
redacted_debug!(WorkDrain, "WorkDrain([REDACTED])");
redacted_debug!(WorkScope, "WorkScope([REDACTED])");
redacted_debug!(WorkGuard, "WorkGuard([REDACTED])");
impl Inner {
    fn state(&self) -> MutexGuard<'_, State> {
        match self.state.lock() {
            Ok(state) => state,
            Err(error) => {
                let mut state = error.into_inner();
                state.unconfirmed = true;
                state.sealed = true;
                state
            }
        }
    }
    fn insert(
        self: &Arc<Self>,
        state: &mut State,
        descendant: bool,
    ) -> Result<WorkGuard, WorkError> {
        if state.unconfirmed {
            return Err(WorkError::Closed);
        }
        if state.entries.len() >= MAX_WORK {
            return Err(WorkError::Capacity);
        }
        let id = state.next.checked_add(1).ok_or(WorkError::Capacity)?;
        state.next = id;
        state.entries.insert(
            id,
            Entry {
                running: false,
                descendant,
            },
        );
        Ok(WorkGuard {
            inner: self.clone(),
            id,
            retired: false,
        })
    }
    fn notify(&self) {
        self.changed.send_replace(());
    }
}
impl Default for WorkDrain {
    fn default() -> Self {
        Self::new()
    }
}
impl WorkDrain {
    pub fn new() -> Self {
        let (changed, _) = watch::channel(());
        Self(Arc::new(Inner {
            state: Mutex::new(State::default()),
            changed,
        }))
    }
    /// Register before detaching or queueing work, not inside its eventual task.
    pub fn register(&self) -> Result<WorkGuard, WorkError> {
        let mut state = self.0.state();
        if state.sealed {
            return Err(WorkError::Closed);
        }
        self.0.insert(&mut state, false)
    }
    pub fn status(&self) -> WorkStatus {
        let state = self.0.state();
        WorkStatus {
            sealed: state.sealed,
            outstanding: state.entries.len(),
            unconfirmed: state.unconfirmed,
        }
    }
    pub fn seal(&self) {
        self.0.state().sealed = true;
        self.0.notify();
    }
    /// Waiters are cancellable; the work is not. Unknown work has no automatic
    /// reset/acknowledgement path and cannot produce a successful drain receipt.
    pub async fn wait(&self) {
        let mut changed = self.0.changed.subscribe();
        loop {
            let state = self.status();
            if state.sealed && state.outstanding == 0 && !state.unconfirmed {
                return;
            }
            // The sender is owned by self. Subscription precedes inspection so
            // completion between inspection and await cannot lose a wakeup.
            if changed.changed().await.is_err() {
                std::future::pending::<()>().await;
            }
        }
    }
}
impl WorkScope {
    /// Reserve descendants while the parent is still running. An admitted
    /// operation may finish during drain, but a stale copied context cannot
    /// start a new independent chain after its parent retires.
    pub fn fork(&self) -> Result<WorkGuard, WorkError> {
        let mut state = self.inner.state();
        if !state.entries.get(&self.parent).is_some_and(|e| e.running) {
            return Err(WorkError::Stale);
        }
        self.inner.insert(&mut state, true)
    }
}
impl WorkGuard {
    /// The root start/close race is linearized under the same state mutex.
    pub fn begin(&mut self) -> Result<(), WorkError> {
        if self.retired {
            return Err(WorkError::Stale);
        }
        let mut state = self.inner.state();
        let entry = *state.entries.get(&self.id).ok_or(WorkError::Stale)?;
        if entry.running {
            return Err(WorkError::Stale);
        }
        if state.unconfirmed || (state.sealed && !entry.descendant) {
            state.entries.remove(&self.id);
            self.retired = true;
            drop(state);
            self.inner.notify();
            return Err(WorkError::Closed);
        }
        state
            .entries
            .get_mut(&self.id)
            .expect("checked entry")
            .running = true;
        Ok(())
    }
    pub fn scope(&self) -> WorkScope {
        WorkScope {
            inner: self.inner.clone(),
            parent: self.id,
        }
    }
    pub fn complete(mut self) {
        if !self.retired {
            self.inner.state().entries.remove(&self.id);
            self.retired = true;
            self.inner.notify();
        }
    }
}
impl Drop for WorkGuard {
    fn drop(&mut self) {
        if self.retired {
            return;
        }
        let mut state = self.inner.state();
        if let Some(entry) = state.entries.remove(&self.id) {
            if entry.running {
                state.unconfirmed = true;
                state.sealed = true;
            }
        }
        self.retired = true;
        drop(state);
        self.inner.notify();
    }
}
#[cfg(test)]
mod tests;

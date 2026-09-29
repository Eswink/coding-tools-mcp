//! Connection ownership is not execution authority or proof of termination.
use crate::{LinkError, Result};
use serde::Serialize;
use std::{sync::{Arc, Mutex}, time::Duration};

const MAX_ACTIVE: usize = 4;

/// A local status projection. No endpoint, workspace, identity or grant is exposed.
/// `loop_running` is deliberately not named `online` or `authorized`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct ConnectionStatus {
    pub loop_running: bool,
    pub active_requests: usize,
    pub recovery_required: bool,
}

#[derive(Default)]
struct State {
    running: bool,
    active: usize,
    fenced: bool,
}

/// Shared by every NativeLink referencing the same locked journal. Per-link
/// semaphores alone cannot prevent an independently constructed link overlapping.
pub(crate) struct Lifecycle(Mutex<State>);
impl Lifecycle {
    pub(crate) fn new(recovery_required: bool) -> Arc<Self> {
        Arc::new(Self(Mutex::new(State { fenced: recovery_required, ..State::default() })))
    }

    pub(crate) fn status(&self) -> ConnectionStatus {
        match self.0.lock() {
            Ok(state) => ConnectionStatus {
                loop_running: state.running,
                active_requests: state.active,
                recovery_required: state.fenced,
            },
            Err(_) => ConnectionStatus {
                loop_running: true,
                active_requests: MAX_ACTIVE,
                recovery_required: true,
            },
        }
    }

    pub(crate) fn begin(self: &Arc<Self>) -> Result<RunLease> {
        let mut state = self.0.lock().map_err(|_| LinkError::Journal)?;
        if state.fenced { return Err(LinkError::Journal); }
        if state.running || state.active != 0 { return Err(LinkError::Capacity); }
        state.running = true;
        Ok(RunLease(self.clone()))
    }

    /// Reserve before spawning so cancellation before the first poll is tracked.
    pub(crate) fn worker(self: &Arc<Self>) -> Result<WorkLease> {
        let mut state = self.0.lock().map_err(|_| LinkError::Journal)?;
        if state.fenced { return Err(LinkError::Journal); }
        if !state.running { return Err(LinkError::Stopped); }
        if state.active >= MAX_ACTIVE { return Err(LinkError::Capacity); }
        state.active += 1;
        Ok(WorkLease { lifecycle: self.clone(), completed: false })
    }

    /// Timeout never aborts admitted work or clears its ownership. The caller may
    /// report a bounded stop failure; subsequent starts still see active/fenced.
    pub(crate) async fn drain(&self, limit: Duration) -> Result<()> {
        tokio::time::timeout(limit, async {
            loop {
                let status = self.status();
                if status.active_requests == 0 {
                    return if status.recovery_required { Err(LinkError::Journal) } else { Ok(()) };
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        }).await.map_err(|_| LinkError::Capacity)?
    }
}

pub(crate) struct RunLease(Arc<Lifecycle>);
impl Drop for RunLease {
    fn drop(&mut self) {
        if let Ok(mut state) = self.0.0.lock() {
            // Dropping the connection loop does not acknowledge native workers.
            state.running = false;
        }
    }
}

pub(crate) struct WorkLease {
    lifecycle: Arc<Lifecycle>,
    completed: bool,
}
impl WorkLease {
    /// Only after a known terminal result and its required durable receipt.
    pub(crate) fn finish(mut self) { self.completed = true; }
}
impl Drop for WorkLease {
    fn drop(&mut self) {
        if let Ok(mut state) = self.lifecycle.0.lock() {
            if !self.completed || state.active == 0 { state.fenced = true; }
            state.active = state.active.saturating_sub(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_connection_owner_per_journal() {
        let state = Lifecycle::new(false);
        let first = state.begin().unwrap();
        assert!(matches!(state.begin(), Err(LinkError::Capacity)));
        drop(first);
        assert!(state.begin().is_ok());
    }

    #[test]
    fn a_worker_cannot_start_without_a_connection_owner() {
        assert!(matches!(Lifecycle::new(false).worker(), Err(LinkError::Stopped)));
    }

    #[test]
    fn unpolled_or_panicking_worker_fences_restarts() {
        let state = Lifecycle::new(false);
        let run = state.begin().unwrap();
        let worker = state.worker().unwrap();
        drop(worker);
        drop(run);
        assert!(state.status().recovery_required);
        assert!(matches!(state.begin(), Err(LinkError::Journal)));
    }

    #[test]
    fn cancelling_run_does_not_release_inflight_work() {
        let state = Lifecycle::new(false);
        let run = state.begin().unwrap();
        let work = state.worker().unwrap();
        drop(run);
        assert_eq!(state.status().active_requests, 1);
        assert!(matches!(state.begin(), Err(LinkError::Capacity)));
        work.finish();
        assert!(state.begin().is_ok());
    }

    #[test]
    fn work_capacity_is_shared_and_bounded() {
        let state = Lifecycle::new(false);
        let _run = state.begin().unwrap();
        let jobs: Vec<_> = (0..MAX_ACTIVE).map(|_| state.worker().unwrap()).collect();
        assert!(matches!(state.worker(), Err(LinkError::Capacity)));
        for job in jobs { job.finish(); }
        assert_eq!(state.status().active_requests, 0);
    }

    #[tokio::test]
    async fn drain_timeout_keeps_ownership_instead_of_claiming_termination() {
        let state = Lifecycle::new(false);
        let run = state.begin().unwrap();
        let work = state.worker().unwrap();
        assert_eq!(state.drain(Duration::from_millis(20)).await, Err(LinkError::Capacity));
        drop(run);
        assert!(matches!(state.begin(), Err(LinkError::Capacity)));
        work.finish();
        assert_eq!(state.drain(Duration::from_secs(1)).await, Ok(()));
        assert!(state.begin().is_ok());
    }

    #[tokio::test]
    async fn drain_waits_for_explicit_terminal_completion() {
        let state = Lifecycle::new(false);
        let _run = state.begin().unwrap();
        let work = state.worker().unwrap();
        let drained = state.clone();
        let wait = tokio::spawn(async move { drained.drain(Duration::from_secs(1)).await });
        tokio::task::yield_now().await;
        assert!(!wait.is_finished());
        work.finish();
        assert_eq!(wait.await.unwrap(), Ok(()));
    }

    #[test]
    fn durable_unknown_history_starts_fenced() {
        let state = Lifecycle::new(true);
        assert!(state.status().recovery_required);
        assert!(matches!(state.begin(), Err(LinkError::Journal)));
    }

    #[test]
    fn status_is_not_a_grant_or_connectivity_claim() {
        let value = serde_json::to_value(Lifecycle::new(false).status()).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 3);
        for forbidden in ["online", "authorized", "workspace", "issuer", "grant"] {
            assert!(value.get(forbidden).is_none());
        }
    }
}

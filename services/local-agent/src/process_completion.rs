//! Windows opt-in evidence gate, separated from legacy outcome classification.
use super::{ExecOutcome, ExecTermination, TERMINATE_WAIT};
use std::{io, time::Duration};
use tokio::{sync::watch, time::Instant};

pub(super) async fn publish(
    done: watch::Sender<Option<ExecOutcome>>,
    mut outcome: ExecOutcome,
    prerequisites: bool,
    query: impl FnMut() -> io::Result<bool>,
    started: std::time::Instant,
) {
    let empty = confirm_empty(query, Instant::now() + TERMINATE_WAIT).await;
    if !prerequisites || !empty {
        outcome.termination = ExecTermination::TerminationUncertain;
    }
    // Existing uncertainty is never cleared by a later successful observation.
    outcome.duration_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    done.send_replace(Some(outcome));
}

async fn confirm_empty(mut query: impl FnMut() -> io::Result<bool>, deadline: Instant) -> bool {
    loop {
        if Instant::now() >= deadline {
            return false;
        }
        let observed = query();
        // A slow query returning zero after the deadline cannot claim completion.
        if Instant::now() >= deadline {
            return false;
        }
        match observed {
            Ok(true) => return true,
            Err(_) => return false,
            Ok(false) => {}
        }
        let next = (Instant::now() + Duration::from_millis(20)).min(deadline);
        tokio::time::sleep_until(next).await;
    }
}

#[cfg(test)]
#[path = "process_completion_tests.rs"]
mod tests;

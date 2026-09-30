//! Windows owned-Job evidence, separate from parent and pipe completion.
use super::ExecSession;
use std::sync::atomic::Ordering;

impl ExecSession {
    /// One exact observation. The native drain owner polls with its bounded
    /// deadline and separately requires direct-child exit and completed readers.
    /// Unknown remains sticky; a later empty query cannot erase an earlier error.
    pub(crate) fn owned_job_drained(&self) -> bool {
        if self.tree_cleanup_failed.load(Ordering::Acquire) {
            return false;
        }
        let result = self
            .process_tree
            .lock()
            .ok()
            .and_then(|tree| tree.as_ref().map(|tree| tree.is_empty()));
        match result {
            Some(Ok(empty)) => empty && !self.tree_cleanup_failed.load(Ordering::Acquire),
            _ => {
                self.tree_cleanup_failed.store(true, Ordering::Release);
                false
            }
        }
    }
}

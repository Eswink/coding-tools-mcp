//! A1 C7-3 (SPEC v5.6 §3.3): the process-local link between a main root's worker
//! store and the live cloud host serving it. A spawn/discard marks the projection
//! dirty (the runner then challenges on its next tick instead of waiting for the
//! 4 s interval); an acknowledged projection records its worker ids so a remote
//! spawn can wait, bounded, until the gateway accepted a projection naming it.
//! "Attached" means a live runner session holds the dirty receiver; without one
//! there is nothing to wait for and the answer is immediately "pending".
use super::{namespace, HostRoots};
use std::{
    collections::{HashMap, HashSet},
    path::PathBuf,
    sync::{Condvar, Mutex, MutexGuard, OnceLock},
    time::{Duration, Instant},
};
use tokio::sync::watch;

struct Entry {
    dirty: watch::Sender<u64>,
    applied: HashSet<String>,
}
struct Bus {
    entries: Mutex<HashMap<PathBuf, Entry>>,
    changed: Condvar,
}
fn bus() -> &'static Bus {
    static BUS: OnceLock<Bus> = OnceLock::new();
    BUS.get_or_init(|| Bus {
        entries: Mutex::default(),
        changed: Condvar::new(),
    })
}
fn entries() -> MutexGuard<'static, HashMap<PathBuf, Entry>> {
    // A poisoned bus only carries advisory state; recover it rather than fail spawn.
    bus().entries.lock().unwrap_or_else(|e| e.into_inner())
}
fn entry<'a>(map: &'a mut HashMap<PathBuf, Entry>, host: &HostRoots) -> &'a mut Entry {
    map.entry(namespace(host)).or_insert_with(|| Entry {
        dirty: watch::channel(0).0,
        applied: HashSet::new(),
    })
}

/// The worker list of this main root changed; never blocks, never fails.
pub(crate) fn mark_dirty(host: &HostRoots) {
    entry(&mut entries(), host)
        .dirty
        .send_modify(|n| *n = n.wrapping_add(1));
}
/// One receiver per live runner session (`LocalHost::projection_dirty`).
pub(crate) fn subscribe(host: &HostRoots) -> watch::Receiver<u64> {
    entry(&mut entries(), host).dirty.subscribe()
}
/// The gateway acknowledged a projection naming exactly these workers.
pub(crate) fn applied(host: &HostRoots, workers: impl IntoIterator<Item = String>) {
    entry(&mut entries(), host).applied = workers.into_iter().collect();
    bus().changed.notify_all();
}
/// Waits at most `budget` for an acknowledged projection naming `worker_id`.
/// `false` at once when no live session is attached to this main root.
pub(crate) fn wait_applied(host: &HostRoots, worker_id: &str, budget: Duration) -> bool {
    let deadline = Instant::now() + budget;
    let key = namespace(host);
    let mut map = entries();
    loop {
        match map.get(&key) {
            None => return false,
            Some(e) if e.dirty.receiver_count() == 0 => return false,
            Some(e) if e.applied.contains(worker_id) => return true,
            Some(_) => {}
        }
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return false;
        }
        map = bus()
            .changed
            .wait_timeout(map, left)
            .unwrap_or_else(|e| e.into_inner())
            .0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tools::ToolContext;

    fn host() -> (
        tempfile::TempDir,
        tempfile::TempDir,
        std::sync::Arc<HostRoots>,
    ) {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        let ctx = ToolContext::for_test(root.path().into(), state.path().into()).unwrap();
        let host = ctx.host.clone();
        (root, state, host)
    }
    const ID: &str = "0123456789abcdef0123456789abcdef";

    #[test]
    fn c7_wait_without_an_attached_session_is_pending_at_once() {
        let (_r, _s, host) = host();
        let t = Instant::now();
        assert!(!wait_applied(&host, ID, Duration::from_secs(3)));
        mark_dirty(&host);
        assert!(!wait_applied(&host, ID, Duration::from_secs(3)));
        assert!(
            t.elapsed() < Duration::from_millis(500),
            "{:?}",
            t.elapsed()
        );
    }
    #[test]
    fn c7_wait_returns_once_an_acknowledged_projection_names_the_worker() {
        let (_r, _s, host) = host();
        let mut rx = subscribe(&host);
        mark_dirty(&host);
        assert!(rx.has_changed().unwrap(), "spawn marks the session dirty");
        rx.borrow_and_update();
        let other = host.clone();
        let ack = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(100));
            applied(&other, ["f".repeat(32)]);
            std::thread::sleep(Duration::from_millis(100));
            applied(&other, [ID.to_owned()]);
        });
        let t = Instant::now();
        assert!(wait_applied(&host, ID, Duration::from_secs(3)));
        assert!(t.elapsed() < Duration::from_secs(2), "{:?}", t.elapsed());
        ack.join().unwrap();
        drop(rx);
        assert!(!wait_applied(&host, ID, Duration::from_secs(3)), "detached");
    }
    #[test]
    fn c7_wait_is_bounded_when_no_projection_names_the_worker() {
        let (_r, _s, host) = host();
        let _rx = subscribe(&host);
        let t = Instant::now();
        assert!(!wait_applied(&host, ID, Duration::from_millis(300)));
        assert!(t.elapsed() >= Duration::from_millis(300));
        assert!(t.elapsed() < Duration::from_secs(2), "{:?}", t.elapsed());
    }
    #[test]
    fn c7_main_roots_do_not_share_a_bus() {
        let (_r1, _s1, a) = host();
        let (_r2, _s2, b) = host();
        let _rx = subscribe(&a);
        let mut rb = subscribe(&b);
        rb.borrow_and_update();
        mark_dirty(&a);
        assert!(!rb.has_changed().unwrap());
        applied(&a, [ID.to_owned()]);
        assert!(!wait_applied(&b, ID, Duration::from_millis(50)));
    }
}

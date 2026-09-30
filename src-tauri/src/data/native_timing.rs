//! Opt-in diagnostics: fixed labels and aggregate durations only, never values.
use std::{
    cell::Cell,
    io::Write,
    sync::atomic::{AtomicUsize, Ordering},
    time::Instant,
};

thread_local! {
    static KEY_READS: Cell<(u64, u128)> = const { Cell::new((0, 0)) };
}
static REPORTS: AtomicUsize = AtomicUsize::new(0);
const MAX_REPORTS: usize = 256;

pub(crate) struct KeyRead(Instant);
pub(crate) fn key_read() -> KeyRead {
    KeyRead(Instant::now())
}
impl Drop for KeyRead {
    fn drop(&mut self) {
        KEY_READS.with(|value| {
            let (calls, micros) = value.get();
            value.set((
                calls.saturating_add(1),
                micros.saturating_add(self.0.elapsed().as_micros()),
            ));
        });
    }
}

pub(crate) struct Span {
    label: &'static str,
    start: Instant,
    keys: (u64, u128),
    ledgers: usize,
}
impl Span {
    pub(crate) fn new(label: &'static str) -> Self {
        Self {
            label,
            start: Instant::now(),
            keys: KEY_READS.with(Cell::get),
            ledgers: 0,
        }
    }
    pub(crate) fn ledger(&mut self) {
        self.ledgers = self.ledgers.saturating_add(1);
    }
}
impl Drop for Span {
    fn drop(&mut self) {
        if REPORTS.fetch_add(1, Ordering::Relaxed) >= MAX_REPORTS {
            return;
        }
        let keys = KEY_READS.with(Cell::get);
        let _ = writeln!(
            std::io::stderr().lock(),
            "native-state-timing stage={} elapsed_us={} key_reads={} key_read_us={} ledgers={}",
            self.label,
            self.start.elapsed().as_micros(),
            keys.0.saturating_sub(self.keys.0),
            keys.1.saturating_sub(self.keys.1),
            self.ledgers,
        );
    }
}

use serde::Serialize;
use std::{
    fmt,
    fs::File,
    io::{self, Read},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};

#[derive(Clone, Eq, PartialEq, Serialize)]
pub struct PtyOutputSnapshot {
    pub output: Vec<u8>,
    pub output_total_bytes: u64,
    pub truncated: bool,
}

impl fmt::Debug for PtyOutputSnapshot {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PtyOutputSnapshot")
            .field("output_bytes", &self.output.len())
            .field("output_total_bytes", &self.output_total_bytes)
            .field("truncated", &self.truncated)
            .finish()
    }
}

#[derive(Default)]
pub(crate) struct OutputState {
    retained: Vec<u8>,
    total: u64,
    truncated: bool,
}

pub(crate) type SharedOutput = Arc<Mutex<OutputState>>;

pub(crate) struct ReaderHandle {
    join: Option<thread::JoinHandle<()>>,
    done: mpsc::Receiver<bool>,
}

pub(crate) fn shared_output() -> SharedOutput {
    Arc::new(Mutex::new(OutputState::default()))
}

pub(crate) fn spawn_reader(
    mut reader: File,
    state: SharedOutput,
    limit: usize,
    overflow: Arc<AtomicBool>,
) -> ReaderHandle {
    let (done_tx, done) = mpsc::channel();
    let join = thread::spawn(move || {
        let mut complete = true;
        let mut buffer = [0u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => break,
                Ok(read) => {
                    let Ok(mut output) = state.lock() else {
                        complete = false;
                        break;
                    };
                    output.total = output.total.saturating_add(read as u64);
                    let remaining = limit.saturating_sub(output.retained.len());
                    let keep = remaining.min(read);
                    output.retained.extend_from_slice(&buffer[..keep]);
                    if keep < read {
                        output.truncated = true;
                        overflow.store(true, Ordering::Release);
                    }
                }
                Err(error) if terminal_eof(&error) => break,
                Err(_) => {
                    complete = false;
                    break;
                }
            }
        }
        let _ = done_tx.send(complete);
    });
    ReaderHandle {
        join: Some(join),
        done,
    }
}

impl ReaderHandle {
    pub(crate) fn finish(mut self, timeout: Duration) -> bool {
        let complete = self.done.recv_timeout(timeout).unwrap_or(false);
        if complete {
            if let Some(join) = self.join.take() {
                let _ = join.join();
            }
        }
        complete
    }
}

pub(crate) fn live_snapshot(state: &SharedOutput) -> Option<PtyOutputSnapshot> {
    let output = state.lock().ok()?;
    Some(PtyOutputSnapshot {
        output: output.retained.clone(),
        output_total_bytes: output.total,
        truncated: output.truncated,
    })
}

pub(crate) fn snapshot(state: &SharedOutput) -> (Vec<u8>, u64, bool) {
    let Ok(mut output) = state.lock() else {
        return (Vec::new(), 0, true);
    };
    let retained = std::mem::take(&mut output.retained);
    (retained, output.total, output.truncated)
}

#[cfg(unix)]
fn terminal_eof(error: &io::Error) -> bool {
    error.raw_os_error() == Some(libc::EIO)
}

#[cfg(not(unix))]
fn terminal_eof(_error: &io::Error) -> bool {
    false
}

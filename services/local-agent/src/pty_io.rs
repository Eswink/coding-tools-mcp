use std::{
    fs::File,
    io::{self, Read},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};

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
                Err(error) if cfg!(unix) && error.raw_os_error() == Some(libc::EIO) => break,
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

pub(crate) fn snapshot(state: &SharedOutput) -> (Vec<u8>, u64, bool) {
    let Ok(mut output) = state.lock() else {
        return (Vec::new(), 0, true);
    };
    let retained = std::mem::take(&mut output.retained);
    (retained, output.total, output.truncated)
}

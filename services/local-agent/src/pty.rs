use crate::process::{
    MAX_ARGC, MAX_COMMAND_BYTES, MAX_ENV_TOTAL_BYTES, MAX_ENV_VALUE_BYTES, MAX_ENV_VARS,
    MAX_STREAM_BYTES, MAX_TIMEOUT, MAX_TOKEN_BYTES,
};
use crate::pty_io;
use serde::Serialize;
use std::{
    collections::BTreeMap,
    error::Error,
    fmt,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc, Arc,
    },
    thread,
    time::{Duration, Instant},
};
use tokio::sync::{watch, Semaphore};

#[cfg(unix)]
#[path = "pty_unix.rs"]
mod platform;
#[cfg(windows)]
#[path = "pty_windows.rs"]
mod platform;

const MAX_ACTIVE: usize = 32;
const MAX_DIMENSION: u16 = 1000;
const MAX_WRITE_BYTES: usize = 64 * 1024;
const TERMINATE_WAIT: Duration = Duration::from_secs(3);
const READER_WAIT: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PtyErrorKind {
    InvalidSpec,
    Capacity,
    Spawn,
    Closed,
    Io,
}

#[derive(Clone)]
pub struct PtyError {
    pub kind: PtyErrorKind,
    message: &'static str,
}

impl PtyError {
    pub(crate) const fn new(kind: PtyErrorKind, message: &'static str) -> Self {
        Self { kind, message }
    }

    pub fn public_message(&self) -> &'static str {
        self.message
    }
}

impl fmt::Debug for PtyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PtyError")
            .field("kind", &self.kind)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for PtyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message)
    }
}

impl Error for PtyError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct PtySize {
    pub columns: u16,
    pub rows: u16,
}

impl PtySize {
    pub fn new(columns: u16, rows: u16) -> Result<Self, PtyError> {
        if columns == 0 || rows == 0 || columns > MAX_DIMENSION || rows > MAX_DIMENSION {
            return Err(PtyError::new(
                PtyErrorKind::InvalidSpec,
                "invalid terminal size",
            ));
        }
        Ok(Self { columns, rows })
    }
}

#[derive(Clone)]
pub struct PtySpec {
    argv: Vec<String>,
    cwd: PathBuf,
    env: BTreeMap<String, String>,
    size: PtySize,
    timeout: Duration,
    output_limit: usize,
}

impl PtySpec {
    pub fn new(argv: Vec<String>, cwd: impl Into<PathBuf>) -> Result<Self, PtyError> {
        let spec = Self {
            argv,
            cwd: cwd.into(),
            env: BTreeMap::new(),
            size: PtySize::new(80, 24)?,
            timeout: Duration::from_secs(30),
            output_limit: 64 * 1024,
        };
        spec.validate()?;
        Ok(spec)
    }

    pub fn with_env(
        mut self,
        key: impl Into<String>,
        value: impl Into<String>,
    ) -> Result<Self, PtyError> {
        self.env.insert(key.into(), value.into());
        self.validate()?;
        Ok(self)
    }

    pub fn with_size(mut self, size: PtySize) -> Result<Self, PtyError> {
        self.size = size;
        self.validate()?;
        Ok(self)
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Result<Self, PtyError> {
        self.timeout = timeout;
        self.validate()?;
        Ok(self)
    }

    pub fn with_output_limit(mut self, limit: usize) -> Result<Self, PtyError> {
        self.output_limit = limit;
        self.validate()?;
        Ok(self)
    }

    pub(crate) fn argv(&self) -> &[String] {
        &self.argv
    }

    pub(crate) fn cwd(&self) -> &Path {
        &self.cwd
    }

    pub(crate) fn env(&self) -> &BTreeMap<String, String> {
        &self.env
    }

    pub(crate) fn size(&self) -> PtySize {
        self.size
    }

    fn validate(&self) -> Result<(), PtyError> {
        if self.argv.is_empty() || self.argv.len() > MAX_ARGC {
            return Err(invalid());
        }
        if !Path::new(&self.argv[0]).is_absolute() || !self.cwd.is_dir() {
            return Err(invalid());
        }
        let mut command_bytes = 0usize;
        for token in &self.argv {
            if token.len() > MAX_TOKEN_BYTES || token.chars().any(char::is_control) {
                return Err(invalid());
            }
            command_bytes = command_bytes.checked_add(token.len()).ok_or_else(invalid)?;
        }
        if command_bytes > MAX_COMMAND_BYTES || self.env.len() > MAX_ENV_VARS {
            return Err(invalid());
        }
        let mut env_bytes = 0usize;
        for (key, value) in &self.env {
            if !valid_env_key(key)
                || value.len() > MAX_ENV_VALUE_BYTES
                || value.chars().any(char::is_control)
            {
                return Err(invalid());
            }
            env_bytes = env_bytes
                .checked_add(key.len() + value.len())
                .ok_or_else(invalid)?;
        }
        if env_bytes > MAX_ENV_TOTAL_BYTES
            || self.timeout.is_zero()
            || self.timeout > MAX_TIMEOUT
            || self.output_limit == 0
            || self.output_limit > MAX_STREAM_BYTES
        {
            return Err(invalid());
        }
        PtySize::new(self.size.columns, self.size.rows)?;
        Ok(())
    }
}

impl fmt::Debug for PtySpec {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PtySpec")
            .field("argc", &self.argv.len())
            .field("argv", &"<redacted>")
            .field("cwd", &"<redacted>")
            .field("env_entries", &self.env.len())
            .field("env", &"<redacted>")
            .field("size", &self.size)
            .field("timeout_ms", &self.timeout.as_millis())
            .field("output_limit", &self.output_limit)
            .finish()
    }
}

fn valid_env_key(key: &str) -> bool {
    let mut chars = key.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|value| value == '_' || value.is_ascii_alphanumeric())
        && key.len() <= 128
}

fn invalid() -> PtyError {
    PtyError::new(PtyErrorKind::InvalidSpec, "invalid PTY specification")
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PtyTermination {
    Exited,
    TimedOut,
    Cancelled,
    OutputLimit,
    IoError,
    TerminationUncertain,
}

#[derive(Clone, Serialize)]
pub struct PtyOutcome {
    pub session_id: String,
    pub termination: PtyTermination,
    pub exit_code: Option<i32>,
    pub output: Vec<u8>,
    pub output_total_bytes: u64,
    pub truncated: bool,
    pub output_complete: bool,
    pub duration_ms: u64,
}

impl fmt::Debug for PtyOutcome {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PtyOutcome")
            .field("session_id", &self.session_id)
            .field("termination", &self.termination)
            .field("exit_code", &self.exit_code)
            .field("output_bytes", &self.output.len())
            .field("output_total_bytes", &self.output_total_bytes)
            .field("truncated", &self.truncated)
            .field("output_complete", &self.output_complete)
            .field("duration_ms", &self.duration_ms)
            .finish()
    }
}

enum Command {
    Write(Vec<u8>, mpsc::Sender<Result<(), PtyError>>),
    Resize(PtySize, mpsc::Sender<Result<(), PtyError>>),
    Cancel,
    Close,
}

pub struct PtySession {
    id: String,
    commands: mpsc::Sender<Command>,
    done: watch::Receiver<Option<PtyOutcome>>,
}

impl PtySession {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn write(&self, bytes: &[u8]) -> Result<(), PtyError> {
        if bytes.len() > MAX_WRITE_BYTES {
            return Err(invalid());
        }
        request(&self.commands, |reply| Command::Write(bytes.to_vec(), reply))
    }

    pub fn resize(&self, size: PtySize) -> Result<(), PtyError> {
        request(&self.commands, |reply| Command::Resize(size, reply))
    }

    pub fn snapshot(&self) -> Option<PtyOutcome> {
        self.done.borrow().clone()
    }

    pub async fn wait(&mut self) -> PtyOutcome {
        loop {
            if let Some(outcome) = self.done.borrow().clone() {
                return outcome;
            }
            if self.done.changed().await.is_err() {
                return uncertain(&self.id);
            }
        }
    }

    pub async fn cancel(&mut self) -> PtyOutcome {
        let _ = self.commands.send(Command::Cancel);
        self.wait().await
    }
}

impl Drop for PtySession {
    fn drop(&mut self) {
        if self.done.borrow().is_none() {
            let _ = self.commands.send(Command::Close);
        }
    }
}

impl fmt::Debug for PtySession {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PtySession")
            .field("id", &self.id)
            .field("complete", &self.done.borrow().is_some())
            .finish()
    }
}

fn request(
    commands: &mpsc::Sender<Command>,
    build: impl FnOnce(mpsc::Sender<Result<(), PtyError>>) -> Command,
) -> Result<(), PtyError> {
    let (reply_tx, reply_rx) = mpsc::channel();
    commands
        .send(build(reply_tx))
        .map_err(|_| PtyError::new(PtyErrorKind::Closed, "PTY session is closed"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(2))
        .map_err(|_| PtyError::new(PtyErrorKind::Closed, "PTY session is closed"))?
}

#[derive(Clone)]
pub struct PtyManager {
    permits: Arc<Semaphore>,
    next_id: Arc<AtomicU64>,
}

impl PtyManager {
    pub fn new(max_active: usize) -> Result<Self, PtyError> {
        if max_active == 0 || max_active > MAX_ACTIVE {
            return Err(invalid());
        }
        Ok(Self {
            permits: Arc::new(Semaphore::new(max_active)),
            next_id: Arc::new(AtomicU64::new(1)),
        })
    }

    pub async fn start(&self, spec: PtySpec) -> Result<PtySession, PtyError> {
        spec.validate()?;
        let cwd = std::fs::canonicalize(spec.cwd()).map_err(|_| invalid())?;
        let permit = self
            .permits
            .clone()
            .try_acquire_owned()
            .map_err(|_| PtyError::new(PtyErrorKind::Capacity, "PTY capacity exhausted"))?;
        let spawn_spec = spec.clone();
        let spawned = tokio::task::spawn_blocking(move || platform::spawn(&spawn_spec, &cwd))
            .await
            .map_err(|_| PtyError::new(PtyErrorKind::Spawn, "failed to spawn PTY"))??;
        let id = format!("pty-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let output = pty_io::shared_output();
        let overflow = Arc::new(AtomicBool::new(false));
        let reader = pty_io::spawn_reader(
            spawned.reader,
            output.clone(),
            spec.output_limit,
            overflow.clone(),
        );
        let (commands, command_rx) = mpsc::channel();
        let (done_tx, done) = watch::channel(None);
        let supervisor_id = id.clone();
        thread::spawn(move || {
            let _permit = permit;
            let start = Instant::now();
            let mut process = spawned.process;
            let mut termination = PtyTermination::Exited;
            let mut exit_code = None;
            let mut forced = false;
            loop {
                while let Ok(command) = command_rx.try_recv() {
                    match command {
                        Command::Write(bytes, reply) => {
                            let _ = reply.send(process.write(&bytes).map_err(|_| io_error()));
                        }
                        Command::Resize(size, reply) => {
                            let _ = reply.send(process.resize(size).map_err(|_| io_error()));
                        }
                        Command::Cancel => {
                            termination = PtyTermination::Cancelled;
                            forced = true;
                        }
                        Command::Close => {
                            termination = PtyTermination::Cancelled;
                            forced = true;
                        }
                    }
                }
                if forced {
                    break;
                }
                if overflow.load(Ordering::Acquire) {
                    termination = PtyTermination::OutputLimit;
                    forced = true;
                    break;
                }
                if start.elapsed() >= spec.timeout {
                    termination = PtyTermination::TimedOut;
                    forced = true;
                    break;
                }
                match process.try_wait() {
                    Ok(Some(code)) => {
                        exit_code = Some(code);
                        break;
                    }
                    Ok(None) => {}
                    Err(_) => {
                        termination = PtyTermination::IoError;
                        forced = true;
                        break;
                    }
                }
                thread::sleep(Duration::from_millis(10));
            }
            let mut termination_confirmed = true;
            if forced && process.terminate_tree().is_err() {
                termination_confirmed = false;
            }
            if !forced && process.terminate_tree().is_err() {
                termination_confirmed = false;
            }
            let wait_deadline = Instant::now() + TERMINATE_WAIT;
            while exit_code.is_none() && Instant::now() < wait_deadline {
                match process.try_wait() {
                    Ok(Some(code)) => exit_code = Some(code),
                    Ok(None) => thread::sleep(Duration::from_millis(10)),
                    Err(_) => {
                        termination_confirmed = false;
                        break;
                    }
                }
            }
            if exit_code.is_none() && forced {
                termination_confirmed = false;
            }
            if !termination_confirmed {
                termination = PtyTermination::TerminationUncertain;
            }
            process.close_session();
            let output_complete = reader.finish(READER_WAIT);
            let (retained, total, truncated) = pty_io::snapshot(&output);
            if termination == PtyTermination::Exited && (!output_complete || truncated) {
                termination = if truncated {
                    PtyTermination::OutputLimit
                } else {
                    PtyTermination::IoError
                };
            }
            let outcome = PtyOutcome {
                session_id: supervisor_id,
                termination,
                exit_code,
                output: retained,
                output_total_bytes: total,
                truncated,
                output_complete,
                duration_ms: start.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
            };
            done_tx.send_replace(Some(outcome));
        });
        Ok(PtySession { id, commands, done })
    }

    pub async fn run(&self, spec: PtySpec) -> Result<PtyOutcome, PtyError> {
        let mut session = self.start(spec).await?;
        Ok(session.wait().await)
    }
}

impl Default for PtyManager {
    fn default() -> Self {
        Self::new(4).expect("valid PTY capacity")
    }
}

fn io_error() -> PtyError {
    PtyError::new(PtyErrorKind::Io, "PTY I/O failed")
}

fn uncertain(id: &str) -> PtyOutcome {
    PtyOutcome {
        session_id: id.to_owned(),
        termination: PtyTermination::TerminationUncertain,
        exit_code: None,
        output: Vec::new(),
        output_total_bytes: 0,
        truncated: false,
        output_complete: false,
        duration_ms: 0,
    }
}

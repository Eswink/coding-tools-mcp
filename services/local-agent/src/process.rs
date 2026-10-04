use crate::process_tree;
use serde::Serialize;
use std::{
    collections::BTreeMap,
    error::Error,
    fmt,
    path::{Path, PathBuf},
    process::{ExitStatus, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    process::Command,
    sync::{mpsc, watch, Semaphore},
    task::JoinHandle,
};

pub const MAX_ARGC: usize = 128;
pub const MAX_TOKEN_BYTES: usize = 4 * 1024;
pub const MAX_COMMAND_BYTES: usize = 64 * 1024;
pub const MAX_ENV_VARS: usize = 64;
pub const MAX_ENV_VALUE_BYTES: usize = 16 * 1024;
pub const MAX_ENV_TOTAL_BYTES: usize = 64 * 1024;
pub const MAX_STDIN_BYTES: usize = 64 * 1024;
pub const MAX_STREAM_BYTES: usize = 1024 * 1024;
pub const MAX_TIMEOUT: Duration = Duration::from_secs(60 * 60);
const TERMINATE_WAIT: Duration = Duration::from_secs(3);
const READER_WAIT: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecErrorKind {
    InvalidSpec,
    Capacity,
    Spawn,
    #[cfg(target_os = "linux")]
    Sandbox,
}

#[derive(Clone)]
pub struct ExecError {
    pub kind: ExecErrorKind,
    message: &'static str,
}

impl ExecError {
    const fn new(kind: ExecErrorKind, message: &'static str) -> Self {
        Self { kind, message }
    }

    pub fn public_message(&self) -> &'static str {
        self.message
    }
}

impl fmt::Debug for ExecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ExecError")
            .field("kind", &self.kind)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for ExecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message)
    }
}

impl Error for ExecError {}

#[derive(Clone)]
pub struct ExecSpec {
    argv: Vec<String>,
    #[cfg(unix)]
    argv0: Option<String>,
    cwd: PathBuf,
    env: BTreeMap<String, String>,
    stdin: Vec<u8>,
    timeout: Duration,
    stream_limit: usize,
    #[cfg(unix)]
    require_tree_exit: bool,
    #[cfg(target_os = "linux")]
    sandbox: Option<crate::LinuxSandbox>,
}

impl ExecSpec {
    pub fn new(argv: Vec<String>, cwd: impl Into<PathBuf>) -> Result<Self, ExecError> {
        let spec = Self {
            argv,
            #[cfg(unix)]
            argv0: None,
            cwd: cwd.into(),
            env: BTreeMap::new(),
            stdin: Vec::new(),
            timeout: Duration::from_secs(30),
            stream_limit: 64 * 1024,
            #[cfg(unix)]
            require_tree_exit: false,
            #[cfg(target_os = "linux")]
            sandbox: None,
        };
        spec.validate()?;
        Ok(spec)
    }

    /// Attach a host policy after local admission and execution-policy approval.
    #[cfg(target_os = "linux")]
    pub fn with_sandbox(mut self, sandbox: crate::LinuxSandbox) -> Self {
        self.sandbox = Some(sandbox);
        self
    }

    /// Require observed termination of the original child-owned process group.
    /// This strengthens drainage; it neither grants authority nor disables the sandbox.
    #[cfg(unix)]
    pub fn with_tree_exit_confirmation(mut self) -> Self {
        self.require_tree_exit = true;
        self
    }

    pub fn with_env(
        mut self,
        key: impl Into<String>,
        value: impl Into<String>,
    ) -> Result<Self, ExecError> {
        self.env.insert(key.into(), value.into());
        self.validate()?;
        Ok(self)
    }

    pub fn with_stdin(mut self, stdin: impl Into<Vec<u8>>) -> Result<Self, ExecError> {
        self.stdin = stdin.into();
        self.validate()?;
        Ok(self)
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Result<Self, ExecError> {
        self.timeout = timeout;
        self.validate()?;
        Ok(self)
    }

    pub fn with_stream_limit(mut self, limit: usize) -> Result<Self, ExecError> {
        self.stream_limit = limit;
        self.validate()?;
        Ok(self)
    }

    pub fn argv(&self) -> &[String] {
        &self.argv
    }

    pub fn cwd(&self) -> &Path {
        &self.cwd
    }

    fn validate(&self) -> Result<(), ExecError> {
        if self.argv.is_empty() || self.argv.len() > MAX_ARGC {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "invalid argv length",
            ));
        }
        if !Path::new(&self.argv[0]).is_absolute() {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "program path must be absolute",
            ));
        }
        let mut command_bytes = 0usize;
        for token in &self.argv {
            if token.is_empty() && command_bytes == 0
                || token.len() > MAX_TOKEN_BYTES
                || token.chars().any(char::is_control)
            {
                return Err(ExecError::new(
                    ExecErrorKind::InvalidSpec,
                    "invalid argv token",
                ));
            }
            command_bytes = command_bytes
                .checked_add(token.len())
                .ok_or_else(|| ExecError::new(ExecErrorKind::InvalidSpec, "argv size overflow"))?;
        }
        if command_bytes > MAX_COMMAND_BYTES {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "argv is too large",
            ));
        }
        if self.env.len() > MAX_ENV_VARS {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "too many environment variables",
            ));
        }
        let mut env_bytes = 0usize;
        for (key, value) in &self.env {
            if !valid_env_key(key)
                || value.len() > MAX_ENV_VALUE_BYTES
                || value.chars().any(char::is_control)
            {
                return Err(ExecError::new(
                    ExecErrorKind::InvalidSpec,
                    "invalid environment entry",
                ));
            }
            env_bytes = env_bytes
                .checked_add(key.len() + value.len())
                .ok_or_else(|| {
                    ExecError::new(ExecErrorKind::InvalidSpec, "environment size overflow")
                })?;
        }
        if env_bytes > MAX_ENV_TOTAL_BYTES {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "environment is too large",
            ));
        }
        if self.stdin.len() > MAX_STDIN_BYTES {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "stdin is too large",
            ));
        }
        if self.timeout.is_zero() || self.timeout > MAX_TIMEOUT {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "invalid timeout",
            ));
        }
        if self.stream_limit == 0 || self.stream_limit > MAX_STREAM_BYTES {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "invalid stream output limit",
            ));
        }
        if !self.cwd.is_dir() {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "working directory must exist",
            ));
        }
        Ok(())
    }
}

impl fmt::Debug for ExecSpec {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ExecSpec")
            .field("argc", &self.argv.len())
            .field("argv", &"<redacted>")
            .field("cwd", &"<redacted>")
            .field("env_entries", &self.env.len())
            .field("env", &"<redacted>")
            .field("stdin_bytes", &self.stdin.len())
            .field("timeout_ms", &self.timeout.as_millis())
            .field("stream_limit", &self.stream_limit)
            .finish()
    }
}

fn valid_env_key(key: &str) -> bool {
    let mut chars = key.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|c| c == '_' || c.is_ascii_alphanumeric())
        && key.len() <= 128
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecTermination {
    Exited,
    TimedOut,
    Cancelled,
    OutputLimit,
    OutputError,
    StdinError,
    TerminationUncertain,
}

#[derive(Clone, Serialize)]
pub struct ExecOutcome {
    pub session_id: String,
    pub termination: ExecTermination,
    pub exit_code: Option<i32>,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub stdout_total_bytes: u64,
    pub stderr_total_bytes: u64,
    pub stdout_truncated: bool,
    pub stderr_truncated: bool,
    pub output_complete: bool,
    pub duration_ms: u64,
}

impl ExecOutcome {
    pub fn command_ok(&self) -> bool {
        self.termination == ExecTermination::Exited
            && self.exit_code == Some(0)
            && self.output_complete
            && !self.stdout_truncated
            && !self.stderr_truncated
    }
}

impl fmt::Debug for ExecOutcome {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ExecOutcome")
            .field("session_id", &self.session_id)
            .field("termination", &self.termination)
            .field("exit_code", &self.exit_code)
            .field("stdout_bytes", &self.stdout.len())
            .field("stderr_bytes", &self.stderr.len())
            .field("stdout_total_bytes", &self.stdout_total_bytes)
            .field("stderr_total_bytes", &self.stderr_total_bytes)
            .field("output_complete", &self.output_complete)
            .field("duration_ms", &self.duration_ms)
            .finish()
    }
}

#[derive(Default)]
struct StreamState {
    retained: Vec<u8>,
    total: u64,
    truncated: bool,
}

type SharedStream = Arc<Mutex<StreamState>>;

#[derive(Clone)]
pub struct ProcessSession {
    id: String,
    cancel: watch::Sender<bool>,
    done: watch::Receiver<Option<ExecOutcome>>,
}

impl ProcessSession {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn snapshot(&self) -> Option<ExecOutcome> {
        self.done.borrow().clone()
    }

    pub async fn wait(&mut self) -> ExecOutcome {
        loop {
            if let Some(outcome) = self.done.borrow().clone() {
                return outcome;
            }
            if self.done.changed().await.is_err() {
                return uncertain_outcome(&self.id);
            }
        }
    }

    pub async fn cancel(&mut self) -> ExecOutcome {
        if self.done.borrow().is_none() {
            self.cancel.send_replace(true);
        }
        self.wait().await
    }
}

impl fmt::Debug for ProcessSession {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ProcessSession")
            .field("id", &self.id)
            .field("complete", &self.done.borrow().is_some())
            .finish()
    }
}

#[derive(Clone)]
pub struct ProcessManager {
    permits: Arc<Semaphore>,
    next_id: Arc<AtomicU64>,
}

impl ProcessManager {
    pub fn new(max_active: usize) -> Result<Self, ExecError> {
        if max_active == 0 || max_active > 32 {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "invalid active process limit",
            ));
        }
        Ok(Self {
            permits: Arc::new(Semaphore::new(max_active)),
            next_id: Arc::new(AtomicU64::new(1)),
        })
    }

    pub async fn run(&self, spec: ExecSpec) -> Result<ExecOutcome, ExecError> {
        let mut session = self.start(spec).await?;
        Ok(session.wait().await)
    }
}

impl Default for ProcessManager {
    fn default() -> Self {
        Self::new(4).expect("valid default process limit")
    }
}

fn uncertain_outcome(id: &str) -> ExecOutcome {
    ExecOutcome {
        session_id: id.to_owned(),
        termination: ExecTermination::TerminationUncertain,
        exit_code: None,
        stdout: Vec::new(),
        stderr: Vec::new(),
        stdout_total_bytes: 0,
        stderr_total_bytes: 0,
        stdout_truncated: false,
        stderr_truncated: false,
        output_complete: false,
        duration_ms: 0,
    }
}

#[cfg(test)]
#[path = "process_tests.rs"]
mod tests;

#[cfg(all(test, unix))]
#[path = "process_group_completion_tests.rs"]
mod group_completion_tests;

#[cfg(unix)]
#[path = "process_argv0.rs"]
mod argv0;

#[path = "process_supervisor.rs"]
mod supervisor;
#[cfg(all(test, unix))]
use supervisor::confirm_group_exit;
#[cfg(test)]
use supervisor::{read_bounded, take_stream};

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
    cwd: PathBuf,
    env: BTreeMap<String, String>,
    stdin: Vec<u8>,
    timeout: Duration,
    stream_limit: usize,
    #[cfg(target_os = "linux")]
    sandbox: Option<crate::LinuxSandbox>,
}

impl ExecSpec {
    pub fn new(argv: Vec<String>, cwd: impl Into<PathBuf>) -> Result<Self, ExecError> {
        let spec = Self {
            argv,
            cwd: cwd.into(),
            env: BTreeMap::new(),
            stdin: Vec::new(),
            timeout: Duration::from_secs(30),
            stream_limit: 64 * 1024,
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

    pub async fn start(&self, spec: ExecSpec) -> Result<ProcessSession, ExecError> {
        spec.validate()?;
        let cwd = std::fs::canonicalize(&spec.cwd).map_err(|_| {
            ExecError::new(ExecErrorKind::InvalidSpec, "working directory unavailable")
        })?;
        if !cwd.is_dir() {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "working directory must be a directory",
            ));
        }
        let permit =
            self.permits.clone().try_acquire_owned().map_err(|_| {
                ExecError::new(ExecErrorKind::Capacity, "process capacity exhausted")
            })?;

        let mut command = Command::new(&spec.argv[0]);
        command
            .args(&spec.argv[1..])
            .current_dir(&cwd)
            .env_clear()
            .envs(&spec.env)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(target_os = "linux")]
        if let Some(policy) = &spec.sandbox {
            let sandbox = policy
                .prepare(Path::new(&spec.argv[0]), &cwd)
                .map_err(|_| ExecError::new(ExecErrorKind::Sandbox, "sandbox setup rejected"))?;
            // Prepared state is owned by the closure; no allocation after fork.
            unsafe {
                command.pre_exec(move || sandbox.apply());
            }
        }

        let (mut child, tree) = process_tree::spawn(&mut command).await.map_err(|_| {
            #[cfg(target_os = "linux")]
            if spec.sandbox.is_some() {
                return ExecError::new(ExecErrorKind::Sandbox, "sandbox process startup rejected");
            }
            ExecError::new(ExecErrorKind::Spawn, "failed to spawn process")
        })?;
        let stdin = child.stdin.take();
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| ExecError::new(ExecErrorKind::Spawn, "stdout pipe unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| ExecError::new(ExecErrorKind::Spawn, "stderr pipe unavailable"))?;

        let id = format!("proc-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let stdout_state = Arc::new(Mutex::new(StreamState::default()));
        let stderr_state = Arc::new(Mutex::new(StreamState::default()));
        let (overflow_tx, mut overflow_rx) = mpsc::unbounded_channel();
        let stdout_task = tokio::spawn(read_bounded(
            stdout,
            stdout_state.clone(),
            spec.stream_limit,
            overflow_tx.clone(),
        ));
        let stderr_task = tokio::spawn(read_bounded(
            stderr,
            stderr_state.clone(),
            spec.stream_limit,
            overflow_tx,
        ));

        let (stdin_error_tx, mut stdin_error_rx) = mpsc::unbounded_channel();
        let stdin_bytes = spec.stdin;
        let stdin_task = tokio::spawn(async move {
            let result = async move {
                let mut input = stdin.ok_or_else(|| std::io::Error::other("stdin unavailable"))?;
                if !stdin_bytes.is_empty() {
                    input.write_all(&stdin_bytes).await?;
                }
                input.shutdown().await
            }
            .await;
            let complete = result.is_ok();
            if !complete {
                let _ = stdin_error_tx.send(());
            }
            complete
        });

        let (cancel_tx, mut cancel_rx) = watch::channel(false);
        let (done_tx, done_rx) = watch::channel(None);
        let supervisor_id = id.clone();
        let timeout = spec.timeout;
        tokio::spawn(async move {
            let _permit = permit;
            let start = Instant::now();
            let mut tree = tree;
            let deadline = tokio::time::sleep(timeout);
            tokio::pin!(deadline);

            let mut termination = ExecTermination::Exited;
            let mut status: Option<ExitStatus> = None;
            let mut must_terminate = false;
            tokio::select! {
                result = child.wait() => {
                    status = result.ok();
                }
                _ = &mut deadline => {
                    termination = ExecTermination::TimedOut;
                    must_terminate = true;
                }
                changed = cancel_rx.changed() => {
                    if changed.is_ok() && *cancel_rx.borrow() {
                        termination = ExecTermination::Cancelled;
                        must_terminate = true;
                    } else {
                        termination = ExecTermination::TerminationUncertain;
                        must_terminate = true;
                    }
                }
                Some(_) = overflow_rx.recv() => {
                    termination = ExecTermination::OutputLimit;
                    must_terminate = true;
                }
                Some(_) = stdin_error_rx.recv() => {
                    termination = ExecTermination::StdinError;
                    must_terminate = true;
                }
            }

            let mut termination_confirmed = true;
            if must_terminate {
                if tree.terminate().is_err() {
                    termination_confirmed = false;
                }
                let _ = child.start_kill();
                match tokio::time::timeout(TERMINATE_WAIT, child.wait()).await {
                    Ok(Ok(exit)) => status = Some(exit),
                    _ => termination_confirmed = false,
                }
            } else if tree.terminate().is_err() {
                termination_confirmed = false;
            }

            if !termination_confirmed {
                termination = ExecTermination::TerminationUncertain;
            }

            let io = join_io(stdout_task, stderr_task, stdin_task).await;
            let stdout = take_stream(&stdout_state);
            let stderr = take_stream(&stderr_state);
            let output_complete = io.stdout && io.stderr;
            if termination == ExecTermination::Exited {
                if stdout.truncated || stderr.truncated {
                    termination = ExecTermination::OutputLimit;
                } else if !io.stdin {
                    termination = ExecTermination::StdinError;
                } else if !output_complete {
                    termination = ExecTermination::OutputError;
                }
            }
            let duration_ms = start.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
            let outcome = ExecOutcome {
                session_id: supervisor_id,
                termination,
                exit_code: status.and_then(|value| value.code()),
                stdout: stdout.retained,
                stderr: stderr.retained,
                stdout_total_bytes: stdout.total,
                stderr_total_bytes: stderr.total,
                stdout_truncated: stdout.truncated,
                stderr_truncated: stderr.truncated,
                output_complete,
                duration_ms,
            };
            done_tx.send_replace(Some(outcome));
        });

        Ok(ProcessSession {
            id,
            cancel: cancel_tx,
            done: done_rx,
        })
    }
}

impl Default for ProcessManager {
    fn default() -> Self {
        Self::new(4).expect("valid default process limit")
    }
}

async fn read_bounded<R>(
    mut stream: R,
    state: SharedStream,
    limit: usize,
    overflow: mpsc::UnboundedSender<()>,
) -> bool
where
    R: AsyncRead + Unpin,
{
    let mut signalled = false;
    let mut buf = [0u8; 4096];
    loop {
        let read = match stream.read(&mut buf).await {
            Ok(read) => read,
            Err(_) => return false,
        };
        if read == 0 {
            return true;
        }
        let mut shared = match state.lock() {
            Ok(value) => value,
            Err(_) => return false,
        };
        shared.total = shared.total.saturating_add(read as u64);
        let remaining = limit.saturating_sub(shared.retained.len());
        let keep = remaining.min(read);
        if keep != 0 {
            shared.retained.extend_from_slice(&buf[..keep]);
        }
        if keep < read {
            shared.truncated = true;
            if !signalled {
                signalled = true;
                let _ = overflow.send(());
            }
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct IoCompletion {
    stdout: bool,
    stderr: bool,
    stdin: bool,
}

async fn join_io(
    mut stdout: JoinHandle<bool>,
    mut stderr: JoinHandle<bool>,
    mut stdin: JoinHandle<bool>,
) -> IoCompletion {
    let readers = async {
        IoCompletion {
            stdout: (&mut stdout).await.unwrap_or(false),
            stderr: (&mut stderr).await.unwrap_or(false),
            stdin: (&mut stdin).await.unwrap_or(false),
        }
    };
    match tokio::time::timeout(READER_WAIT, readers).await {
        Ok(done) => done,
        Err(_) => {
            stdout.abort();
            stderr.abort();
            stdin.abort();
            let _ = stdout.await;
            let _ = stderr.await;
            let _ = stdin.await;
            IoCompletion::default()
        }
    }
}

fn take_stream(state: &SharedStream) -> StreamState {
    let Ok(mut guard) = state.lock() else {
        return StreamState {
            retained: Vec::new(),
            total: 0,
            truncated: true,
        };
    };
    std::mem::take(&mut *guard)
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
mod tests {
    use super::*;

    #[test]
    fn spec_bounds_fail_before_spawn() {
        let cwd = std::env::current_dir().unwrap();
        assert!(ExecSpec::new(Vec::new(), &cwd).is_err());
        assert!(ExecSpec::new(vec!["relative-program".into()], &cwd).is_err());

        let exe = std::env::current_exe().unwrap().display().to_string();
        assert!(ExecSpec::new(vec![exe.clone(), "x".repeat(MAX_TOKEN_BYTES + 1)], &cwd).is_err());
        assert!(ExecSpec::new(vec![exe.clone()], &cwd)
            .unwrap()
            .with_stdin(vec![0; MAX_STDIN_BYTES + 1])
            .is_err());
        assert!(ExecSpec::new(vec![exe.clone()], &cwd)
            .unwrap()
            .with_timeout(Duration::ZERO)
            .is_err());
        assert!(ExecSpec::new(vec![exe], &cwd)
            .unwrap()
            .with_stream_limit(MAX_STREAM_BYTES + 1)
            .is_err());
    }

    #[tokio::test]
    async fn stream_read_error_is_incomplete_not_success() {
        use std::{
            pin::Pin,
            task::{Context, Poll},
        };
        use tokio::io::ReadBuf;

        struct ErrorAfterData {
            delivered: bool,
        }

        impl AsyncRead for ErrorAfterData {
            fn poll_read(
                self: Pin<&mut Self>,
                _cx: &mut Context<'_>,
                buf: &mut ReadBuf<'_>,
            ) -> Poll<std::io::Result<()>> {
                let this = self.get_mut();
                if !this.delivered {
                    this.delivered = true;
                    buf.put_slice(b"partial");
                    Poll::Ready(Ok(()))
                } else {
                    Poll::Ready(Err(std::io::Error::other("fixture read failure")))
                }
            }
        }

        let state = Arc::new(Mutex::new(StreamState::default()));
        let (overflow, _rx) = mpsc::unbounded_channel();
        let complete = read_bounded(
            ErrorAfterData { delivered: false },
            state.clone(),
            1024,
            overflow,
        )
        .await;
        assert!(!complete);
        let captured = take_stream(&state);
        assert_eq!(captured.retained, b"partial");
        assert!(!captured.truncated);
    }

    #[test]
    fn debug_redacts_command_environment_and_working_directory() {
        let cwd = std::env::current_dir().unwrap();
        let exe = std::env::current_exe().unwrap().display().to_string();
        let spec = ExecSpec::new(vec![exe, "secret-argument".into()], &cwd)
            .unwrap()
            .with_env("SECRET_KEY", "secret-value")
            .unwrap();
        let rendered = format!("{spec:?}");
        assert!(!rendered.contains("secret-argument"));
        assert!(!rendered.contains("secret-value"));
        assert!(!rendered.contains(&cwd.display().to_string()));
    }
}

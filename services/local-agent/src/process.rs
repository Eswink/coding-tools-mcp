use crate::{
    Capability, ExecPolicy, ExecutionAuthorization, ScopedApproval, ToolCall, VerifiedInvocation,
};
use crate::policy::Command as PolicyCommand;
use crate::process_tree;
use std::{
    collections::{BTreeMap, VecDeque},
    fmt,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt},
    process::Command,
    sync::{mpsc, Notify},
    task::JoinHandle,
    time::Instant,
};

pub const MAX_SESSIONS: usize = 8;
pub const MAX_RETAINED_STREAM_BYTES: usize = 256 * 1024;
pub const MAX_READ_BYTES: usize = 64 * 1024;
pub const MAX_TIMEOUT_MS: u64 = 10 * 60 * 1000;
const SUPERVISOR_TICK: Duration = Duration::from_millis(20);
const READER_DRAIN_TIMEOUT: Duration = Duration::from_secs(2);
const CHILD_WAIT_TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct ProcessId(u64);

impl ProcessId {
    pub fn get(self) -> u64 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TerminationReason {
    Exited,
    TimedOut,
    Killed,
    IoFailed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProcessErrorKind {
    InvalidRequest,
    Unauthorized,
    PolicyDenied,
    Backpressure,
    SpawnFailed,
    NotFound,
    InvalidCursor,
    Io,
}

#[derive(Clone)]
pub struct ProcessError {
    pub kind: ProcessErrorKind,
    message: &'static str,
}

impl ProcessError {
    const fn new(kind: ProcessErrorKind, message: &'static str) -> Self {
        Self { kind, message }
    }

    pub fn public_message(&self) -> &'static str {
        self.message
    }
}

impl fmt::Debug for ProcessError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ProcessError")
            .field("kind", &self.kind)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for ProcessError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message)
    }
}

impl std::error::Error for ProcessError {}

#[derive(Clone)]
pub struct SpawnRequest {
    executable: String,
    args: Vec<String>,
    cwd: PathBuf,
    timeout: Duration,
}

impl SpawnRequest {
    pub fn new(
        executable: impl Into<String>,
        args: Vec<String>,
        cwd: PathBuf,
        timeout_ms: u64,
    ) -> Result<Self, ProcessError> {
        let executable = executable.into();
        if executable.is_empty()
            || executable.len() > 4096
            || executable.chars().any(char::is_control)
            || !Path::new(&executable).is_absolute()
            || args.len() > 128
            || args
                .iter()
                .any(|arg| arg.len() > 4096 || arg.chars().any(char::is_control))
            || !cwd.is_absolute()
            || !(1..=MAX_TIMEOUT_MS).contains(&timeout_ms)
        {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidRequest,
                "invalid process spawn request",
            ));
        }
        let total = args
            .iter()
            .try_fold(executable.len(), |sum, value| sum.checked_add(value.len()))
            .ok_or_else(|| {
                ProcessError::new(ProcessErrorKind::InvalidRequest, "process arguments are too large")
            })?;
        if total > 64 * 1024 {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidRequest,
                "process arguments are too large",
            ));
        }
        Ok(Self {
            executable,
            args,
            cwd,
            timeout: Duration::from_millis(timeout_ms),
        })
    }

    fn policy_command(&self) -> Result<PolicyCommand, ProcessError> {
        let mut argv = Vec::with_capacity(self.args.len() + 1);
        argv.push(self.executable.clone());
        argv.extend(self.args.iter().cloned());
        PolicyCommand::new(argv).map_err(|_| {
            ProcessError::new(ProcessErrorKind::InvalidRequest, "invalid policy command")
        })
    }
}

impl fmt::Debug for SpawnRequest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SpawnRequest")
            .field("executable", &"<redacted>")
            .field("argc", &self.args.len())
            .field("cwd", &"<workspace>")
            .field("timeout_ms", &self.timeout.as_millis())
            .finish()
    }
}

#[derive(Clone, Debug)]
pub struct ExecutionRoot {
    canonical_root: PathBuf,
    generation: u64,
}

impl ExecutionRoot {
    pub(crate) async fn from_verified(
        verified: &VerifiedInvocation<'_>,
        root: PathBuf,
    ) -> Result<Self, ProcessError> {
        if !root.is_absolute() {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidRequest,
                "workspace root must be absolute",
            ));
        }
        let canonical_root = tokio::fs::canonicalize(root)
            .await
            .map_err(|_| ProcessError::new(ProcessErrorKind::InvalidRequest, "workspace root unavailable"))?;
        if !canonical_root.is_dir() {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidRequest,
                "workspace root is not a directory",
            ));
        }
        Ok(Self {
            canonical_root,
            generation: verified.generation(),
        })
    }

    async fn resolve_cwd(
        &self,
        cwd: &Path,
        verified: &VerifiedInvocation<'_>,
    ) -> Result<PathBuf, ProcessError> {
        if self.generation != verified.generation() || !cwd.is_absolute() {
            return Err(ProcessError::new(
                ProcessErrorKind::Unauthorized,
                "local execution root is stale",
            ));
        }
        let canonical = tokio::fs::canonicalize(cwd)
            .await
            .map_err(|_| ProcessError::new(ProcessErrorKind::InvalidRequest, "working directory unavailable"))?;
        if !canonical.starts_with(&self.canonical_root) {
            return Err(ProcessError::new(
                ProcessErrorKind::Unauthorized,
                "working directory is outside the workspace root",
            ));
        }
        Ok(canonical)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OutputCursor(pub u64);

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OutputChunk {
    pub data: Vec<u8>,
    pub next: OutputCursor,
    pub truncated_before_cursor: bool,
    pub eof: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProcessStatus {
    pub termination: Option<TerminationReason>,
    pub exit_code: Option<i32>,
}

impl ProcessStatus {
    pub fn running(self) -> bool {
        self.termination.is_none()
    }
}

#[derive(Debug)]
struct BufferState {
    base: u64,
    total: u64,
    bytes: VecDeque<u8>,
}

#[derive(Debug)]
struct OutputBuffer {
    inner: Mutex<BufferState>,
}

impl OutputBuffer {
    fn new() -> Self {
        Self {
            inner: Mutex::new(BufferState {
                base: 0,
                total: 0,
                bytes: VecDeque::new(),
            }),
        }
    }

    fn append(&self, data: &[u8]) {
        let mut state = self.inner.lock().expect("output buffer lock");
        state.total = state.total.saturating_add(data.len() as u64);
        state.bytes.extend(data.iter().copied());
        while state.bytes.len() > MAX_RETAINED_STREAM_BYTES {
            state.bytes.pop_front();
            state.base = state.base.saturating_add(1);
        }
    }

    fn read(
        &self,
        cursor: OutputCursor,
        limit: usize,
        terminal: bool,
    ) -> Result<OutputChunk, ProcessError> {
        if limit == 0 || limit > MAX_READ_BYTES {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidCursor,
                "invalid output read limit",
            ));
        }
        let state = self.inner.lock().expect("output buffer lock");
        if cursor.0 > state.total {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidCursor,
                "output cursor is beyond the stream",
            ));
        }
        let start = cursor.0.max(state.base);
        let offset = usize::try_from(start - state.base).map_err(|_| {
            ProcessError::new(ProcessErrorKind::InvalidCursor, "output cursor overflow")
        })?;
        let available = state.bytes.len().saturating_sub(offset);
        let take = available.min(limit);
        let data = state
            .bytes
            .iter()
            .skip(offset)
            .take(take)
            .copied()
            .collect::<Vec<_>>();
        let next = start.saturating_add(take as u64);
        Ok(OutputChunk {
            data,
            next: OutputCursor(next),
            truncated_before_cursor: cursor.0 < state.base,
            eof: terminal && next >= state.total,
        })
    }
}

#[derive(Debug)]
struct SessionState {
    termination: Option<TerminationReason>,
    exit_code: Option<i32>,
}

enum Control {
    Kill,
}

pub struct ProcessSession {
    id: ProcessId,
    control: mpsc::Sender<Control>,
    state: Arc<Mutex<SessionState>>,
    notify: Arc<Notify>,
    stdout: Arc<OutputBuffer>,
    stderr: Arc<OutputBuffer>,
}

impl ProcessSession {
    pub fn id(&self) -> ProcessId {
        self.id
    }

    pub fn status(&self) -> ProcessStatus {
        let state = self.state.lock().expect("process state lock");
        ProcessStatus {
            termination: state.termination,
            exit_code: state.exit_code,
        }
    }

    pub async fn wait(&self) -> ProcessStatus {
        loop {
            let notified = self.notify.notified();
            tokio::pin!(notified);
            // Register with Notify before inspecting terminal state. Without this,
            // notify_waiters() can race between the state read and first poll.
            notified.as_mut().enable();
            let status = self.status();
            if !status.running() {
                return status;
            }
            notified.await;
        }
    }

    pub async fn kill(&self) -> Result<ProcessStatus, ProcessError> {
        if !self.status().running() {
            return Ok(self.status());
        }
        self.control
            .send(Control::Kill)
            .await
            .map_err(|_| ProcessError::new(ProcessErrorKind::Io, "process supervisor unavailable"))?;
        Ok(self.wait().await)
    }

    pub fn read_stdout(
        &self,
        cursor: OutputCursor,
        limit: usize,
    ) -> Result<OutputChunk, ProcessError> {
        self.stdout.read(cursor, limit, !self.status().running())
    }

    pub fn read_stderr(
        &self,
        cursor: OutputCursor,
        limit: usize,
    ) -> Result<OutputChunk, ProcessError> {
        self.stderr.read(cursor, limit, !self.status().running())
    }
}

impl fmt::Debug for ProcessSession {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ProcessSession")
            .field("id", &self.id)
            .field("status", &self.status())
            .field("stdout", &"<bounded>")
            .field("stderr", &"<bounded>")
            .finish()
    }
}

impl Drop for ProcessSession {
    fn drop(&mut self) {
        let _ = self.control.try_send(Control::Kill);
    }
}

pub struct SpawnContext<'a> {
    call: &'a ToolCall,
    verified: &'a VerifiedInvocation<'a>,
    root: &'a ExecutionRoot,
    policy: &'a ExecPolicy,
    approval: Option<&'a ScopedApproval>,
    now_unix_ms: u64,
}

impl<'a> SpawnContext<'a> {
    pub fn new(
        call: &'a ToolCall,
        verified: &'a VerifiedInvocation<'a>,
        root: &'a ExecutionRoot,
        policy: &'a ExecPolicy,
        now_unix_ms: u64,
    ) -> Self {
        Self {
            call,
            verified,
            root,
            policy,
            approval: None,
            now_unix_ms,
        }
    }

    pub fn with_approval(mut self, approval: &'a ScopedApproval) -> Self {
        self.approval = Some(approval);
        self
    }
}

pub struct ProcessManager {
    next_id: AtomicU64,
    sessions: Mutex<BTreeMap<ProcessId, Arc<ProcessSession>>>,
}

impl Default for ProcessManager {
    fn default() -> Self {
        Self::new()
    }
}

impl ProcessManager {
    pub fn new() -> Self {
        Self {
            next_id: AtomicU64::new(1),
            sessions: Mutex::new(BTreeMap::new()),
        }
    }

    pub async fn spawn(
        &self,
        request: SpawnRequest,
        context: SpawnContext<'_>,
    ) -> Result<Arc<ProcessSession>, ProcessError> {
        if context.now_unix_ms > context.verified.expires_at_unix_ms()
            || !context.verified.has_capability(Capability::ProcessExec)
        {
            return Err(ProcessError::new(
                ProcessErrorKind::Unauthorized,
                "local process admission rejected",
            ));
        }

        let command_for_policy = request.policy_command()?;
        match context.policy.authorize(
            &command_for_policy,
            context.call,
            context.verified,
            context.approval,
            context.now_unix_ms,
        ) {
            ExecutionAuthorization::Allowed => {}
            ExecutionAuthorization::ApprovalRequired
            | ExecutionAuthorization::Forbidden
            | ExecutionAuthorization::NoMatchingRule => {
                return Err(ProcessError::new(
                    ProcessErrorKind::PolicyDenied,
                    "execution policy did not allow the process",
                ))
            }
        }

        let cwd = context
            .root
            .resolve_cwd(&request.cwd, context.verified)
            .await?;
        {
            let sessions = self.sessions.lock().expect("process manager lock");
            if sessions.len() >= MAX_SESSIONS {
                return Err(ProcessError::new(
                    ProcessErrorKind::Backpressure,
                    "process session limit reached",
                ));
            }
        }

        let mut command = Command::new(&request.executable);
        command
            .args(&request.args)
            .current_dir(cwd)
            .env_clear()
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        if let Some(system_root) = std::env::var_os("SystemRoot") {
            command.env("SystemRoot", system_root);
        }

        let (mut child, tree) = process_tree::spawn(&mut command)
            .await
            .map_err(|_| ProcessError::new(ProcessErrorKind::SpawnFailed, "process spawn failed"))?;
        let stdout = child.stdout.take().ok_or_else(|| {
            ProcessError::new(ProcessErrorKind::SpawnFailed, "process stdout unavailable")
        })?;
        let stderr = child.stderr.take().ok_or_else(|| {
            ProcessError::new(ProcessErrorKind::SpawnFailed, "process stderr unavailable")
        })?;

        let id = ProcessId(self.next_id.fetch_add(1, Ordering::Relaxed));
        if id.0 == 0 {
            return Err(ProcessError::new(
                ProcessErrorKind::Backpressure,
                "process identifier exhausted",
            ));
        }
        let (tx, rx) = mpsc::channel(2);
        let state = Arc::new(Mutex::new(SessionState {
            termination: None,
            exit_code: None,
        }));
        let notify = Arc::new(Notify::new());
        let stdout_buffer = Arc::new(OutputBuffer::new());
        let stderr_buffer = Arc::new(OutputBuffer::new());

        let session = Arc::new(ProcessSession {
            id,
            control: tx,
            state: state.clone(),
            notify: notify.clone(),
            stdout: stdout_buffer.clone(),
            stderr: stderr_buffer.clone(),
        });

        let capacity_full = {
            let mut sessions = self.sessions.lock().expect("process manager lock");
            if sessions.len() >= MAX_SESSIONS {
                true
            } else {
                sessions.insert(id, session.clone());
                false
            }
        };
        if capacity_full {
            let mut tree = tree;
            let _ = tree.terminate();
            let _ = child.kill().await;
            return Err(ProcessError::new(
                ProcessErrorKind::Backpressure,
                "process session limit reached",
            ));
        }

        let stdout_task = tokio::spawn(read_stream(stdout, stdout_buffer));
        let stderr_task = tokio::spawn(read_stream(stderr, stderr_buffer));
        tokio::spawn(supervise(
            child,
            tree,
            rx,
            state,
            notify,
            stdout_task,
            stderr_task,
            request.timeout,
        ));

        Ok(session)
    }

    pub fn get(&self, id: ProcessId) -> Result<Arc<ProcessSession>, ProcessError> {
        self.sessions
            .lock()
            .expect("process manager lock")
            .get(&id)
            .cloned()
            .ok_or_else(|| ProcessError::new(ProcessErrorKind::NotFound, "process session not found"))
    }

    pub fn remove_terminal(&self, id: ProcessId) -> Result<(), ProcessError> {
        let mut sessions = self.sessions.lock().expect("process manager lock");
        let Some(session) = sessions.get(&id) else {
            return Err(ProcessError::new(
                ProcessErrorKind::NotFound,
                "process session not found",
            ));
        };
        if session.status().running() {
            return Err(ProcessError::new(
                ProcessErrorKind::InvalidRequest,
                "running process session cannot be removed",
            ));
        }
        sessions.remove(&id);
        Ok(())
    }

    pub fn session_count(&self) -> usize {
        self.sessions.lock().expect("process manager lock").len()
    }
}

async fn read_stream<R: AsyncRead + Unpin>(
    mut stream: R,
    output: Arc<OutputBuffer>,
) -> std::io::Result<()> {
    let mut chunk = [0u8; 8192];
    loop {
        let n = stream.read(&mut chunk).await?;
        if n == 0 {
            return Ok(());
        }
        output.append(&chunk[..n]);
    }
}

#[allow(clippy::too_many_arguments)]
async fn supervise(
    mut child: tokio::process::Child,
    mut tree: process_tree::ProcessTree,
    mut control: mpsc::Receiver<Control>,
    state: Arc<Mutex<SessionState>>,
    notify: Arc<Notify>,
    stdout_task: JoinHandle<std::io::Result<()>>,
    stderr_task: JoinHandle<std::io::Result<()>>,
    timeout: Duration,
) {
    let deadline = Instant::now() + timeout;
    let (mut reason, mut exit_code) = loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                // The direct child exited, but detached/background descendants can still
                // exist in the owned process group/job. Tear down the remaining tree
                // before reporting a terminal session.
                let cleanup_ok = tree.terminate().is_ok();
                if cleanup_ok {
                    break (TerminationReason::Exited, status.code());
                }
                break (TerminationReason::IoFailed, None);
            }
            Ok(None) => {}
            Err(_) => {
                let _ = tree.terminate();
                let _ = child.start_kill();
                break (TerminationReason::IoFailed, None);
            }
        }

        if Instant::now() >= deadline {
            let _ = tree.terminate();
            let _ = child.start_kill();
            let status = tokio::time::timeout(CHILD_WAIT_TIMEOUT, child.wait()).await;
            let code = status.ok().and_then(Result::ok).and_then(|s| s.code());
            break (TerminationReason::TimedOut, code);
        }

        tokio::select! {
            command = control.recv() => {
                match command {
                    Some(Control::Kill) | None => {
                        let _ = tree.terminate();
                        let _ = child.start_kill();
                        let status = tokio::time::timeout(CHILD_WAIT_TIMEOUT, child.wait()).await;
                        let code = status.ok().and_then(Result::ok).and_then(|s| s.code());
                        break (TerminationReason::Killed, code);
                    }
                }
            }
            _ = tokio::time::sleep(SUPERVISOR_TICK) => {}
        }
    };

    let stdout_ok = reader_ok(stdout_task).await;
    let stderr_ok = reader_ok(stderr_task).await;
    if reason == TerminationReason::Exited && (!stdout_ok || !stderr_ok) {
        reason = TerminationReason::IoFailed;
        exit_code = None;
    }

    {
        let mut current = state.lock().expect("process state lock");
        current.termination = Some(reason);
        current.exit_code = exit_code;
    }
    notify.notify_waiters();
}

async fn reader_ok(task: JoinHandle<std::io::Result<()>>) -> bool {
    tokio::time::timeout(READER_DRAIN_TIMEOUT, task)
        .await
        .is_ok_and(|join| join.is_ok_and(|result| result.is_ok()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spawn_request_debug_redacts_command_and_workspace() {
        let cwd = std::env::current_dir().unwrap();
        let executable = std::env::current_exe().unwrap();
        let request = SpawnRequest::new(
            executable.to_string_lossy(),
            vec!["secret-argument".into()],
            cwd,
            1000,
        )
        .unwrap();
        let rendered = format!("{request:?}");
        assert!(!rendered.contains("secret-argument"));
        assert!(!rendered.contains(&executable.to_string_lossy().to_string()));
    }

    fn fixture_context(
        executable: &str,
    ) -> (
        crate::LocalAdmission,
        ToolCall,
        ExecPolicy,
    ) {
        let admission = crate::LocalAdmission::fixture(
            "conversation-a",
            "workspace-a",
            [Capability::ProcessExec],
            7,
            60_000,
        );
        let call = ToolCall::new(
            "request-a",
            "conversation-a",
            "workspace-a",
            crate::ToolName::parse("exec_command").unwrap(),
            serde_json::json!({}),
        )
        .unwrap();
        let rule = crate::PrefixRule::new(
            vec![crate::TokenPattern::exact(executable).unwrap()],
            crate::ExecDecision::Allow,
        )
        .unwrap();
        let policy = ExecPolicy::new(vec![rule], vec![], false).unwrap();
        (admission, call, policy)
    }

    #[test]
    fn process_child_echo() {
        if std::env::args().any(|arg| arg == "--exact") {
            println!("ctm-process-echo");
        }
    }

    #[test]
    fn process_child_timeout_fixture() {
        if std::env::args().any(|arg| arg == "--exact") {
            std::thread::sleep(Duration::from_secs(30));
        }
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn manager_runs_structured_argv_and_captures_bounded_output() {
        let executable = std::env::current_exe().unwrap();
        let executable_text = executable.to_string_lossy().to_string();
        let cwd = std::env::current_dir().unwrap();
        let (admission, call, policy) = fixture_context(&executable_text);
        let verified = VerifiedInvocation::fixture(&admission);
        let root = ExecutionRoot::from_verified(&verified, cwd.clone())
            .await
            .unwrap();
        let request = SpawnRequest::new(
            executable_text,
            vec![
                "--exact".into(),
                "process::tests::process_child_echo".into(),
                "--nocapture".into(),
            ],
            cwd,
            10_000,
        )
        .unwrap();
        let manager = ProcessManager::new();
        let session = manager
            .spawn(
                request,
                SpawnContext::new(&call, &verified, &root, &policy, 100),
            )
            .await
            .unwrap();
        let status = session.wait().await;
        assert_eq!(status.termination, Some(TerminationReason::Exited));
        assert_eq!(status.exit_code, Some(0));
        let stdout = session.read_stdout(OutputCursor(0), MAX_READ_BYTES).unwrap();
        assert!(String::from_utf8_lossy(&stdout.data).contains("ctm-process-echo"));
        assert!(stdout.eof);
        manager.remove_terminal(session.id()).unwrap();
        assert_eq!(manager.session_count(), 0);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn timeout_is_distinct_and_terminal() {
        let executable = std::env::current_exe().unwrap();
        let executable_text = executable.to_string_lossy().to_string();
        let cwd = std::env::current_dir().unwrap();
        let (admission, call, policy) = fixture_context(&executable_text);
        let verified = VerifiedInvocation::fixture(&admission);
        let root = ExecutionRoot::from_verified(&verified, cwd.clone())
            .await
            .unwrap();
        let request = SpawnRequest::new(
            executable_text,
            vec![
                "--exact".into(),
                "process::tests::process_child_timeout_fixture".into(),
                "--nocapture".into(),
            ],
            cwd,
            150,
        )
        .unwrap();
        let manager = ProcessManager::new();
        let session = manager
            .spawn(
                request,
                SpawnContext::new(&call, &verified, &root, &policy, 100),
            )
            .await
            .unwrap();
        let status = session.wait().await;
        assert_eq!(status.termination, Some(TerminationReason::TimedOut));
    }

    #[tokio::test]
    async fn no_match_prompt_and_missing_capability_fail_before_spawn() {
        let executable = std::env::current_exe().unwrap();
        let executable_text = executable.to_string_lossy().to_string();
        let cwd = std::env::current_dir().unwrap();
        let admission = crate::LocalAdmission::fixture(
            "conversation-a",
            "workspace-a",
            [],
            7,
            60_000,
        );
        let verified = VerifiedInvocation::fixture(&admission);
        let root = ExecutionRoot::from_verified(&verified, cwd.clone())
            .await
            .unwrap();
        let call = ToolCall::new(
            "request-a",
            "conversation-a",
            "workspace-a",
            crate::ToolName::parse("exec_command").unwrap(),
            serde_json::json!({}),
        )
        .unwrap();
        let policy = ExecPolicy::new(vec![], vec![], false).unwrap();
        let request = SpawnRequest::new(executable_text, vec![], cwd, 1_000).unwrap();
        let error = ProcessManager::new()
            .spawn(
                request,
                SpawnContext::new(&call, &verified, &root, &policy, 100),
            )
            .await
            .unwrap_err();
        assert_eq!(error.kind, ProcessErrorKind::Unauthorized);
    }

    #[tokio::test]
    async fn non_allow_policy_results_fail_before_process_creation() {
        let executable = std::env::current_exe().unwrap();
        let executable_text = executable.to_string_lossy().to_string();
        let cwd = std::env::current_dir().unwrap();
        let admission = crate::LocalAdmission::fixture(
            "conversation-a",
            "workspace-a",
            [Capability::ProcessExec],
            7,
            60_000,
        );
        let verified = VerifiedInvocation::fixture(&admission);
        let root = ExecutionRoot::from_verified(&verified, cwd.clone())
            .await
            .unwrap();
        let call = ToolCall::new(
            "request-policy-denied",
            "conversation-a",
            "workspace-a",
            crate::ToolName::parse("exec_command").unwrap(),
            serde_json::json!({}),
        )
        .unwrap();

        for decision in [
            None,
            Some(crate::ExecDecision::Prompt),
            Some(crate::ExecDecision::Forbidden),
        ] {
            let policy = match decision {
                None => ExecPolicy::new(vec![], vec![], false).unwrap(),
                Some(decision) => ExecPolicy::new(
                    vec![
                        crate::PrefixRule::new(
                            vec![crate::TokenPattern::exact(&executable_text).unwrap()],
                            decision,
                        )
                        .unwrap(),
                    ],
                    vec![],
                    false,
                )
                .unwrap(),
            };
            let request = SpawnRequest::new(
                executable_text.clone(),
                vec!["--this-must-never-run".into()],
                cwd.clone(),
                1_000,
            )
            .unwrap();
            let manager = ProcessManager::new();
            let error = manager
                .spawn(
                    request,
                    SpawnContext::new(&call, &verified, &root, &policy, 100),
                )
                .await
                .unwrap_err();
            assert_eq!(error.kind, ProcessErrorKind::PolicyDenied);
            assert_eq!(manager.session_count(), 0);
        }
    }

    #[test]
    fn output_cursor_reports_truncation_without_unbounded_retention() {
        let output = OutputBuffer::new();
        let bytes = vec![b'x'; MAX_RETAINED_STREAM_BYTES + 32];
        output.append(&bytes);
        let chunk = output.read(OutputCursor(0), 64, true).unwrap();
        assert!(chunk.truncated_before_cursor);
        assert_eq!(chunk.data.len(), 64);
        assert!(chunk.next.0 >= 32);
    }
}

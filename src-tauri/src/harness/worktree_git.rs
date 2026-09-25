use std::ffi::OsString;
use std::io::{self, Read};
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use super::worktree::{WorktreeError, WorktreeResult};

const MAX_GIT_OUTPUT_BYTES: usize = 64 * 1024;
const GIT_TIMEOUT: Duration = Duration::from_secs(10);

pub(super) struct GitOutput {
    pub(super) success: bool,
    pub(super) stdout: Vec<u8>,
}

struct Capture {
    bytes: Vec<u8>,
    overflow: bool,
}

pub(super) fn run_git(cwd: &Path, args: &[OsString]) -> WorktreeResult<GitOutput> {
    let mut command = Command::new("git");
    command
        .current_dir(cwd)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW);
    }
    let mut child = command.spawn().map_err(|_| {
        error(
            "GIT_UNAVAILABLE",
            "Git is unavailable for managed worktree operations.",
        )
    })?;
    let stdout = child.stdout.take().ok_or_else(io_failure)?;
    let stderr = child.stderr.take().ok_or_else(io_failure)?;
    let budget = Arc::new(Mutex::new(0usize));
    let stdout_reader = spawn_reader(stdout, budget.clone());
    let stderr_reader = spawn_reader(stderr, budget);
    let deadline = Instant::now() + GIT_TIMEOUT;
    let status = loop {
        match child.try_wait().map_err(|_| io_failure())? {
            Some(status) => break status,
            None if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
            None => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = join_reader(stdout_reader);
                let _ = join_reader(stderr_reader);
                return Err(error("GIT_TIMEOUT", "Git command timed out."));
            }
        }
    };
    let stdout = join_reader(stdout_reader)?;
    let stderr = join_reader(stderr_reader)?;
    if stdout.overflow || stderr.overflow {
        return Err(error("OUTPUT_LIMIT", "Git output exceeded the configured limit."));
    }
    Ok(GitOutput {
        success: status.success(),
        stdout: stdout.bytes,
    })
}

fn spawn_reader<R>(reader: R, budget: Arc<Mutex<usize>>) -> thread::JoinHandle<io::Result<Capture>>
where
    R: Read + Send + 'static,
{
    thread::spawn(move || read_bounded(reader, budget))
}

fn read_bounded<R: Read>(mut reader: R, budget: Arc<Mutex<usize>>) -> io::Result<Capture> {
    let mut bytes = Vec::new();
    let mut overflow = false;
    let mut buffer = [0u8; 8192];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        let mut used = budget.lock().map_err(|_| io::Error::other("budget poisoned"))?;
        let remaining = MAX_GIT_OUTPUT_BYTES.saturating_sub(*used);
        let keep = remaining.min(read);
        bytes.extend_from_slice(&buffer[..keep]);
        *used += keep;
        if keep < read {
            overflow = true;
        }
    }
    Ok(Capture { bytes, overflow })
}

fn join_reader(handle: thread::JoinHandle<io::Result<Capture>>) -> WorktreeResult<Capture> {
    handle
        .join()
        .map_err(|_| io_failure())?
        .map_err(|_| io_failure())
}


fn error(code: &'static str, message: &'static str) -> WorktreeError {
    WorktreeError::new(code, message)
}

fn io_failure() -> WorktreeError {
    error("IO_FAILED", "Managed worktree I/O failed.")
}

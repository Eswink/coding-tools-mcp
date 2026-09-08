//! Async commands own a process group/job, not merely the shell process.
//! This controls ordinary descendants; it is not an OS security sandbox.
use std::io;
use tokio::process::{Child, Command};

#[cfg(windows)]
#[path = "进程树Windowsv2.rs"]
mod platform;
#[cfg(windows)]
pub(crate) use platform::ProcessTree;

#[cfg(unix)]
pub(crate) struct ProcessTree(Option<libc::pid_t>);

#[cfg(unix)]
impl ProcessTree {
    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        let Some(pgid) = self.0.take() else { return Ok(()); };
        // pgid comes only from our freshly spawned child, never from disk or a
        // remote parameter. Disarm immediately, before this identifier can age.
        let result = unsafe { libc::kill(-pgid, libc::SIGKILL) };
        if result == 0 { return Ok(()); }
        let err = io::Error::last_os_error();
        if err.raw_os_error() == Some(libc::ESRCH) { Ok(()) } else { Err(err) }
    }
}

#[cfg(unix)]
impl Drop for ProcessTree {
    fn drop(&mut self) { let _ = self.terminate(); }
}

pub(crate) async fn spawn(command: &mut Command) -> io::Result<(Child, ProcessTree)> {
    command.kill_on_drop(true);
    #[cfg(unix)]
    {
        command.process_group(0);
        let child = command.spawn()?;
        let id = child.id().ok_or_else(|| io::Error::other("Missing child process identity"))?;
        Ok((child, ProcessTree(Some(id as libc::pid_t))))
    }
    #[cfg(windows)]
    { platform::spawn(command).await }
}

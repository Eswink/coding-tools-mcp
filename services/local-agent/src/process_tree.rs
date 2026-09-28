//! Owned child-process tree lifecycle. This is lifecycle containment, not a security sandbox.
use std::io;
use tokio::process::{Child, Command};

#[cfg(windows)]
#[path = "process_tree_windows.rs"]
mod platform;
#[cfg(windows)]
pub(crate) use platform::ProcessTree;

#[cfg(unix)]
pub(crate) struct ProcessTree(Option<libc::pid_t>);

#[cfg(unix)]
impl ProcessTree {
    pub(crate) fn from_pgid(pgid: libc::pid_t) -> Self {
        Self(Some(pgid))
    }

    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        let Some(pgid) = self.0.take() else {
            return Ok(());
        };
        let result = unsafe { libc::kill(-pgid, libc::SIGKILL) };
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ESRCH) {
            Ok(())
        } else {
            Err(error)
        }
    }
}

#[cfg(unix)]
impl Drop for ProcessTree {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
}

pub(crate) async fn spawn(command: &mut Command) -> io::Result<(Child, ProcessTree)> {
    command.kill_on_drop(true);
    #[cfg(unix)]
    {
        command.process_group(0);
        let child = command.spawn()?;
        let id = child
            .id()
            .ok_or_else(|| io::Error::other("missing child process identity"))?;
        Ok((child, ProcessTree(Some(id as libc::pid_t))))
    }
    #[cfg(windows)]
    {
        platform::spawn(command).await
    }
}

//! Owned child-process tree lifecycle. This is lifecycle containment, not a security sandbox.
use std::io;
use tokio::process::{Child, Command};

#[cfg(windows)]
#[path = "process_tree_windows.rs"]
mod platform;
#[cfg(windows)]
pub(crate) use platform::ProcessTree;

/// A1 C4-b (SPEC-A1 v5.3 §4.2): the group id plus, on Linux, a pidfd for the
/// leader opened right after spawn (the leader is our unreaped child, so its
/// pid cannot have been reused yet). The leader is signalled through the pidfd,
/// never by a raw pid; the group itself is still terminated by `kill(-pgid)`.
/// pidfds are host-side only: the sandboxed child's seccomp still denies
/// `pidfd_*` (`sandbox/filter.rs`).
#[cfg(unix)]
pub(crate) struct ProcessTree(Option<libc::pid_t>, Option<std::os::fd::OwnedFd>);

/// `pidfd_open(2)` for our own freshly spawned, unreaped child. `None` where
/// pidfds are unavailable (non-Linux, or a kernel before 5.3): pgid only.
#[cfg(unix)]
fn leader_pidfd(pid: libc::pid_t) -> Option<std::os::fd::OwnedFd> {
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::FromRawFd;
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        (fd >= 0).then(|| unsafe { std::os::fd::OwnedFd::from_raw_fd(fd as libc::c_int) })
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = pid;
        None
    }
}

/// Signals the leader through its pidfd. A leader that is already gone (or a
/// zombie) is not an error.
#[cfg(unix)]
fn signal_leader(fd: &std::os::fd::OwnedFd) {
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        let _ = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
    }
    #[cfg(not(target_os = "linux"))]
    let _ = fd;
}

#[cfg(unix)]
impl ProcessTree {
    /// `pgid` is the pid of our own freshly spawned session/group leader.
    pub(crate) fn from_pgid(pgid: libc::pid_t) -> Self {
        Self(Some(pgid), leader_pidfd(pgid))
    }

    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        if let Some(leader) = self.1.take() {
            signal_leader(&leader);
        }
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
        let pid = id as libc::pid_t;
        Ok((child, ProcessTree(Some(pid), leader_pidfd(pid))))
    }
    #[cfg(windows)]
    {
        platform::spawn(command).await
    }
}

/// A1 C4-b: the process a held pidfd refers to (`Pid:` in its fdinfo; `-1`
/// once that process has been reaped).
#[cfg(all(test, target_os = "linux"))]
pub(crate) fn pidfd_target(tree: &ProcessTree) -> Option<libc::pid_t> {
    use std::os::fd::AsRawFd;
    let fd = tree.1.as_ref()?.as_raw_fd();
    let info = std::fs::read_to_string(format!("/proc/self/fdinfo/{fd}")).ok()?;
    info.lines()
        .find_map(|line| line.strip_prefix("Pid:"))
        .and_then(|pid| pid.trim().parse().ok())
}

#[cfg(all(test, target_os = "linux"))]
mod pidfd_tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;

    #[tokio::test]
    async fn the_leader_is_held_by_a_pidfd_and_killed_through_it() {
        let mut command = Command::new("/bin/sleep");
        command.arg("30");
        let (mut child, mut tree) = spawn(&mut command).await.unwrap();
        let pid = child.id().unwrap() as libc::pid_t;
        assert_eq!(pidfd_target(&tree), Some(pid));
        tree.terminate().unwrap();
        assert!(tree.0.is_none() && tree.1.is_none());
        let status = child.wait().await.unwrap();
        assert_eq!(status.signal(), Some(libc::SIGKILL));
    }

    #[tokio::test]
    async fn a_held_pidfd_reports_the_leader_reaped_instead_of_a_reused_pid() {
        let mut command = Command::new("/bin/true");
        let (mut child, tree) = spawn(&mut command).await.unwrap();
        let pid = child.id().unwrap() as libc::pid_t;
        assert_eq!(pidfd_target(&tree), Some(pid));
        assert!(child.wait().await.unwrap().success());
        // After the reap the pidfd still names that exact process (now gone),
        // never whichever process may later be given the same number.
        assert_eq!(pidfd_target(&tree), Some(-1));
    }
}

//! Async commands own a process group/job, not merely the shell process.
//! This controls ordinary descendants; it is not an OS security sandbox.
use std::io;
use tokio::process::{Child, Command};

#[cfg(windows)]
#[path = "进程树Windowsv2.rs"]
mod platform;
#[cfg(windows)]
pub(crate) use platform::ProcessTree;

/// A1 C4-b (SPEC-A1 v5.3 §4.2): the group id plus, on Linux, a pidfd for the
/// leader opened right after spawn (the leader is our unreaped child, so its
/// pid cannot have been reused yet). The leader is signalled through the pidfd,
/// never by a raw pid. A1 C4-c C: the group is killed by `kill(-pgid)` only
/// while that pidfd shows the leader unreaped (alive or a zombie), i.e. while
/// `pgid` still names this group; once the leader is reaped there is no group
/// kill on the old number. Worker descendants that escaped the group are the
/// cgroup's job (`cgroup.kill` on cancel); in the rlimit fallback they survive
/// (SPEC-A1 v5.5 known limitation).
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

/// A1 C4-c C: signal 0 through the pidfd succeeds while the leader exists
/// (running or zombie) and fails with `ESRCH` once it has been reaped.
#[cfg(unix)]
fn leader_unreaped(fd: &std::os::fd::OwnedFd) -> bool {
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        let result = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd.as_raw_fd(),
                0,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        result == 0 || io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = fd;
        true
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
    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        let leader = self.1.take();
        let Some(pgid) = self.0.take() else {
            if let Some(leader) = &leader {
                signal_leader(leader);
            }
            return Ok(());
        };
        if let Some(leader) = &leader {
            // A1 C4-c C: checked before the group kill. A reaped leader means
            // `pgid` may no longer be this group: never `kill(-pgid)` then.
            if !leader_unreaped(leader) {
                return Ok(());
            }
            signal_leader(leader);
        }
        // No pidfd (non-Linux, or a kernel before 5.3): the group kill alone.
        // pgid comes only from our freshly spawned child, never from disk or a
        // remote parameter. Disarm immediately, before this identifier can age.
        let result = unsafe { libc::kill(-pgid, libc::SIGKILL) };
        if result == 0 {
            return Ok(());
        }
        let err = io::Error::last_os_error();
        if err.raw_os_error() == Some(libc::ESRCH) {
            Ok(())
        } else {
            Err(err)
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
            .ok_or_else(|| io::Error::other("Missing child process identity"))?;
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

    /// The pid recorded in `file` by a background `sleep` of the group.
    fn straggler(file: &std::path::Path) -> libc::pid_t {
        for _ in 0..200 {
            if let Ok(text) = std::fs::read_to_string(file) {
                if let Ok(pid) = text.trim().parse() {
                    return pid;
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        panic!("no straggler pid in {file:?}");
    }

    /// Running (not gone, not a zombie awaiting its new parent).
    fn running(pid: libc::pid_t) -> bool {
        std::fs::read_to_string(format!("/proc/{pid}/stat"))
            .ok()
            .and_then(|stat| {
                stat.rsplit_once(") ")
                    .map(|(_, rest)| !rest.starts_with('Z'))
            })
            .unwrap_or(false)
    }

    fn pid_file(tag: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!("ctm-c4c-{tag}-{}", std::process::id()))
    }

    /// A1 C4-c C: once the leader has been reaped, terminate sends nothing to
    /// its old pgid, so a process now holding that group (here a leftover of
    /// the same group, standing in for any reuse) is untouched.
    #[tokio::test]
    async fn a_reaped_leader_means_no_kill_on_its_old_pgid() {
        let file = pid_file("reaped");
        let script = format!("sleep 30 >/dev/null 2>&1 & echo $! > '{}'", file.display());
        let mut command = Command::new("/bin/sh");
        command.args(["-c", &script]);
        let (mut child, mut tree) = spawn(&mut command).await.unwrap();
        assert!(child.wait().await.unwrap().success()); // the leader is reaped
        let pid = straggler(&file);
        let _ = std::fs::remove_file(&file);
        assert!(running(pid));
        tree.terminate().unwrap();
        std::thread::sleep(std::time::Duration::from_millis(200));
        let survived = running(pid);
        // Our own leftover, by its pid.
        unsafe { libc::kill(pid, libc::SIGKILL) };
        assert!(survived, "terminate killed the reaped leader's old group");
    }

    /// A1 C4-c C: while the leader is alive the whole group is killed.
    #[tokio::test]
    async fn a_live_leader_means_the_whole_group_is_killed() {
        let file = pid_file("live");
        let script = format!(
            "sleep 30 >/dev/null 2>&1 & echo $! > '{}'; exec sleep 30",
            file.display()
        );
        let mut command = Command::new("/bin/sh");
        command.args(["-c", &script]);
        let (mut child, mut tree) = spawn(&mut command).await.unwrap();
        let pid = straggler(&file);
        let _ = std::fs::remove_file(&file);
        tree.terminate().unwrap();
        assert_eq!(child.wait().await.unwrap().signal(), Some(libc::SIGKILL));
        let mut gone = false;
        for _ in 0..100 {
            if !running(pid) {
                gone = true;
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        if !gone {
            unsafe { libc::kill(pid, libc::SIGKILL) };
        }
        assert!(gone, "the group member survived terminate");
    }
}

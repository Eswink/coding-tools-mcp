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
/// never by a raw pid.
///
/// A1 C6s (SPEC-A1 v5.5 T5): the group is killed by `kill(-pgid)` only through
/// the group's holder (`GroupHold`): a minimal process of ours, spawned right
/// after the leader into the leader's group. While the holder is our own
/// unreaped child it is a member of that group, so `pgid` cannot be freed or
/// reused, whether or not the leader has already been reaped; so after
/// confirming the holder is still alive, one `kill(-pgid)` reaches exactly
/// this group (the holder included), and the holder is reaped afterwards.
/// Without a holder (it could not be spawned, or could not join the group),
/// or once the holder died on its own, there is no group kill at all: the
/// desktop has no worker cgroup, so such leftovers survive (residual risk,
/// SPEC-A1 v5.5 T5). Processes that left the group (`setsid`/`setpgid`) are
/// never reached by the group kill (SPEC-A1 v5.5 known limitation).
/// pidfds are host-side only: the sandboxed child's seccomp still denies
/// `pidfd_*` (`sandbox/filter.rs`).
#[cfg(unix)]
pub(crate) struct ProcessTree(Option<libc::pid_t>, Option<std::os::fd::OwnedFd>, GroupHold);

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

/// A1 C6s: what the tree did about its group. A `kill(-pgid)` is sent only on
/// the way to `KilledWithHolder` or `KillFailed`, i.e. after the holder was
/// confirmed alive; the `Skipped*` outcomes never signal the group.
#[cfg(unix)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(not(test), allow(dead_code))]
pub(crate) enum GroupCleanup {
    /// The holder is in the group; `terminate` has not run yet.
    Pending,
    /// The holder was alive, so the group was killed once (holder included).
    KilledWithHolder,
    /// No holder: it could not be spawned or could not join the group.
    SkippedNoHolder,
    /// The holder had died on its own (or could not be checked) before.
    SkippedHolderDied,
    /// The group kill itself failed with something other than `ESRCH`.
    KillFailed,
}

/// A1 C6s: the program the holder runs: it only has to stay alive, without
/// touching anything. A fresh `exec` (not a bare `fork`) gives it no copy of
/// our address space, threads, locks or signal handlers; `sleep` exists on
/// every supported Unix host and takes this argument everywhere (68 years).
#[cfg(unix)]
const HOLDER_PROGRAM: &str = "/bin/sleep";
#[cfg(unix)]
const HOLDER_ARG: &str = "2147483647";

/// Spawns a holder, or how it fails (tests inject failures).
#[cfg(unix)]
type SpawnHolder = fn(libc::pid_t) -> io::Result<std::process::Child>;
/// Sends the one group kill (tests inject a counter).
#[cfg(unix)]
type KillGroup = fn(libc::pid_t) -> io::Result<()>;

/// A1 C6s: spawns the holder into group `pgid` (`0`: a new group of its own).
/// Its stdio is `/dev/null` and every other inherited fd
/// is close-on-exec, so it can hold none of the worker's pipes open; its cwd
/// is `/` and its environment is empty. `setpgid` runs in the holder before
/// `exec` and `spawn` returns only after the `exec`, so a holder that failed
/// to join is an error, never a holder outside the group; the membership is
/// re-read once more (`getpgid`).
#[cfg(unix)]
fn spawn_holder(pgid: libc::pid_t) -> io::Result<std::process::Child> {
    use std::os::unix::process::CommandExt;
    use std::process::Stdio;
    let mut command = std::process::Command::new(HOLDER_PROGRAM);
    command
        .arg(HOLDER_ARG)
        .env_clear()
        .current_dir("/")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .process_group(pgid);
    unsafe {
        command.pre_exec(|| {
            cloexec_inherited_fds();
            Ok(())
        });
    }
    let mut holder = command.spawn()?;
    let pid = holder.id() as libc::pid_t;
    let expected = if pgid == 0 { pid } else { pgid };
    if unsafe { libc::getpgid(pid) } != expected {
        // Our own unreaped child, by its pid.
        let _ = holder.kill();
        let _ = holder.wait();
        return Err(io::Error::other("group holder outside the group"));
    }
    Ok(holder)
}

/// In the forked holder, before `exec`: marks every fd above stderr
/// close-on-exec (async-signal-safe syscalls only). `close_range` with
/// `CLOSE_RANGE_CLOEXEC` (Linux >= 5.11) in one call, else one `fcntl` per fd.
#[cfg(unix)]
fn cloexec_inherited_fds() {
    #[cfg(target_os = "linux")]
    {
        const CLOSE_RANGE_CLOEXEC: libc::c_uint = 1 << 2;
        let done = unsafe {
            libc::syscall(
                libc::SYS_close_range,
                3u32,
                libc::c_uint::MAX,
                CLOSE_RANGE_CLOEXEC,
            )
        };
        if done == 0 {
            return;
        }
    }
    let mut limit: libc::rlimit = unsafe { std::mem::zeroed() };
    let top = if unsafe { libc::getrlimit(libc::RLIMIT_NOFILE, &mut limit) } == 0 {
        limit.rlim_cur.min(65_536) as libc::c_int
    } else {
        4096
    };
    for fd in 3..top {
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
        if flags >= 0 {
            unsafe { libc::fcntl(fd, libc::F_SETFD, flags | libc::FD_CLOEXEC) };
        }
    }
}

/// A1 C6s: the only group kill in this file. Reached only from
/// `GroupHold::kill_group`, after the holder was confirmed alive.
#[cfg(unix)]
fn kill_held_group(pgid: libc::pid_t) -> io::Result<()> {
    if unsafe { libc::kill(-pgid, libc::SIGKILL) } == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

/// A1 C6s: the group's holder (our own unreaped child), what happened to the
/// group, and the group kill (injectable for tests).
#[cfg(unix)]
pub(crate) struct GroupHold {
    holder: Option<std::process::Child>,
    cleanup: GroupCleanup,
    kill_group: KillGroup,
}

#[cfg(unix)]
impl GroupHold {
    fn new(pgid: libc::pid_t, spawn: SpawnHolder, kill_group: KillGroup) -> Self {
        let holder = spawn(pgid).ok();
        let cleanup = if holder.is_some() {
            GroupCleanup::Pending
        } else {
            GroupCleanup::SkippedNoHolder
        };
        Self {
            holder,
            cleanup,
            kill_group,
        }
    }

    /// Kills group `pgid` once, if and only if the holder is confirmed alive,
    /// then reaps the holder. Why that is safe after the leader's reap: the
    /// kernel frees a pid number only when no task uses it as pid, pgid or
    /// sid, and the holder (alive, or at worst a zombie until our own reap
    /// below) uses `pgid` as its pgid, so the number still names this group.
    /// Nobody else can reap the holder (`std::process::Child`, never waited
    /// for anywhere else). A holder that already exited on its own (or whose
    /// state cannot be read) is reaped without any group kill.
    fn kill_group(&mut self, pgid: libc::pid_t) -> io::Result<()> {
        let Some(mut holder) = self.holder.take() else {
            return Ok(());
        };
        match holder.try_wait() {
            Ok(None) => {}
            Ok(Some(_)) | Err(_) => {
                self.cleanup = GroupCleanup::SkippedHolderDied;
                return Ok(());
            }
        }
        let result = (self.kill_group)(pgid);
        self.cleanup = if result.is_ok() {
            GroupCleanup::KilledWithHolder
        } else {
            // Our own unreaped child, by its pid.
            let _ = holder.kill();
            GroupCleanup::KillFailed
        };
        let _ = holder.wait();
        result
    }
}

#[cfg(unix)]
impl Drop for GroupHold {
    /// A holder never outlives its tree (`terminate` normally took it).
    fn drop(&mut self) {
        if let Some(mut holder) = self.holder.take() {
            let _ = holder.kill();
            let _ = holder.wait();
        }
    }
}

#[cfg(unix)]
impl ProcessTree {
    /// A1 C6s: a tree for our freshly spawned leader `pid` (= its pgid),
    /// with the group's holder spawned into that group.
    fn held(pid: libc::pid_t) -> Self {
        Self::held_with(pid, spawn_holder, kill_held_group)
    }

    fn held_with(pid: libc::pid_t, spawn: SpawnHolder, kill_group: KillGroup) -> Self {
        let leader = leader_pidfd(pid);
        Self(Some(pid), leader, GroupHold::new(pid, spawn, kill_group))
    }

    #[cfg(test)]
    fn group_cleanup(&self) -> GroupCleanup {
        self.2.cleanup
    }

    pub(crate) fn terminate(&mut self) -> io::Result<()> {
        let leader = self.1.take();
        if let Some(leader) = &leader {
            signal_leader(leader);
        }
        // pgid comes only from our freshly spawned child, never from disk or a
        // remote parameter. A1 C6s: the group kill happens only through the
        // holder check; with no holder (or a dead one) there is none, reaped
        // leader or not.
        match self.0.take() {
            Some(pgid) => self.2.kill_group(pgid),
            None => Ok(()),
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
        Ok((child, ProcessTree::held(pid)))
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

    std::thread_local! {
        static GROUP_KILLS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    }

    /// A1 C6s: the injected group kill: counts, then kills for real.
    fn counted_kill(pgid: libc::pid_t) -> io::Result<()> {
        GROUP_KILLS.with(|kills| kills.set(kills.get() + 1));
        kill_held_group(pgid)
    }

    fn group_kills() -> usize {
        GROUP_KILLS.with(|kills| kills.get())
    }

    fn no_holder(_: libc::pid_t) -> io::Result<std::process::Child> {
        Err(io::Error::other("injected holder spawn failure"))
    }

    /// A1 C6s: like `spawn`, with an injected holder spawn and a counted
    /// group kill.
    fn spawn_counted(command: &mut Command, holder: SpawnHolder) -> (Child, ProcessTree) {
        command.kill_on_drop(true);
        command.process_group(0);
        let child = command.spawn().unwrap();
        let pid = child.id().unwrap() as libc::pid_t;
        (child, ProcessTree::held_with(pid, holder, counted_kill))
    }

    /// A group with one backgrounded `sleep` whose leader exits at once.
    fn leftover_command(tag: &str) -> (Command, std::path::PathBuf) {
        let file = pid_file(tag);
        let script = format!("sleep 30 >/dev/null 2>&1 & echo $! > '{}'", file.display());
        let mut command = Command::new("/bin/sh");
        command.args(["-c", &script]);
        (command, file)
    }

    fn straggler_of(file: &std::path::Path) -> libc::pid_t {
        let pid = straggler(file);
        let _ = std::fs::remove_file(file);
        pid
    }

    /// Up to 5 s for `pid` to be gone.
    fn gone_within(pid: libc::pid_t) -> bool {
        for _ in 0..500 {
            if !running(pid) {
                return true;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        false
    }

    /// After `terminate`, a leftover still running 200 ms later received no
    /// group kill. Kills it by pid.
    fn survived_unkilled(pid: libc::pid_t) -> bool {
        std::thread::sleep(std::time::Duration::from_millis(200));
        let survived = running(pid);
        unsafe { libc::kill(pid, libc::SIGKILL) };
        survived
    }

    fn holder_pid(tree: &ProcessTree) -> libc::pid_t {
        tree.2.holder.as_ref().expect("a holder").id() as libc::pid_t
    }

    /// A1 C4-c C: once the leader has been reaped, terminate sends nothing to
    /// its old pgid, so a process now holding that group (here a leftover of
    /// the same group, standing in for any reuse) is untouched. (A1 C6s: on a
    /// tree whose holder could not be spawned; with a live holder the old
    /// pgid provably still names this group and is killed, see below.)
    #[tokio::test]
    async fn a_reaped_leader_means_no_kill_on_its_old_pgid() {
        let file = pid_file("reaped");
        let script = format!("sleep 30 >/dev/null 2>&1 & echo $! > '{}'", file.display());
        let mut command = Command::new("/bin/sh");
        command.args(["-c", &script]);
        let (mut child, mut tree) = spawn_counted(&mut command, no_holder);
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

    /// A1 C6s: a normal exit, with the leader already reaped by its owner (as
    /// the supervisor's `child.wait()` does), still kills the leftover group
    /// once, through the live holder, which is then reaped too.
    #[tokio::test]
    async fn a_normal_exit_kills_the_group_through_the_live_holder() {
        let (mut command, file) = leftover_command("holder");
        let (mut child, mut tree) = spawn_counted(&mut command, spawn_holder);
        let holder = holder_pid(&tree);
        assert!(child.wait().await.unwrap().success()); // the leader is reaped
        let pid = straggler_of(&file);
        assert_eq!(tree.group_cleanup(), GroupCleanup::Pending);
        tree.terminate().unwrap();
        let gone = gone_within(pid);
        if !gone {
            unsafe { libc::kill(pid, libc::SIGKILL) };
        }
        assert!(gone, "the group of a normally exited leader survived");
        assert_eq!(tree.group_cleanup(), GroupCleanup::KilledWithHolder);
        assert_eq!(group_kills(), 1);
        assert!(tree.2.holder.is_none(), "the holder was not taken");
        assert!(
            !std::path::Path::new(&format!("/proc/{holder}")).exists(),
            "the holder was not reaped"
        );
    }

    /// A1 C6s: the holder is in the leader's group, runs `/bin/sleep`, and
    /// holds nothing but `/dev/null` on fds 0-2: none of the worker's pipes.
    #[tokio::test]
    async fn the_holder_joins_the_group_and_holds_no_worker_pipe() {
        let mut command = Command::new("/bin/sleep");
        command.arg("30");
        command.stdout(std::process::Stdio::piped());
        let (mut child, mut tree) = spawn(&mut command).await.unwrap();
        let leader = child.id().unwrap() as libc::pid_t;
        let holder = holder_pid(&tree);
        assert_eq!(unsafe { libc::getpgid(holder) }, leader);
        let mut fds: Vec<(String, String)> = std::fs::read_dir(format!("/proc/{holder}/fd"))
            .unwrap()
            .map(|entry| {
                let entry = entry.unwrap();
                let target = std::fs::read_link(entry.path()).unwrap();
                (
                    entry.file_name().to_string_lossy().into_owned(),
                    target.display().to_string(),
                )
            })
            .collect();
        fds.sort();
        let null = |fd: &str| (fd.to_string(), "/dev/null".to_string());
        assert_eq!(fds, vec![null("0"), null("1"), null("2")]);
        let cmdline = std::fs::read(format!("/proc/{holder}/cmdline")).unwrap();
        assert_eq!(cmdline, b"/bin/sleep\x002147483647\x00");
        tree.terminate().unwrap();
        assert_eq!(child.wait().await.unwrap().signal(), Some(libc::SIGKILL));
        assert_eq!(tree.group_cleanup(), GroupCleanup::KilledWithHolder);
    }

    /// A1 C6s: an (injected) holder spawn failure means no group kill: the
    /// fallback branch, which does not depend on any kernel feature.
    #[tokio::test]
    async fn a_failed_holder_spawn_means_no_group_kill() {
        let (mut command, file) = leftover_command("noholder");
        let (mut child, mut tree) = spawn_counted(&mut command, no_holder);
        assert_eq!(tree.group_cleanup(), GroupCleanup::SkippedNoHolder);
        assert!(child.wait().await.unwrap().success());
        let pid = straggler_of(&file);
        tree.terminate().unwrap();
        assert_eq!(tree.group_cleanup(), GroupCleanup::SkippedNoHolder);
        assert_eq!(group_kills(), 0, "a group kill without a holder");
        assert!(
            survived_unkilled(pid),
            "the group was killed without a holder"
        );
    }

    /// A1 C6s: a holder that died on its own (not by our group kill) means no
    /// group kill: the group's number is no longer known to be held.
    #[tokio::test]
    async fn a_dead_holder_means_no_group_kill() {
        let (mut command, file) = leftover_command("deadholder");
        let (mut child, mut tree) = spawn_counted(&mut command, spawn_holder);
        let holder = holder_pid(&tree);
        // Our own holder child, by its pid; left unreaped for `terminate`.
        unsafe { libc::kill(holder, libc::SIGTERM) };
        assert!(child.wait().await.unwrap().success());
        let pid = straggler_of(&file);
        for _ in 0..500 {
            if !running(holder) {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        tree.terminate().unwrap();
        assert_eq!(tree.group_cleanup(), GroupCleanup::SkippedHolderDied);
        assert_eq!(group_kills(), 0, "a group kill after the holder died");
        assert!(
            survived_unkilled(pid),
            "the group was killed after its holder died"
        );
    }

    /// A1 C6s: a holder that cannot join the group (`setpgid` across sessions
    /// fails with `EPERM`) is no holder: no group kill.
    #[tokio::test]
    async fn a_failed_setpgid_means_no_group_kill() {
        let (mut command, file) = leftover_command("setpgid");
        unsafe {
            command.pre_exec(|| {
                if libc::setsid() == -1 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        command.kill_on_drop(true);
        let mut child = command.spawn().unwrap();
        let pid = child.id().unwrap() as libc::pid_t;
        let error = spawn_holder(pid).expect_err("a holder joined another session's group");
        assert_eq!(error.raw_os_error(), Some(libc::EPERM), "{error}");
        let mut tree = ProcessTree::held_with(pid, spawn_holder, counted_kill);
        assert_eq!(tree.group_cleanup(), GroupCleanup::SkippedNoHolder);
        assert!(child.wait().await.unwrap().success());
        let straggler = straggler_of(&file);
        tree.terminate().unwrap();
        assert_eq!(group_kills(), 0, "a group kill without a joined holder");
        assert!(
            survived_unkilled(straggler),
            "the group was killed without a joined holder"
        );
    }

    /// A1 C6s: the one `kill(-pgid)` in this file is `kill_held_group`,
    /// called only from `GroupHold::kill_group` after the holder check
    /// (and injected nowhere else outside the tests).
    #[test]
    fn the_only_group_kill_is_behind_the_holder_check() {
        let source = include_str!("进程树v2.rs");
        let code = source
            .split("#[cfg(all(test, target_os = \"linux\"))]")
            .next()
            .unwrap();
        assert_eq!(code.matches(concat!("libc::", "kill(-")).count(), 1);
        let body = code.split("fn kill_held_group(").nth(1).unwrap();
        let first = body.find(concat!("libc::", "kill(-")).unwrap();
        assert!(first < 120, "the group kill is not kill_held_group's");
        assert_eq!(code.matches("(self.kill_group)(pgid)").count(), 1);
        let gate = code.split("fn kill_group(&mut self").nth(1).unwrap();
        let check = gate.find("holder.try_wait()").unwrap();
        let kill = gate.find("(self.kill_group)(pgid)").unwrap();
        assert!(check < kill, "the group kill precedes the holder check");
        assert_eq!(code.matches("kill_held_group").count(), 2);
    }
}

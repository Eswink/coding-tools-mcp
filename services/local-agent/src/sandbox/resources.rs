//! A1 C4-b (SPEC-A1 v5.3 §4.2): per-worker resource limits for sandboxed
//! children. Preferred: a delegated cgroup v2 (`systemd-run --user --scope
//! -p Delegate=yes`) with `holder/` and one `w-<worker_id>/` per worker, which
//! the child joins in `pre_exec` before any other restriction. Fallback (no
//! user systemd/D-Bus, controllers not delegated, or a refused migration):
//! `RLIMIT_AS`/`RLIMIT_NPROC`/`RLIMIT_CPU` in `pre_exec` plus pgid termination.
//! This is containment of ordinary workloads, not an authorization source.
use std::{
    collections::HashMap,
    ffi::CString,
    fs, io,
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd, RawFd},
        unix::{ffi::OsStrExt, process::CommandExt},
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex, OnceLock},
    time::{Duration, Instant},
};

/// `memory.max`, and `RLIMIT_AS` in the fallback.
pub const MEMORY_MAX_BYTES: u64 = 4 << 30;
/// `pids.max`; the fallback allows this many tasks above the user's current count.
pub const PIDS_MAX: u64 = 256;
/// `RLIMIT_CPU` (seconds) in the fallback. SPEC-A1 v5.3 names the limit without
/// a value; `cpu.max` is left at the kernel default for the same reason.
pub const CPU_SECONDS: u64 = 3600;

const SYSTEMD_RUN: &str = "/usr/bin/systemd-run";
const CGROUP_ROOT: &str = "/sys/fs/cgroup";

/// How a worker child's resources are limited (the environment report).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceReport {
    /// `"cgroup_v2"` or `"rlimit_fallback"`.
    pub resource_limit: &'static str,
    /// Why the cgroup was not used (`"EACCES"`, `"NO_USER_SYSTEMD"`, ...).
    pub cgroup_error: Option<String>,
    /// Controllers missing from an otherwise used cgroup; their rlimit applies.
    pub cgroup_partial: Vec<&'static str>,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Rlimits {
    address_space: bool,
    tasks: bool,
    cpu: bool,
}

const ALL_RLIMITS: Rlimits = Rlimits {
    address_space: true,
    tasks: true,
    cpu: true,
};

/// Host-side, per-worker state shared by every sandbox for that worker.
pub(crate) struct WorkerResources {
    cgroup: Option<PathBuf>,
    rlimits: Rlimits,
    report: ResourceReport,
}

/// Per-child, prepared in the parent; `apply` only issues syscalls.
pub(crate) struct PreparedResources {
    procs: Option<OwnedFd>,
    rlimits: Rlimits,
    nproc: u64,
}

fn errno_name(error: &io::Error) -> String {
    match error.raw_os_error() {
        Some(libc::EACCES) => "EACCES".into(),
        Some(libc::EPERM) => "EPERM".into(),
        Some(libc::EBUSY) => "EBUSY".into(),
        Some(libc::ENOENT) => "ENOENT".into(),
        Some(libc::ENOSPC) => "ENOSPC".into(),
        Some(libc::EINVAL) => "EINVAL".into(),
        Some(libc::EROFS) => "EROFS".into(),
        Some(libc::EOPNOTSUPP) => "EOPNOTSUPP".into(),
        Some(code) => format!("E{code}"),
        None => "EIO".into(),
    }
}

fn valid_worker_id(id: &str) -> bool {
    (1..=64).contains(&id.len())
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

fn open_procs(dir: &Path) -> io::Result<OwnedFd> {
    let path = CString::new(dir.join("cgroup.procs").as_os_str().as_bytes())
        .map_err(|_| io::Error::from(io::ErrorKind::InvalidInput))?;
    let fd = unsafe { libc::open(path.as_ptr(), libc::O_WRONLY | libc::O_CLOEXEC) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { OwnedFd::from_raw_fd(fd) })
}

/// Async-signal-safe: writes the calling process's pid, no allocation.
fn write_own_pid(fd: RawFd) -> io::Result<()> {
    let mut buffer = [0u8; 24];
    let mut end = buffer.len();
    end -= 1;
    buffer[end] = b'\n';
    let mut pid = unsafe { libc::getpid() } as u64;
    loop {
        end -= 1;
        buffer[end] = b'0' + (pid % 10) as u8;
        pid /= 10;
        if pid == 0 {
            break;
        }
    }
    let length = buffer.len() - end;
    let written = unsafe { libc::write(fd, buffer[end..].as_ptr().cast(), length) };
    if written == length as isize {
        Ok(())
    } else if written < 0 {
        Err(io::Error::last_os_error())
    } else {
        Err(io::Error::from_raw_os_error(libc::EIO))
    }
}

/// Tasks (threads) the real user already runs: `RLIMIT_NPROC` counts all of
/// them, so a bare 256 could fail every fork on a busy desktop.
fn current_user_tasks() -> u64 {
    let uid = unsafe { libc::getuid() }.to_string();
    let Ok(entries) = fs::read_dir("/proc") else {
        return 0;
    };
    let mut total = 0;
    for entry in entries.flatten() {
        let Ok(status) = fs::read_to_string(entry.path().join("status")) else {
            continue;
        };
        let mut mine = false;
        let mut threads = 0;
        for line in status.lines() {
            if let Some(rest) = line.strip_prefix("Uid:") {
                mine = rest.split_whitespace().next() == Some(uid.as_str());
            } else if let Some(rest) = line.strip_prefix("Threads:") {
                threads = rest.trim().parse().unwrap_or(0);
            }
        }
        if mine {
            total += threads;
        }
    }
    total
}

/// Joins `dir` from a throwaway `/bin/true` exactly as a sandboxed child would
/// (pre_exec, own pid). The spawn error carries the child's errno.
fn probe_migration(dir: &Path) -> io::Result<()> {
    let procs = open_procs(dir)?;
    let fd = procs.as_raw_fd();
    let mut command = Command::new("/bin/true");
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    unsafe {
        command.pre_exec(move || write_own_pid(fd));
    }
    let status = command.spawn()?.wait()?;
    drop(procs);
    if status.success() {
        Ok(())
    } else {
        Err(io::Error::from_raw_os_error(libc::ECHILD))
    }
}

impl WorkerResources {
    fn fallback(error: String) -> Self {
        Self {
            cgroup: None,
            rlimits: ALL_RLIMITS,
            report: ResourceReport {
                resource_limit: "rlimit_fallback",
                cgroup_error: Some(error),
                cgroup_partial: Vec::new(),
            },
        }
    }

    /// `root` is the delegated scope (or why there is none).
    pub(crate) fn prepare_under(root: Result<&Path, &str>, worker_id: &str) -> Self {
        if !valid_worker_id(worker_id) {
            return Self::fallback("INVALID_WORKER_ID".into());
        }
        let root = match root {
            Ok(root) => root,
            Err(error) => return Self::fallback(error.into()),
        };
        let dir = root.join(format!("w-{worker_id}"));
        match fs::create_dir(&dir) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Self::fallback(errno_name(&error)),
        }
        let mut partial = Vec::new();
        let mut rlimits = Rlimits::default();
        let memory = MEMORY_MAX_BYTES.to_string();
        let pids = PIDS_MAX.to_string();
        for (controller, file, value) in [
            ("memory", "memory.max", Some(memory.as_str())),
            ("pids", "pids.max", Some(pids.as_str())),
            ("cpu", "cpu.max", None),
        ] {
            let path = dir.join(file);
            let ok = match value {
                // Interface files exist only for enabled controllers; never create.
                Some(value) => fs::OpenOptions::new()
                    .write(true)
                    .open(&path)
                    .and_then(|mut file| io::Write::write_all(&mut file, value.as_bytes()))
                    .is_ok(),
                None => path.is_file(),
            };
            if !ok {
                partial.push(controller);
                match controller {
                    "memory" => rlimits.address_space = true,
                    "pids" => rlimits.tasks = true,
                    _ => rlimits.cpu = true,
                }
            }
        }
        if let Err(error) = probe_migration(&dir) {
            return Self::fallback(errno_name(&error));
        }
        Self {
            cgroup: Some(dir),
            rlimits,
            report: ResourceReport {
                resource_limit: "cgroup_v2",
                cgroup_error: None,
                cgroup_partial: partial,
            },
        }
    }

    pub(crate) fn report(&self) -> &ResourceReport {
        &self.report
    }

    /// Opened in the parent for each child. A cgroup that can no longer be
    /// opened degrades this child to the full rlimit set, never to no limit.
    pub(crate) fn prepare_child(&self) -> PreparedResources {
        let procs = self.cgroup.as_deref().and_then(|dir| open_procs(dir).ok());
        let rlimits = if self.cgroup.is_some() && procs.is_none() {
            ALL_RLIMITS
        } else {
            self.rlimits
        };
        PreparedResources {
            procs,
            rlimits,
            nproc: current_user_tasks() + PIDS_MAX,
        }
    }
}

impl PreparedResources {
    /// Only called in `pre_exec`, first: ① join `w-<id>` → (then close_range,
    /// Landlock, seccomp in `PreparedSandbox::apply`). A refused migration
    /// (`EACCES`/`EPERM`/`EBUSY`, or any other error) does not abort the exec:
    /// the child applies every rlimit instead.
    pub(crate) fn apply(&self) -> io::Result<()> {
        let mut rlimits = self.rlimits;
        if let Some(procs) = &self.procs {
            if write_own_pid(procs.as_raw_fd()).is_err() {
                rlimits = ALL_RLIMITS;
            }
        }
        for (enabled, resource, value) in [
            (rlimits.address_space, libc::RLIMIT_AS, MEMORY_MAX_BYTES),
            (rlimits.tasks, libc::RLIMIT_NPROC, self.nproc),
            (rlimits.cpu, libc::RLIMIT_CPU, CPU_SECONDS),
        ] {
            if !enabled {
                continue;
            }
            let limit = libc::rlimit {
                rlim_cur: value as libc::rlim_t,
                rlim_max: value as libc::rlim_t,
            };
            if unsafe { libc::setrlimit(resource, &limit) } != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(())
    }
}

/// The delegated scope plus the holder keeping it alive. The holder reads its
/// stdin, so it exits when the host does (the pipe closes) and `--collect`
/// removes the scope.
struct Delegation {
    scope: PathBuf,
    _holder: Mutex<Child>,
}

fn boot_tag() -> String {
    fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .unwrap_or_default()
        .chars()
        .filter(char::is_ascii_hexdigit)
        .take(8)
        .collect()
}

fn write_value(path: &Path, value: &str) -> io::Result<()> {
    fs::OpenOptions::new()
        .write(true)
        .open(path)
        .and_then(|mut file| io::Write::write_all(&mut file, value.as_bytes()))
}

/// SPEC-A1 v5.3 §4.2: `systemd-run --user --scope -p Delegate=yes --collect
/// --unit=ctm-agents-<boot>-<pid>.scope`, then `holder/` (no internal
/// processes) and `+memory +pids +cpu` where available.
fn acquire(systemd_run: &Path) -> Result<Delegation, String> {
    if !Path::new(CGROUP_ROOT).join("cgroup.controllers").is_file() {
        return Err("NO_CGROUP_V2".into());
    }
    if !systemd_run.is_file() {
        return Err("NO_USER_SYSTEMD".into());
    }
    let unit = format!("ctm-agents-{}-{}.scope", boot_tag(), std::process::id());
    let mut holder = Command::new(systemd_run)
        .args([
            "--user",
            "--scope",
            "-p",
            "Delegate=yes",
            "--collect",
            "--quiet",
        ])
        .arg(format!("--unit={unit}"))
        .args(["--", "/bin/sh", "-c", "read -r _ || :"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "NO_USER_SYSTEMD".to_owned())?;
    let pid = holder.id();
    let deadline = Instant::now() + Duration::from_secs(3);
    let suffix = format!("/{unit}");
    let scope = loop {
        if let Ok(Some(_)) = holder.try_wait() {
            return Err("NO_USER_SYSTEMD".into());
        }
        let cgroup = fs::read_to_string(format!("/proc/{pid}/cgroup")).unwrap_or_default();
        if let Some(path) = cgroup
            .lines()
            .find_map(|line| line.strip_prefix("0::"))
            .filter(|path| path.ends_with(&suffix))
        {
            break Path::new(CGROUP_ROOT).join(path.trim_start_matches('/'));
        }
        if Instant::now() > deadline {
            let _ = holder.kill();
            let _ = holder.wait();
            return Err("SCOPE_TIMEOUT".into());
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let fail = |holder: &mut Child, error: io::Error| {
        let _ = holder.kill();
        let _ = holder.wait();
        errno_name(&error)
    };
    let inner = scope.join("holder");
    if let Err(error) = fs::create_dir(&inner)
        .and_then(|()| write_value(&inner.join("cgroup.procs"), &pid.to_string()))
    {
        return Err(fail(&mut holder, error));
    }
    for controller in ["+memory", "+pids", "+cpu"] {
        // A missing controller shows up per worker as `cgroup_partial`.
        let _ = write_value(&scope.join("cgroup.subtree_control"), controller);
    }
    Ok(Delegation {
        scope,
        _holder: Mutex::new(holder),
    })
}

fn delegation() -> Result<&'static Path, &'static str> {
    static DELEGATION: OnceLock<Result<Delegation, String>> = OnceLock::new();
    match DELEGATION.get_or_init(|| acquire(Path::new(SYSTEMD_RUN))) {
        Ok(delegation) => Ok(delegation.scope.as_path()),
        Err(error) => Err(error.as_str()),
    }
}

fn workers() -> &'static Mutex<HashMap<String, Arc<WorkerResources>>> {
    static WORKERS: OnceLock<Mutex<HashMap<String, Arc<WorkerResources>>>> = OnceLock::new();
    WORKERS.get_or_init(Default::default)
}

/// The worker's resources, prepared once per worker (first spawn).
pub(crate) fn for_worker(worker_id: &str) -> Arc<WorkerResources> {
    let mut map = workers().lock().unwrap_or_else(|e| e.into_inner());
    map.entry(worker_id.to_owned())
        .or_insert_with(|| Arc::new(WorkerResources::prepare_under(delegation(), worker_id)))
        .clone()
}

fn kill_dir(dir: &Path) -> io::Result<bool> {
    write_value(&dir.join("cgroup.kill"), "1").map(|()| true)
}

/// Cancel: `1` → `w-<id>/cgroup.kill` (Linux ≥ 5.14), which also reaches
/// descendants that left the process group. `Ok(false)`: the worker has no
/// cgroup (rlimit fallback); the caller's pgid termination is the mechanism.
pub fn kill_worker_cgroup(worker_id: &str) -> io::Result<bool> {
    let resources = workers()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(worker_id)
        .cloned();
    match resources.as_deref().and_then(|r| r.cgroup.as_deref()) {
        Some(dir) => kill_dir(dir),
        None => Ok(false),
    }
}

/// Discard: forget the worker and remove its (empty) cgroup. A cgroup that
/// still has members is left for the scope's `--collect`.
pub fn release_worker_cgroup(worker_id: &str) {
    let resources = workers()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(worker_id);
    if let Some(dir) = resources.as_deref().and_then(|r| r.cgroup.as_deref()) {
        let _ = fs::remove_dir(dir);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A stand-in for a delegated cgroup: the interface files a real `w-<id>`
    /// would get from its enabled controllers.
    fn fake(controllers: &[&str]) -> (tempfile_dir::Dir, PathBuf) {
        let root = tempfile_dir::Dir::new();
        let dir = root.0.join("w-w1");
        fs::create_dir(&dir).unwrap();
        for file in ["cgroup.procs", "cgroup.kill"] {
            fs::write(dir.join(file), b"").unwrap();
        }
        for controller in controllers {
            fs::write(dir.join(format!("{controller}.max")), b"").unwrap();
        }
        (root, dir)
    }

    mod tempfile_dir {
        pub struct Dir(pub std::path::PathBuf);
        impl Dir {
            pub fn new() -> Self {
                use std::sync::atomic::{AtomicU64, Ordering};
                static NEXT: AtomicU64 = AtomicU64::new(0);
                let path = std::env::temp_dir().join(format!(
                    "ctm-cgroup-unit-{}-{}",
                    std::process::id(),
                    NEXT.fetch_add(1, Ordering::Relaxed)
                ));
                std::fs::create_dir(&path).unwrap();
                Self(path)
            }
        }
        impl Drop for Dir {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
    }

    #[test]
    fn a_delegated_cgroup_gets_the_limits_and_the_probe_joins_it() {
        let (root, dir) = fake(&["memory", "pids", "cpu"]);
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(
            resources.report(),
            &ResourceReport {
                resource_limit: "cgroup_v2",
                cgroup_error: None,
                cgroup_partial: vec![],
            }
        );
        assert_eq!(
            fs::read_to_string(dir.join("memory.max")).unwrap(),
            "4294967296"
        );
        assert_eq!(fs::read_to_string(dir.join("pids.max")).unwrap(), "256");
        // The probe wrote its own pid (a positive number) exactly like a child.
        let probe = fs::read_to_string(dir.join("cgroup.procs")).unwrap();
        assert!(probe.trim_end().parse::<u32>().unwrap() > 1, "{probe:?}");
        assert_eq!(resources.rlimits, Rlimits::default());
    }

    #[test]
    fn missing_controllers_are_reported_partial_and_get_their_rlimit() {
        let (root, _dir) = fake(&["pids"]);
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(resources.report().resource_limit, "cgroup_v2");
        assert_eq!(resources.report().cgroup_partial, ["memory", "cpu"]);
        assert_eq!(
            resources.rlimits,
            Rlimits {
                address_space: true,
                tasks: false,
                cpu: true
            }
        );
    }

    #[test]
    fn a_refused_migration_falls_back_to_rlimits_with_its_errno() {
        use std::os::unix::fs::PermissionsExt;
        let (root, dir) = fake(&["memory", "pids", "cpu"]);
        fs::set_permissions(dir.join("cgroup.procs"), fs::Permissions::from_mode(0o444)).unwrap();
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(
            resources.report(),
            &ResourceReport {
                resource_limit: "rlimit_fallback",
                cgroup_error: Some("EACCES".into()),
                cgroup_partial: vec![],
            }
        );
        assert_eq!(resources.rlimits, ALL_RLIMITS);
        assert!(resources.cgroup.is_none());
        // A migration the kernel refuses in the child itself (here a write error).
        let (root, dir) = fake(&["memory", "pids", "cpu"]);
        fs::remove_file(dir.join("cgroup.procs")).unwrap();
        std::os::unix::fs::symlink("/dev/full", dir.join("cgroup.procs")).unwrap();
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(resources.report().resource_limit, "rlimit_fallback");
        assert_eq!(resources.report().cgroup_error.as_deref(), Some("ENOSPC"));
    }

    #[test]
    fn no_user_systemd_or_an_invalid_worker_id_falls_back() {
        let missing = Path::new("/nonexistent/systemd-run");
        let error = acquire(missing).err().unwrap();
        assert!(
            error == "NO_USER_SYSTEMD" || error == "NO_CGROUP_V2",
            "{error}"
        );
        let resources = WorkerResources::prepare_under(Err(&error), "w1");
        assert_eq!(resources.report().resource_limit, "rlimit_fallback");
        assert_eq!(
            resources.report().cgroup_error.as_deref(),
            Some(error.as_str())
        );
        assert_eq!(resources.rlimits, ALL_RLIMITS);
        let (root, _dir) = fake(&[]);
        for id in ["", "../w1", "a/b", &"x".repeat(65)] {
            let resources = WorkerResources::prepare_under(Ok(&root.0), id);
            assert_eq!(
                resources.report().cgroup_error.as_deref(),
                Some("INVALID_WORKER_ID")
            );
        }
        assert_eq!(fs::read_dir(&root.0).unwrap().count(), 1);
    }

    #[test]
    fn cancel_writes_one_to_cgroup_kill() {
        let (_root, dir) = fake(&["memory", "pids", "cpu"]);
        assert!(kill_dir(&dir).unwrap());
        assert_eq!(fs::read_to_string(dir.join("cgroup.kill")).unwrap(), "1");
        assert!(!kill_worker_cgroup("never-prepared").unwrap());
    }
}

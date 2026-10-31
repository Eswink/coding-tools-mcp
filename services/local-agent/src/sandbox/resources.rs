//! A1 C4-b (SPEC-A1 v5.3 §4.2): per-worker resource limits for sandboxed
//! children. Preferred: a delegated cgroup v2 (`systemd-run --user --scope
//! -p Delegate=yes`) with `holder/` and one `w-<worker_id>/` per worker, which
//! the child joins in `pre_exec` before any other restriction. Fallback (no
//! user systemd/D-Bus, controllers not delegated, or a refused migration):
//! `RLIMIT_DATA`/`RLIMIT_CPU` in `pre_exec`; there is no process-count limit
//! outside the cgroup (`procs_limit: "none"`, A1 C4-c D). This is containment
//! of ordinary workloads, not an authorization source.
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
    ptr::NonNull,
    sync::{
        atomic::{AtomicI32, Ordering},
        Arc, Mutex, OnceLock,
    },
    time::{Duration, Instant},
};

/// `memory.max` of the worker cgroup.
pub const MEMORY_MAX_BYTES: u64 = 4 << 30;
/// A1 C4-c E: `RLIMIT_DATA` in the fallback (and for an undelegated memory
/// controller). Not `RLIMIT_AS`: node, JVMs and ASan builds reserve far more
/// address space than they ever touch and would not even start under 4 GiB.
pub const FALLBACK_DATA_BYTES: u64 = 8 << 30;
/// `pids.max`. The only process-count limit: A1 C4-c D dropped `RLIMIT_NPROC`
/// (it counts every process of the real uid, not the worker's).
pub const PIDS_MAX: u64 = 256;
/// `RLIMIT_CPU` (seconds) in the fallback. SPEC-A1 v5.3 names the limit without
/// a value; `cpu.max` is left at the kernel default for the same reason.
pub const CPU_SECONDS: u64 = 3600;

const SYSTEMD_RUN: &str = "/usr/bin/systemd-run";
const CGROUP_ROOT: &str = "/sys/fs/cgroup";
/// A1 C4-c G: a failed delegation is retried after this long, not cached.
const DELEGATION_RETRY: Duration = Duration::from_secs(30);

/// How a worker child's resources are limited (the environment report).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceReport {
    /// `"cgroup_v2"` or `"rlimit_fallback"`.
    pub resource_limit: &'static str,
    /// Why the cgroup was not used (`"EACCES"`, `"NO_USER_SYSTEMD"`, ...).
    pub cgroup_error: Option<String>,
    /// Controllers missing from an otherwise used cgroup; their rlimit applies.
    pub cgroup_partial: Vec<&'static str>,
    /// `"cgroup_pids_max"`, or `"none"` (fallback, or no pids controller).
    pub procs_limit: &'static str,
    /// A1 C6s: how the leader's group is cleaned. `"holder_killpg"`: one
    /// `kill(-pgid)` after the group's holder was confirmed alive. Where this
    /// host cannot run the holder there is no group kill: `"cgroup_kill_on_cancel"`
    /// (leftovers stay in `w-<id>` until the worker's `cgroup.kill`), or
    /// `"skipped_unsafe"` (no cgroup: residual risk, leftovers survive).
    pub group_cleanup: &'static str,
}

/// A1 C6s: `ResourceReport::group_cleanup` for a host that can (`holds`) or
/// cannot run the group holder, with or without a cgroup.
fn group_cleanup(holds: bool, cgroup: bool) -> &'static str {
    match (holds, cgroup) {
        (true, _) => "holder_killpg",
        (false, true) => "cgroup_kill_on_cancel",
        (false, false) => "skipped_unsafe",
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Rlimits {
    data: bool,
    cpu: bool,
}

const ALL_RLIMITS: Rlimits = Rlimits {
    data: true,
    cpu: true,
};

/// A1 C4-c F: one shared (`MAP_SHARED`) word per worker. A child whose
/// migration fails in `pre_exec` stores its errno here (async-signal-safe),
/// so the parent's report says `rlimit_fallback` instead of `cgroup_v2`.
struct MigrationError(NonNull<AtomicI32>);

// The mapping is only ever accessed through the atomic.
unsafe impl Send for MigrationError {}
unsafe impl Sync for MigrationError {}

impl MigrationError {
    fn new() -> Option<Self> {
        let page = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                std::mem::size_of::<AtomicI32>(),
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED | libc::MAP_ANONYMOUS,
                -1,
                0,
            )
        };
        if page == libc::MAP_FAILED {
            return None;
        }
        NonNull::new(page.cast::<AtomicI32>()).map(Self)
    }

    fn get(&self) -> i32 {
        unsafe { self.0.as_ref() }.load(Ordering::SeqCst)
    }

    /// Async-signal-safe; the first error wins.
    fn set(&self, errno: i32) {
        let _ = unsafe { self.0.as_ref() }.compare_exchange(
            0,
            errno.max(1),
            Ordering::SeqCst,
            Ordering::SeqCst,
        );
    }
}

impl Drop for MigrationError {
    fn drop(&mut self) {
        unsafe { libc::munmap(self.0.as_ptr().cast(), std::mem::size_of::<AtomicI32>()) };
    }
}

/// Host-side, per-worker state shared by every sandbox for that worker.
pub(crate) struct WorkerResources {
    cgroup: Option<PathBuf>,
    rlimits: Rlimits,
    report: ResourceReport,
    migration: Option<Arc<MigrationError>>,
}

/// Per-child, prepared in the parent; `apply` only issues syscalls.
pub(crate) struct PreparedResources {
    procs: Option<OwnedFd>,
    rlimits: Rlimits,
    migration: Option<Arc<MigrationError>>,
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
                procs_limit: "none",
                group_cleanup: group_cleanup(crate::process_tree::host_holds_groups(), false),
            },
            migration: None,
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
        let mut procs_limit = "cgroup_pids_max";
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
                    "memory" => rlimits.data = true,
                    // No rlimit substitute (C4-c D): reported, not emulated.
                    "pids" => procs_limit = "none",
                    _ => rlimits.cpu = true,
                }
            }
        }
        if let Err(error) = probe_migration(&dir) {
            return Self::fallback(errno_name(&error));
        }
        let Some(migration) = MigrationError::new() else {
            // Without the shared word a failed child migration would be
            // reported as cgroup_v2 (C4-c F): do not use the cgroup at all.
            return Self::fallback("ENOMEM".into());
        };
        Self {
            cgroup: Some(dir),
            rlimits,
            report: ResourceReport {
                resource_limit: "cgroup_v2",
                cgroup_error: None,
                cgroup_partial: partial,
                procs_limit,
                group_cleanup: group_cleanup(crate::process_tree::host_holds_groups(), true),
            },
            migration: Some(Arc::new(migration)),
        }
    }

    /// A1 C4-c F: once any child of this worker could not join `w-<id>` (and
    /// so runs under the rlimits), the report says so, with that errno.
    pub(crate) fn report(&self) -> ResourceReport {
        match self.migration.as_deref().map(MigrationError::get) {
            Some(errno) if errno != 0 => {
                Self::fallback(errno_name(&io::Error::from_raw_os_error(errno))).report
            }
            _ => self.report.clone(),
        }
    }

    /// Opened in the parent for each child. A cgroup that can no longer be
    /// opened degrades this child to the full rlimit set, never to no limit,
    /// and the report to `rlimit_fallback`.
    pub(crate) fn prepare_child(&self) -> PreparedResources {
        let procs = match self.cgroup.as_deref().map(open_procs) {
            Some(Ok(procs)) => Some(procs),
            Some(Err(error)) => {
                if let Some(migration) = &self.migration {
                    migration.set(error.raw_os_error().unwrap_or(libc::EIO));
                }
                None
            }
            None => None,
        };
        let rlimits = if self.cgroup.is_some() && procs.is_none() {
            ALL_RLIMITS
        } else {
            self.rlimits
        };
        PreparedResources {
            procs,
            rlimits,
            migration: self.migration.clone(),
        }
    }
}

impl PreparedResources {
    /// Only called in `pre_exec`, first: ① join `w-<id>` → (then umask,
    /// fchdir, no_new_privs, Landlock, close_range, seccomp in
    /// `PreparedSandbox::apply`). A refused migration (`EACCES`/`EPERM`/
    /// `EBUSY`, or any other error) does not abort the exec: the child applies
    /// every rlimit instead and records the errno for the report.
    pub(crate) fn apply(&self) -> io::Result<()> {
        let mut rlimits = self.rlimits;
        if let Some(procs) = &self.procs {
            if let Err(error) = write_own_pid(procs.as_raw_fd()) {
                rlimits = ALL_RLIMITS;
                if let Some(migration) = &self.migration {
                    migration.set(error.raw_os_error().unwrap_or(libc::EIO));
                }
            }
        }
        for (enabled, resource, value) in [
            (rlimits.data, libc::RLIMIT_DATA, FALLBACK_DATA_BYTES),
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
    holder: Mutex<Child>,
}

/// Only a delegation that lost a concurrent acquire (C4-c G) is dropped; the
/// one in use lives for the process.
impl Drop for Delegation {
    fn drop(&mut self) {
        let holder = self.holder.get_mut().unwrap_or_else(|e| e.into_inner());
        let _ = holder.kill();
        let _ = holder.wait();
    }
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
        holder: Mutex::new(holder),
    })
}

/// A1 C4-c G: a success is kept for the process; a failure only for
/// `retry_after`, then the next caller tries again. `acquire` runs without
/// the lock held, so a slow `systemd-run` never blocks other callers.
struct Retrying<T: 'static> {
    slot: Mutex<Slot<T>>,
}

enum Slot<T: 'static> {
    Empty,
    Ready(&'static T),
    Failed(Instant, String),
}

impl<T: 'static> Retrying<T> {
    const fn new() -> Self {
        Self {
            slot: Mutex::new(Slot::Empty),
        }
    }

    fn get(
        &self,
        now: Instant,
        retry_after: Duration,
        acquire: impl FnOnce() -> Result<T, String>,
    ) -> Result<&'static T, String> {
        {
            let slot = self.slot.lock().unwrap_or_else(|e| e.into_inner());
            match &*slot {
                Slot::Ready(value) => return Ok(value),
                Slot::Failed(at, error) if now.saturating_duration_since(*at) < retry_after => {
                    return Err(error.clone())
                }
                _ => {}
            }
        }
        let result = acquire();
        let mut slot = self.slot.lock().unwrap_or_else(|e| e.into_inner());
        if let Slot::Ready(value) = &*slot {
            // A concurrent caller won; ours (if any) is dropped.
            return Ok(value);
        }
        match result {
            Ok(value) => {
                let value: &'static T = Box::leak(Box::new(value));
                *slot = Slot::Ready(value);
                Ok(value)
            }
            Err(error) => {
                *slot = Slot::Failed(now, error.clone());
                Err(error)
            }
        }
    }
}

fn delegation() -> Result<&'static Path, String> {
    static DELEGATION: Retrying<Delegation> = Retrying::new();
    DELEGATION
        .get(Instant::now(), DELEGATION_RETRY, || {
            acquire(Path::new(SYSTEMD_RUN))
        })
        .map(|delegation| delegation.scope.as_path())
}

fn workers() -> &'static Mutex<HashMap<String, Arc<WorkerResources>>> {
    static WORKERS: OnceLock<Mutex<HashMap<String, Arc<WorkerResources>>>> = OnceLock::new();
    WORKERS.get_or_init(Default::default)
}

/// The worker's resources, prepared once per worker (first spawn). The
/// delegation (`systemd-run`) and the migration probe run outside the map
/// lock (C4-c G); a concurrent first spawn keeps whichever was stored first.
pub(crate) fn for_worker(worker_id: &str) -> Arc<WorkerResources> {
    if let Some(known) = workers()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(worker_id)
    {
        return known.clone();
    }
    let root = delegation();
    let root = match &root {
        Ok(root) => Ok(*root),
        Err(error) => Err(error.as_str()),
    };
    let prepared = Arc::new(WorkerResources::prepare_under(root, worker_id));
    workers()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .entry(worker_id.to_owned())
        .or_insert(prepared)
        .clone()
}

fn kill_dir(dir: &Path) -> io::Result<bool> {
    write_value(&dir.join("cgroup.kill"), "1").map(|()| true)
}

/// Cancel: `1` → `w-<id>/cgroup.kill` (Linux ≥ 5.14), which also reaches
/// descendants that left the process group. `Ok(false)`: the worker has no
/// cgroup (rlimit fallback); the caller's pidfd-checked group termination is
/// the mechanism.
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
            ResourceReport {
                resource_limit: "cgroup_v2",
                cgroup_error: None,
                cgroup_partial: vec![],
                procs_limit: "cgroup_pids_max",
                group_cleanup: "holder_killpg",
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

    /// A1 C6s: without the group holder there is no group kill;
    /// the report names the cgroup's `cgroup.kill` or the residual risk.
    #[test]
    fn group_cleanup_reports_the_fallback_or_the_residual_risk() {
        assert_eq!(group_cleanup(true, true), "holder_killpg");
        assert_eq!(group_cleanup(true, false), "holder_killpg");
        assert_eq!(group_cleanup(false, true), "cgroup_kill_on_cancel");
        assert_eq!(group_cleanup(false, false), "skipped_unsafe");
    }

    #[test]
    fn missing_controllers_are_reported_partial_and_get_their_rlimit() {
        let (root, _dir) = fake(&["pids"]);
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(resources.report().resource_limit, "cgroup_v2");
        assert_eq!(resources.report().cgroup_partial, ["memory", "cpu"]);
        assert_eq!(resources.report().procs_limit, "cgroup_pids_max");
        assert_eq!(
            resources.rlimits,
            Rlimits {
                data: true,
                cpu: true
            }
        );
        // C4-c D: a missing pids controller gets no rlimit substitute.
        let (root, _dir) = fake(&["memory", "cpu"]);
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(resources.report().cgroup_partial, ["pids"]);
        assert_eq!(resources.report().procs_limit, "none");
        assert_eq!(resources.rlimits, Rlimits::default());
    }

    #[test]
    fn a_refused_migration_falls_back_to_rlimits_with_its_errno() {
        use std::os::unix::fs::PermissionsExt;
        let (root, dir) = fake(&["memory", "pids", "cpu"]);
        fs::set_permissions(dir.join("cgroup.procs"), fs::Permissions::from_mode(0o444)).unwrap();
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(
            resources.report(),
            ResourceReport {
                resource_limit: "rlimit_fallback",
                cgroup_error: Some("EACCES".into()),
                cgroup_partial: vec![],
                procs_limit: "none",
                group_cleanup: "holder_killpg",
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

    /// A1 C4-c F: a cgroup that can no longer be opened for a child degrades
    /// that child to the rlimits, and the report says so, with the errno.
    #[test]
    fn a_child_that_cannot_join_turns_the_report_into_rlimit_with_its_errno() {
        let (root, dir) = fake(&["memory", "pids", "cpu"]);
        let resources = WorkerResources::prepare_under(Ok(&root.0), "w1");
        assert_eq!(resources.report().resource_limit, "cgroup_v2");
        fs::remove_file(dir.join("cgroup.procs")).unwrap();
        let child = resources.prepare_child();
        assert!(child.procs.is_none());
        assert_eq!(child.rlimits, ALL_RLIMITS);
        assert_eq!(
            resources.report(),
            ResourceReport {
                resource_limit: "rlimit_fallback",
                cgroup_error: Some("ENOENT".into()),
                cgroup_partial: vec![],
                procs_limit: "none",
                group_cleanup: "holder_killpg",
            }
        );
    }

    /// A1 C4-c E: under the fallback a child can reserve far more than
    /// 4 GiB of address space (node/JVM/ASan style, `PROT_NONE`), while
    /// writable private memory is still capped by `RLIMIT_DATA`.
    #[test]
    fn the_fallback_allows_large_reservations_but_caps_data() {
        let resources = WorkerResources::prepare_under(Err("NO_USER_SYSTEMD"), "w1");
        let child = resources.prepare_child();
        // Only async-signal-safe calls between fork and _exit.
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            let map = |len: u64, prot| unsafe {
                libc::mmap(
                    std::ptr::null_mut(),
                    len as usize,
                    prot,
                    libc::MAP_PRIVATE | libc::MAP_ANONYMOUS | libc::MAP_NORESERVE,
                    -1,
                    0,
                ) != libc::MAP_FAILED
            };
            let code = if child.apply().is_err() {
                10
            } else if !map(6 << 30, libc::PROT_NONE) {
                11
            } else if map(
                FALLBACK_DATA_BYTES + (1 << 30),
                libc::PROT_READ | libc::PROT_WRITE,
            ) {
                12
            } else {
                0
            };
            unsafe { libc::_exit(code) };
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert!(libc::WIFEXITED(status), "{status}");
        assert_eq!(
            libc::WEXITSTATUS(status),
            0,
            "10 apply, 11 reserve, 12 data cap"
        );
    }

    /// A1 C4-c G: a failed delegation is retried after the cooldown (not
    /// cached for the process), a success is kept, and `acquire` (the
    /// `systemd-run` call) runs with the lock released.
    #[test]
    fn a_failed_delegation_is_retried_after_the_cooldown_outside_the_lock() {
        let cell: Retrying<u32> = Retrying::new();
        let cooldown = Duration::from_secs(30);
        let t0 = Instant::now();
        let calls = std::cell::Cell::new(0);
        let attempt = |result: Result<u32, String>| {
            || {
                calls.set(calls.get() + 1);
                assert!(cell.slot.try_lock().is_ok(), "acquire ran under the lock");
                result
            }
        };
        assert_eq!(
            cell.get(t0, cooldown, attempt(Err("NO_USER_SYSTEMD".into()))),
            Err("NO_USER_SYSTEMD".into())
        );
        assert_eq!(calls.get(), 1);
        // Within the cooldown: the cached error, no new attempt.
        let early = cell.get(t0 + Duration::from_secs(5), cooldown, attempt(Ok(7)));
        assert_eq!(early, Err("NO_USER_SYSTEMD".into()));
        assert_eq!(calls.get(), 1);
        // After it: tried again, and the success is kept.
        assert_eq!(
            cell.get(t0 + cooldown, cooldown, attempt(Ok(7))).copied(),
            Ok(7)
        );
        assert_eq!(calls.get(), 2);
        assert_eq!(
            cell.get(t0 + cooldown * 9, cooldown, attempt(Ok(8)))
                .copied(),
            Ok(7)
        );
        assert_eq!(calls.get(), 2);
    }
}

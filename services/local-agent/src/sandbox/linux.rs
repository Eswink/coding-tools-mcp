use super::{filter, Root, SandboxError, SandboxErrorKind};
use std::{
    ffi::CString,
    fs::File,
    io,
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd, RawFd},
        unix::ffi::OsStrExt,
    },
    path::Path,
};

const EXECUTE: u64 = 1;
const WRITE_FILE: u64 = 1 << 1;
const READ_FILE: u64 = 1 << 2;
const READ_DIR: u64 = 1 << 3;
const TRUNCATE: u64 = 1 << 14;
const HANDLED_FS: u64 = (1 << 15) - 1;
const WORKSPACE_FS: u64 = HANDLED_FS & !((1 << 6) | (1 << 9) | (1 << 11));
const RUNTIME_DIRS: &[&str] = &[
    "/usr/bin",
    "/usr/sbin",
    "/usr/lib",
    "/usr/lib64",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
];

#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}

#[repr(C, packed)]
struct PathBeneath {
    allowed_access: u64,
    parent_fd: i32,
}

fn failure(kind: SandboxErrorKind) -> SandboxError {
    SandboxError { kind }
}

fn open_beneath(parent: RawFd, path: &Path) -> io::Result<File> {
    let value = if path.as_os_str().is_empty() {
        Path::new(".")
    } else {
        path
    };
    let path = CString::new(value.as_os_str().as_bytes())
        .map_err(|_| io::Error::from(io::ErrorKind::InvalidInput))?;
    let how = OpenHow {
        flags: (libc::O_PATH | libc::O_CLOEXEC | libc::O_DIRECTORY) as u64,
        mode: 0,
        // RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS.
        resolve: 0x08 | 0x04 | 0x02,
    };
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            parent,
            path.as_ptr(),
            &how as *const OpenHow,
            std::mem::size_of::<OpenHow>(),
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd as RawFd) })
}

fn open_path(path: &Path) -> io::Result<File> {
    let path = CString::new(path.as_os_str().as_bytes())
        .map_err(|_| io::Error::from(io::ErrorKind::InvalidInput))?;
    let fd = unsafe { libc::open(path.as_ptr(), libc::O_PATH | libc::O_CLOEXEC) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

pub(super) fn pin_root(path: &Path) -> Result<Root, SandboxError> {
    let path = std::fs::canonicalize(path).map_err(|_| failure(SandboxErrorKind::InvalidRoot))?;
    if ["/", "/usr", "/etc", "/dev", "/proc", "/sys", "/run"]
        .iter()
        .any(|denied| path == Path::new(denied))
    {
        return Err(failure(SandboxErrorKind::InvalidRoot));
    }
    let filesystem =
        open_path(Path::new("/")).map_err(|_| failure(SandboxErrorKind::Unavailable))?;
    let file = open_beneath(
        filesystem.as_raw_fd(),
        path.strip_prefix("/")
            .map_err(|_| failure(SandboxErrorKind::InvalidRoot))?,
    )
    .map_err(|_| failure(SandboxErrorKind::InvalidRoot))?;
    Ok(Root { path, file })
}

#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}

#[derive(Clone, Copy, Default)]
#[repr(C)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

fn require_unprivileged() -> Result<(), SandboxError> {
    if unsafe {
        libc::geteuid() == 0
            || libc::geteuid() != libc::getuid()
            || libc::getegid() != libc::getgid()
    } {
        return Err(failure(SandboxErrorKind::PrivilegedHost));
    }
    let header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [CapData::default(); 2];
    if unsafe {
        libc::syscall(
            libc::SYS_capget,
            &header as *const CapHeader,
            data.as_mut_ptr(),
        )
    } != 0
    {
        return Err(failure(SandboxErrorKind::Unavailable));
    }
    if data
        .iter()
        .any(|cap| cap.effective != 0 || cap.permitted != 0)
    {
        return Err(failure(SandboxErrorKind::PrivilegedHost));
    }
    Ok(())
}

fn add_rule(ruleset: RawFd, file: &File, rights: u64) -> io::Result<()> {
    let rule = PathBeneath {
        allowed_access: rights,
        parent_fd: file.as_raw_fd(),
    };
    if unsafe {
        libc::syscall(
            libc::SYS_landlock_add_rule,
            ruleset,
            1,
            &rule as *const PathBeneath,
            0,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

pub(super) fn prepare(
    root: &Root,
    executable: &Path,
    cwd: &Path,
) -> Result<PreparedSandbox, SandboxError> {
    require_unprivileged()?;
    let abi = unsafe {
        libc::syscall(
            libc::SYS_landlock_create_ruleset,
            std::ptr::null::<u8>(),
            0,
            1,
        )
    };
    if abi < 3 {
        return Err(failure(SandboxErrorKind::Unavailable));
    }
    let relative = cwd
        .strip_prefix(&root.path)
        .map_err(|_| failure(SandboxErrorKind::InvalidWorkingDirectory))?;
    let cwd = open_beneath(root.file.as_raw_fd(), relative)
        .map_err(|_| failure(SandboxErrorKind::InvalidWorkingDirectory))?;
    let program =
        open_path(executable).map_err(|_| failure(SandboxErrorKind::InvalidExecutable))?;
    if !program
        .metadata()
        .map_err(|_| failure(SandboxErrorKind::InvalidExecutable))?
        .is_file()
    {
        return Err(failure(SandboxErrorKind::InvalidExecutable));
    }
    let fd = unsafe {
        libc::syscall(
            libc::SYS_landlock_create_ruleset,
            &HANDLED_FS as *const u64,
            std::mem::size_of::<u64>(),
            0,
        )
    };
    if fd < 0 {
        return Err(failure(SandboxErrorKind::Unavailable));
    }
    let ruleset = unsafe { OwnedFd::from_raw_fd(fd as RawFd) };
    let setup = || -> io::Result<()> {
        add_rule(ruleset.as_raw_fd(), &root.file, WORKSPACE_FS)?;
        add_rule(ruleset.as_raw_fd(), &program, EXECUTE | READ_FILE)?;
        for path in RUNTIME_DIRS {
            match open_path(Path::new(path)) {
                Ok(file) => add_rule(ruleset.as_raw_fd(), &file, EXECUTE | READ_FILE | READ_DIR)?,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(error),
            }
        }
        for path in ["/etc/ld.so.cache", "/etc/localtime"] {
            match open_path(Path::new(path)) {
                Ok(file) => add_rule(ruleset.as_raw_fd(), &file, READ_FILE)?,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(error),
            }
        }
        for path in ["/dev/null", "/dev/zero", "/dev/random", "/dev/urandom"] {
            let file = open_path(Path::new(path))?;
            add_rule(
                ruleset.as_raw_fd(),
                &file,
                READ_FILE | WRITE_FILE | TRUNCATE,
            )?;
        }
        Ok(())
    };
    setup().map_err(|_| failure(SandboxErrorKind::Unavailable))?;
    Ok(PreparedSandbox {
        ruleset,
        cwd,
        filter: filter::program(),
    })
}

pub(crate) struct PreparedSandbox {
    ruleset: OwnedFd,
    cwd: File,
    filter: Vec<libc::sock_filter>,
}

impl PreparedSandbox {
    /// Only called in Command::pre_exec. No allocation or synchronization here.
    pub(crate) fn apply(&self) -> io::Result<()> {
        let program = libc::sock_fprog {
            len: self.filter.len() as u16,
            filter: self.filter.as_ptr() as *mut libc::sock_filter,
        };
        let ok = unsafe {
            libc::fchdir(self.cwd.as_raw_fd()) == 0
                && libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0
                && libc::syscall(libc::SYS_landlock_restrict_self, self.ruleset.as_raw_fd(), 0) == 0
                // CLOEXEC keeps Rust's startup-error pipe usable until exec.
                && libc::syscall(libc::SYS_close_range, 3u32, u32::MAX, 4u32) == 0
                && libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog) == 0
        };
        if ok {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }
}

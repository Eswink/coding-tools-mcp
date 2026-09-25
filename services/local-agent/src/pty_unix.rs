use crate::process_tree::ProcessTree;
use crate::pty::{PtyError, PtyErrorKind, PtySize, PtySpec};
use std::{
    ffi::CStr,
    fs::File,
    io::{self, Write},
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd, RawFd},
        unix::process::CommandExt,
    },
    process::{Child, Command, Stdio},
};

pub(crate) struct Spawned {
    pub(crate) reader: File,
    pub(crate) process: PlatformPty,
}

pub(crate) struct PlatformPty {
    child: Child,
    tree: ProcessTree,
    writer: Option<File>,
    resize_fd: RawFd,
}

pub(crate) fn spawn(spec: &PtySpec, cwd: &std::path::Path) -> Result<Spawned, PtyError> {
    let master = open_master().map_err(|_| spawn_error())?;
    let slave = open_slave(master.as_raw_fd()).map_err(|_| spawn_error())?;
    set_raw(slave.as_raw_fd()).map_err(|_| spawn_error())?;
    set_size(master.as_raw_fd(), spec.size()).map_err(|_| spawn_error())?;
    let reader = duplicate_file(master.as_raw_fd()).map_err(|_| spawn_error())?;
    let writer = duplicate_file(master.as_raw_fd()).map_err(|_| spawn_error())?;
    let resize_fd = writer.as_raw_fd();

    let mut command = Command::new(&spec.argv()[0]);
    command
        .args(&spec.argv()[1..])
        .current_dir(cwd)
        .env_clear()
        .envs(spec.env())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let slave_fd = slave.as_raw_fd();
    unsafe {
        command.pre_exec(move || {
            if libc::setsid() == -1 {
                return Err(io::Error::last_os_error());
            }
            if libc::ioctl(slave_fd, libc::TIOCSCTTY as _, 0) == -1 {
                return Err(io::Error::last_os_error());
            }
            for target in [libc::STDIN_FILENO, libc::STDOUT_FILENO, libc::STDERR_FILENO] {
                if libc::dup2(slave_fd, target) == -1 {
                    return Err(io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }
    let child = command.spawn().map_err(|_| spawn_error())?;
    let pid = child.id();
    drop(slave);
    let tree = ProcessTree::from_pgid(pid as libc::pid_t);
    Ok(Spawned {
        reader,
        process: PlatformPty {
            child,
            tree,
            writer: Some(writer),
            resize_fd,
        },
    })
}

impl PlatformPty {
    pub(crate) fn write(&mut self, bytes: &[u8]) -> io::Result<()> {
        self.writer
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "PTY input closed"))?
            .write_all(bytes)
    }

    pub(crate) fn resize(&mut self, size: PtySize) -> io::Result<()> {
        set_size(self.resize_fd, size)
    }

    pub(crate) fn try_wait(&mut self) -> io::Result<Option<i32>> {
        self.child
            .try_wait()
            .map(|status| status.map(|value| value.code().unwrap_or_default()))
    }

    pub(crate) fn terminate_tree(&mut self) -> io::Result<()> {
        self.tree.terminate()
    }

    pub(crate) fn close_session(&mut self) {
        self.writer.take();
    }
}

fn open_master() -> io::Result<OwnedFd> {
    let raw = unsafe { libc::posix_openpt(libc::O_RDWR | libc::O_NOCTTY | libc::O_CLOEXEC) };
    if raw == -1 {
        return Err(io::Error::last_os_error());
    }
    let master = unsafe { OwnedFd::from_raw_fd(raw) };
    if unsafe { libc::grantpt(master.as_raw_fd()) } == -1
        || unsafe { libc::unlockpt(master.as_raw_fd()) } == -1
    {
        return Err(io::Error::last_os_error());
    }
    Ok(master)
}

fn open_slave(master: RawFd) -> io::Result<OwnedFd> {
    let mut name = vec![0i8; 256];
    let result = unsafe { libc::ptsname_r(master, name.as_mut_ptr(), name.len()) };
    if result != 0 {
        return Err(io::Error::from_raw_os_error(result));
    }
    let path = unsafe { CStr::from_ptr(name.as_ptr()) };
    let raw = unsafe { libc::open(path.as_ptr(), libc::O_RDWR | libc::O_NOCTTY | libc::O_CLOEXEC) };
    if raw == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { OwnedFd::from_raw_fd(raw) })
}

fn set_raw(fd: RawFd) -> io::Result<()> {
    let mut termios = unsafe { std::mem::zeroed::<libc::termios>() };
    if unsafe { libc::tcgetattr(fd, &mut termios) } == -1 {
        return Err(io::Error::last_os_error());
    }
    unsafe { libc::cfmakeraw(&mut termios) };
    if unsafe { libc::tcsetattr(fd, libc::TCSANOW, &termios) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn set_size(fd: RawFd, size: PtySize) -> io::Result<()> {
    let winsize = libc::winsize {
        ws_row: size.rows,
        ws_col: size.columns,
        ws_xpixel: 0,
        ws_ypixel: 0,
    };
    if unsafe { libc::ioctl(fd, libc::TIOCSWINSZ as _, &winsize) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn duplicate_file(fd: RawFd) -> io::Result<File> {
    let duplicate = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 0) };
    if duplicate == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(duplicate) })
}

fn spawn_error() -> PtyError {
    PtyError::new(PtyErrorKind::Spawn, "failed to spawn PTY")
}

//! Explicit document channels. Diagnostic errors never contain paths or document data.
use super::{input, Result, ServiceError};
use std::{
    collections::BTreeMap,
    fs::File,
    io::{IsTerminal, Write},
    path::{Path, PathBuf},
};
use zeroize::Zeroizing;

pub(super) struct Flags {
    pub command: String,
    values: BTreeMap<String, Option<String>>,
}
impl Flags {
    pub fn parse(args: Vec<String>, allowed: &[&str]) -> Result<Self> {
        let mut args = args.into_iter();
        let command = args.next().ok_or(ServiceError::Arguments)?;
        let mut values = BTreeMap::new();
        for_limit(&command)?;
        while let Some(name) = args.next() {
            if !allowed.contains(&name.as_str()) || values.contains_key(&name) {
                return Err(ServiceError::Arguments);
            }
            let value = if name.ends_with("-stdin") || name == "--output-stdout" {
                None
            } else {
                let value = args.next().ok_or(ServiceError::Arguments)?;
                if value.is_empty() || value.len() > 4096 {
                    return Err(ServiceError::Arguments);
                }
                Some(value)
            };
            values.insert(name, value);
        }
        // A pipe is consumed only once; never parse two logical documents from one stream.
        if values.keys().filter(|k| k.ends_with("-stdin")).count() > 1 {
            return Err(ServiceError::Arguments);
        }
        Ok(Self { command, values })
    }
    pub fn value(&self, key: &str) -> Result<&str> {
        self.values
            .get(key)
            .and_then(Option::as_deref)
            .ok_or(ServiceError::Arguments)
    }
    pub fn has(&self, key: &str) -> bool {
        self.values.contains_key(key)
    }
    pub fn path(&self, key: &str) -> Result<PathBuf> {
        let path = PathBuf::from(self.value(key)?);
        if !path.is_absolute() {
            return Err(ServiceError::Arguments);
        }
        Ok(path)
    }
    pub fn document(&self, file: &str, stdin: &str) -> Result<Zeroizing<Vec<u8>>> {
        if self.has(file) == self.has(stdin) {
            return Err(ServiceError::Arguments);
        }
        if self.has(file) {
            input::read_protected(&self.path(file)?)
        } else {
            let stream = std::io::stdin();
            if stream.is_terminal() {
                return Err(ServiceError::Input);
            }
            input::read_bounded(stream.lock())
        }
    }
}
fn for_limit(command: &str) -> Result<()> {
    if command.len() > 32 {
        Err(ServiceError::Arguments)
    } else {
        Ok(())
    }
}
pub(super) enum Output {
    File(File),
    Pipe,
}
impl Output {
    pub fn open(flags: &Flags) -> Result<Self> {
        if flags.has("--output-file") == flags.has("--output-stdout") {
            return Err(ServiceError::Arguments);
        }
        if flags.has("--output-file") {
            Ok(Self::File(create_private(&flags.path("--output-file")?)?))
        } else if std::io::stdout().is_terminal() {
            Err(ServiceError::Input)
        } else {
            Ok(Self::Pipe)
        }
    }
    pub fn write(mut self, bytes: &[u8]) -> Result<()> {
        if bytes.len() > 16_384 {
            return Err(ServiceError::Input);
        }
        match &mut self {
            Self::File(file) => {
                file.write_all(bytes)
                    .map_err(|_| ServiceError::FileProtection)?;
                file.sync_all().map_err(|_| ServiceError::FileProtection)
            }
            Self::Pipe => {
                let mut out = std::io::stdout().lock();
                out.write_all(bytes)
                    .and_then(|_| out.flush())
                    .map_err(|_| ServiceError::Input)
            }
        }
    }
}
#[cfg(unix)]
fn create_private(path: &Path) -> Result<File> {
    use std::{
        ffi::CString,
        os::{
            fd::{AsRawFd, FromRawFd},
            unix::{
                ffi::OsStrExt,
                fs::{MetadataExt, OpenOptionsExt},
            },
        },
    };
    let denied = || ServiceError::FileProtection;
    let parent = path.parent().ok_or_else(denied)?;
    if !path.is_absolute() || parent.canonicalize().map_err(|_| denied())? != parent {
        return Err(denied());
    }
    let directory = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(parent)
        .map_err(|_| denied())?;
    let meta = directory.metadata().map_err(|_| denied())?;
    // SAFETY: geteuid has no pointer arguments.
    if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o022 != 0 {
        return Err(denied());
    }
    let name = path.file_name().ok_or_else(denied)?;
    let name = CString::new(name.as_bytes()).map_err(|_| denied())?;
    // SAFETY: retained directory FD and NUL-terminated single component remain live.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            0o600,
        )
    };
    if fd < 0 {
        return Err(denied());
    }
    // SAFETY: the successful openat returns a new owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
#[cfg(not(unix))]
fn create_private(_path: &Path) -> Result<File> {
    Err(ServiceError::FileAclUnsupported)
}
pub(super) fn serialize(value: &impl serde::Serialize) -> Result<Zeroizing<Vec<u8>>> {
    let mut bytes = Zeroizing::new(serde_json::to_vec(value).map_err(|_| ServiceError::Input)?);
    bytes.push(b'\n');
    Ok(bytes)
}

/// Public pinned origin configuration contains no credential. Unix still enforces ownership;
/// on Windows its integrity is the operator responsibility, as for GatewayConfig.
pub(super) fn read_public_config(path: &Path) -> Result<Zeroizing<Vec<u8>>> {
    #[cfg(unix)]
    {
        input::read_protected(path)
    }
    #[cfg(not(unix))]
    {
        if !path.is_absolute() {
            return Err(ServiceError::Arguments);
        }
        let meta = std::fs::symlink_metadata(path).map_err(|_| ServiceError::Configuration)?;
        if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > 16_384 {
            return Err(ServiceError::Configuration);
        }
        input::read_bounded(File::open(path).map_err(|_| ServiceError::Configuration)?)
    }
}

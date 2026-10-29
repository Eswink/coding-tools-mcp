use crate::AgentError;
use std::{io::Read, path::Path};
use zeroize::Zeroizing;
#[cfg(unix)]
pub(crate) fn read_protected(path: &Path) -> Result<Zeroizing<Vec<u8>>, AgentError> {
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    let denied = || AgentError::Configuration;
    if !path.is_absolute() || path.canonicalize().map_err(|_| denied())? != path {
        return Err(denied());
    }
    let parent = path
        .parent()
        .ok_or_else(denied)?
        .metadata()
        .map_err(|_| denied())?;
    // SAFETY: geteuid takes no pointer or mutable-memory parameters.
    let uid = unsafe { libc::geteuid() };
    if !parent.is_dir() || parent.uid() != uid || parent.mode() & 0o022 != 0 {
        return Err(denied());
    }
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| denied())?;
    let m = file.metadata().map_err(|_| denied())?;
    if !m.is_file() || m.uid() != uid || m.nlink() != 1 || m.mode() & 0o077 != 0 || m.len() > 16_384
    {
        return Err(denied());
    }
    let mut out = Zeroizing::new(Vec::new());
    file.take(16_385)
        .read_to_end(&mut out)
        .map_err(|_| denied())?;
    if out.len() > 16_384 {
        return Err(denied());
    }
    Ok(out)
}

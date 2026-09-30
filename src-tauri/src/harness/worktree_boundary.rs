//! Bounded metadata reads. Never follows a link or treats Git metadata as authority.
use super::worktree::{WorktreeError, WorktreeResult};
use std::{
    fs::{self, File, OpenOptions},
    io::Read,
    path::Path,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub(super) struct FileIdentity(u64, u64);

pub(super) fn failure(code: &'static str) -> WorktreeError {
    WorktreeError::new(code, "Managed worktree safety validation failed.")
}

fn inspect(file: &File) -> WorktreeResult<(FileIdentity, u64)> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        let m = file.metadata().map_err(|_| failure("IO_FAILED"))?;
        Ok((FileIdentity(m.dev(), m.ino()), m.nlink()))
    }
    #[cfg(windows)]
    {
        use std::os::windows::io::AsRawHandle;
        use windows::Win32::{
            Foundation::HANDLE,
            Storage::FileSystem::{GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION},
        };
        let mut info = BY_HANDLE_FILE_INFORMATION::default();
        unsafe { GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info) }
            .map_err(|_| failure("IO_FAILED"))?;
        Ok((
            FileIdentity(
                info.dwVolumeSerialNumber as u64,
                ((info.nFileIndexHigh as u64) << 32) | info.nFileIndexLow as u64,
            ),
            info.nNumberOfLinks as u64,
        ))
    }
}

fn open_checked(path: &Path) -> WorktreeResult<File> {
    let m = fs::symlink_metadata(path).map_err(|_| failure("BOUNDARY_VIOLATION"))?;
    if m.file_type().is_symlink() || (!m.is_dir() && !m.is_file()) {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if m.file_attributes() & 0x0400 != 0 {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // Open the entry itself; directories need backup semantics. Exclude delete sharing.
        options
            .custom_flags(0x0020_0000 | 0x0200_0000)
            .share_mode(0x1 | 0x2);
    }
    let file = options
        .open(path)
        .map_err(|_| failure("BOUNDARY_VIOLATION"))?;
    let actual = file.metadata().map_err(|_| failure("IO_FAILED"))?;
    if actual.is_file() != m.is_file() || actual.is_dir() != m.is_dir() {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    let (_, links) = inspect(&file)?;
    if actual.is_file() && links != 1 {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    Ok(file)
}

pub(super) fn identity(path: &Path) -> WorktreeResult<FileIdentity> {
    inspect(&open_checked(path)?).map(|value| value.0)
}

pub(super) fn read_file(path: &Path, limit: u64) -> WorktreeResult<Vec<u8>> {
    let file = open_checked(path)?;
    let before = inspect(&file)?.0;
    let m = file.metadata().map_err(|_| failure("IO_FAILED"))?;
    if !m.is_file() {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    if m.len() > limit {
        return Err(failure("OUTPUT_LIMIT"));
    }
    let mut data = Vec::new();
    file.take(limit + 1)
        .read_to_end(&mut data)
        .map_err(|_| failure("IO_FAILED"))?;
    if data.len() as u64 > limit {
        return Err(failure("OUTPUT_LIMIT"));
    }
    if identity(path)? != before {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    Ok(data)
}

pub(super) fn validate_tree(root: &Path, max_entries: usize, max_bytes: u64) -> WorktreeResult<()> {
    let before = identity(root)?;
    let mut pending = vec![root.to_path_buf()];
    let mut entries = 0usize;
    let mut bytes = 0u64;
    while let Some(path) = pending.pop() {
        let file = open_checked(&path)?;
        let m = file.metadata().map_err(|_| failure("IO_FAILED"))?;
        entries += 1;
        bytes = bytes
            .checked_add(if m.is_file() { m.len() } else { 0 })
            .ok_or_else(|| failure("OUTPUT_LIMIT"))?;
        if entries > max_entries || bytes > max_bytes {
            return Err(failure("OUTPUT_LIMIT"));
        }
        if m.is_dir() {
            for entry in fs::read_dir(&path).map_err(|_| failure("IO_FAILED"))? {
                pending.push(entry.map_err(|_| failure("IO_FAILED"))?.path());
                if pending.len() + entries > max_entries {
                    return Err(failure("OUTPUT_LIMIT"));
                }
            }
        }
    }
    if identity(root)? != before {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    Ok(())
}

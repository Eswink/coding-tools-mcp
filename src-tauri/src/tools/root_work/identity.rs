//! Pinned native directory identity; a path replacement is never adopted silently.
use super::RootWorkError;
use std::{
    fs::{File, OpenOptions},
    path::Path,
};
pub(super) struct RootIdentity {
    file: File,
    pub key: (u64, u64),
    pub ancestors: Vec<(u64, u64)>,
}
impl RootIdentity {
    pub fn open(root: &Path) -> Result<Self, RootWorkError> {
        let file = open_directory(root)?;
        let key = file_identity(&file)?;
        if key.1 == 0 {
            return Err(RootWorkError);
        }
        let ancestors = root
            .ancestors()
            .take(129)
            .map(|path| file_identity(&open_directory(path)?))
            .collect::<Result<Vec<_>, RootWorkError>>()?;
        if ancestors.len() > 128 {
            return Err(RootWorkError);
        }
        Ok(Self {
            file,
            key,
            ancestors,
        })
    }
    pub fn verify(&self, root: &Path) -> Result<(), RootWorkError> {
        let ancestors = root
            .ancestors()
            .take(129)
            .map(|path| file_identity(&open_directory(path)?))
            .collect::<Result<Vec<_>, RootWorkError>>()?;
        if ancestors != self.ancestors
            || file_identity(&self.file)? != self.key
            || file_identity(&open_directory(root)?)? != self.key
        {
            return Err(RootWorkError);
        }
        Ok(())
    }
}
fn open_directory(root: &Path) -> Result<File, RootWorkError> {
    if root.canonicalize().map_err(|_| RootWorkError)? != root {
        return Err(RootWorkError);
    }
    for ancestor in root.ancestors() {
        let meta = std::fs::symlink_metadata(ancestor).map_err(|_| RootWorkError)?;
        if meta.file_type().is_symlink() || !meta.is_dir() {
            return Err(RootWorkError);
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if meta.file_attributes() & 0x400 != 0 {
                return Err(RootWorkError);
            }
        }
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.custom_flags(0x02000000 | 0x00200000);
    }
    options.open(root).map_err(|_| RootWorkError)
}
#[cfg(unix)]
fn file_identity(file: &File) -> Result<(u64, u64), RootWorkError> {
    use std::os::unix::fs::MetadataExt;
    let meta = file.metadata().map_err(|_| RootWorkError)?;
    if !meta.is_dir() {
        return Err(RootWorkError);
    }
    Ok((meta.dev(), meta.ino()))
}
#[cfg(windows)]
fn file_identity(file: &File) -> Result<(u64, u64), RootWorkError> {
    use std::os::windows::io::AsRawHandle;
    use windows::Win32::{
        Foundation::HANDLE,
        Storage::FileSystem::{GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION},
    };
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe { GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info) }
        .map_err(|_| RootWorkError)?;
    if info.dwFileAttributes & 0x400 != 0 || info.dwFileAttributes & 0x10 == 0 {
        return Err(RootWorkError);
    }
    Ok((
        info.dwVolumeSerialNumber as u64,
        ((info.nFileIndexHigh as u64) << 32) | (info.nFileIndexLow as u64),
    ))
}

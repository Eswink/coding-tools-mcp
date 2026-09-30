//! Linux handle-relative, no-follow filesystem access. Other OSes fail closed.
use super::model::*;
use std::{
    collections::BTreeMap,
    fs::File,
    io::{Read, Write},
    path::Path,
};
#[cfg(target_os = "linux")]
use std::{
    ffi::CString,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::fs::MetadataExt,
    },
};

pub struct Dir {
    pub file: File,
}
pub struct Tree {
    pub entries: Vec<Entry>,
    pub data: BTreeMap<String, Vec<u8>>,
}
#[cfg(target_os = "linux")]
impl Dir {
    fn plain_metadata(file: &File) -> Result<()> {
        let metadata = file.metadata()?;
        if metadata.uid() != unsafe { libc::geteuid() }
            || metadata.gid() != unsafe { libc::getegid() }
            || metadata.mode() & 0o7000 != 0
        {
            return Err(SnapshotError::Unsupported);
        }
        // Reject metadata we cannot reproduce; ENOTSUP/denial is not proof of absence.
        let count = unsafe { libc::flistxattr(file.as_raw_fd(), std::ptr::null_mut(), 0) };
        if count != 0 {
            return Err(SnapshotError::Unsupported);
        }
        Ok(())
    }
    pub fn open(path: &Path) -> Result<Self> {
        if !path.is_absolute() {
            return Err(SnapshotError::Boundary);
        }
        let root = CString::new("/").unwrap();
        let fd = unsafe {
            libc::open(
                root.as_ptr(),
                libc::O_DIRECTORY | libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(SnapshotError::Unavailable);
        }
        let mut dir = Self {
            file: unsafe { File::from_raw_fd(fd) },
        };
        for part in path.components() {
            match part {
                std::path::Component::RootDir => {}
                std::path::Component::Normal(s) => {
                    dir = dir.child(s.to_str().ok_or(SnapshotError::Boundary)?)?
                }
                _ => return Err(SnapshotError::Boundary),
            }
        }
        Ok(dir)
    }
    fn open_file(&self, name: &str, flags: i32, mode: u32) -> Result<File> {
        safe_component(name)?;
        let name = CString::new(name).map_err(|_| SnapshotError::Boundary)?;
        let fd = unsafe {
            libc::openat(
                self.file.as_raw_fd(),
                name.as_ptr(),
                flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
                mode,
            )
        };
        if fd < 0 {
            return Err(SnapshotError::Unavailable);
        }
        Ok(unsafe { File::from_raw_fd(fd) })
    }
    pub fn child(&self, name: &str) -> Result<Self> {
        let file = self.open_file(name, libc::O_DIRECTORY | libc::O_RDONLY, 0)?;
        Ok(Self { file })
    }
    pub fn mkdir(&self, name: &str) -> Result<Self> {
        safe_component(name)?;
        let value = CString::new(name).map_err(|_| SnapshotError::Boundary)?;
        if unsafe { libc::mkdirat(self.file.as_raw_fd(), value.as_ptr(), 0o700) } != 0 {
            return Err(SnapshotError::Unavailable);
        }
        self.sync()?;
        self.child(name)
    }
    pub fn names(&self) -> Result<Vec<String>> {
        let mut names = Vec::new();
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", self.file.as_raw_fd()))? {
            names.push(
                entry?
                    .file_name()
                    .into_string()
                    .map_err(|_| SnapshotError::Boundary)?,
            );
            if names.len() > MAX_ENTRIES + MAX_OBJECTS {
                return Err(SnapshotError::Capacity);
            }
        }
        names.sort();
        Ok(names)
    }
    pub fn identity(&self) -> Result<String> {
        let m = self.file.metadata()?;
        Ok(format!("{}:{}", m.dev(), m.ino()))
    }
    pub fn private(&self) -> Result<()> {
        Self::plain_metadata(&self.file)?;
        let m = self.file.metadata()?;
        if m.mode() & 0o077 != 0 || m.uid() != unsafe { libc::geteuid() } {
            return Err(SnapshotError::Boundary);
        }
        Ok(())
    }
    pub fn sync(&self) -> Result<()> {
        self.file.sync_all()?;
        Ok(())
    }
    pub fn read(&self, name: &str, limit: u64) -> Result<(Vec<u8>, u32)> {
        let mut file = self.open_file(name, libc::O_RDONLY, 0)?;
        let m = file.metadata()?;
        if !m.is_file() || m.nlink() != 1 || m.mode() & 0o7000 != 0 || m.len() > limit {
            return Err(SnapshotError::Boundary);
        }
        Self::plain_metadata(&file)?;
        let mut data = Vec::new();
        (&mut file).take(limit + 1).read_to_end(&mut data)?;
        let after = file.metadata()?;
        if data.len() as u64 > limit
            || m.len() != data.len() as u64
            || m.len() != after.len()
            || m.mtime() != after.mtime()
            || m.mtime_nsec() != after.mtime_nsec()
            || m.ctime() != after.ctime()
            || m.ctime_nsec() != after.ctime_nsec()
            || after.nlink() != 1
        {
            return Err(SnapshotError::Changed);
        }
        Ok((data, m.mode() & 0o777))
    }
    pub fn write_new(&self, name: &str, data: &[u8], mode: u32) -> Result<()> {
        let mut file =
            self.open_file(name, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL, 0o600)?;
        Self::plain_metadata(&file)?;
        file.write_all(data)?;
        if unsafe { libc::fchmod(file.as_raw_fd(), mode) } != 0 {
            return Err(SnapshotError::Unavailable);
        }
        file.sync_all()?;
        self.sync()
    }
    pub fn lock(&self) -> Result<File> {
        let file = self.open_file("operation-lock", libc::O_RDWR | libc::O_CREAT, 0o600)?;
        Self::plain_metadata(&file)?;
        let m = file.metadata()?;
        if !m.is_file()
            || m.nlink() != 1
            || m.mode() & 0o077 != 0
            || m.uid() != unsafe { libc::geteuid() }
        {
            return Err(SnapshotError::Boundary);
        }
        fs2::FileExt::try_lock_exclusive(&file).map_err(|_| SnapshotError::Busy)?;
        Ok(file)
    }
    pub fn move_new(&self, name: &str, to: &Dir, destination: &str) -> Result<()> {
        safe_component(name)?;
        safe_component(destination)?;
        let a = CString::new(name).unwrap();
        let b = CString::new(destination).unwrap();
        if unsafe {
            libc::renameat2(
                self.file.as_raw_fd(),
                a.as_ptr(),
                to.file.as_raw_fd(),
                b.as_ptr(),
                libc::RENAME_NOREPLACE,
            )
        } != 0
        {
            return Err(SnapshotError::Changed);
        }
        self.sync()?;
        to.sync()
    }
    pub fn scan(&self, skip_git: bool) -> Result<Tree> {
        let mut tree = Tree {
            entries: Vec::new(),
            data: BTreeMap::new(),
        };
        self.walk("", skip_git, &mut tree)?;
        tree.entries.sort_by(|a, b| a.path.cmp(&b.path));
        validate_entries(&tree.entries)?;
        Ok(tree)
    }
    fn walk(&self, prefix: &str, skip_git: bool, tree: &mut Tree) -> Result<()> {
        for name in self.names()? {
            if skip_git && name == ".git" {
                continue;
            }
            content_component(&name)?;
            let path = if prefix.is_empty() {
                name.clone()
            } else {
                format!("{prefix}/{name}")
            };
            if tree.entries.len() >= MAX_ENTRIES {
                return Err(SnapshotError::Capacity);
            }
            if let Ok(child) = self.child(&name) {
                Self::plain_metadata(&child.file)?;
                let m = child.file.metadata()?;
                if m.mode() & 0o7000 != 0 {
                    return Err(SnapshotError::Boundary);
                }
                tree.entries.push(Entry {
                    path: path.clone(),
                    directory: true,
                    size: 0,
                    hash: String::new(),
                    mode: m.mode() & 0o777,
                    security: None,
                    attributes: None,
                    uid: Some(unsafe { libc::geteuid() }),
                    gid: Some(unsafe { libc::getegid() }),
                });
                child.walk(&path, false, tree)?;
            } else {
                let (data, mode) = self.read(&name, MAX_FILE)?;
                let total: usize = tree.data.values().map(Vec::len).sum();
                if total + data.len() > MAX_TOTAL as usize {
                    return Err(SnapshotError::Capacity);
                }
                tree.entries.push(Entry {
                    path: path.clone(),
                    directory: false,
                    size: data.len() as u64,
                    hash: hash(&data),
                    mode,
                    security: None,
                    attributes: None,
                    uid: Some(unsafe { libc::geteuid() }),
                    gid: Some(unsafe { libc::getegid() }),
                });
                tree.data.insert(path, data);
            }
        }
        Ok(())
    }
    pub fn materialize(&self, entries: &[Entry], data: &BTreeMap<String, Vec<u8>>) -> Result<()> {
        validate_entries(entries)?;
        for entry in entries {
            let parts: Vec<_> = entry.path.split('/').collect();
            let mut parent = self.child_path(&parts[..parts.len() - 1])?;
            let name = parts[parts.len() - 1];
            if entry.directory {
                parent = parent.mkdir(name)?;
                parent.sync()?;
            } else {
                let bytes = data.get(&entry.path).ok_or(SnapshotError::Corrupt)?;
                if bytes.len() as u64 != entry.size || hash(bytes) != entry.hash {
                    return Err(SnapshotError::Corrupt);
                };
                parent.write_new(name, bytes, entry.mode)?;
            }
        }
        self.sync()
    }
    pub fn apply_directory_modes(&self, entries: &[Entry]) -> Result<()> {
        // Apply desired modes only after cross-parent placement, never to originals.
        for entry in entries.iter().rev().filter(|e| e.directory) {
            let parts: Vec<_> = entry.path.split('/').collect();
            let dir = self.child_path(&parts)?;
            if unsafe { libc::fchmod(dir.file.as_raw_fd(), entry.mode) } != 0 {
                return Err(SnapshotError::Unavailable);
            };
            dir.sync()?;
        }
        self.sync()
    }
    fn child_path(&self, parts: &[&str]) -> Result<Self> {
        let mut dir = Self {
            file: self.file.try_clone()?,
        };
        for p in parts {
            dir = dir.child(p)?;
        }
        Ok(dir)
    }
}
#[cfg(not(target_os = "linux"))]
impl Dir {
    pub fn open(_: &Path) -> Result<Self> {
        Err(SnapshotError::Unsupported)
    }
    pub fn child(&self, _: &str) -> Result<Self> {
        Err(SnapshotError::Unsupported)
    }
    pub fn mkdir(&self, _: &str) -> Result<Self> {
        Err(SnapshotError::Unsupported)
    }
    pub fn names(&self) -> Result<Vec<String>> {
        Err(SnapshotError::Unsupported)
    }
    pub fn identity(&self) -> Result<String> {
        Err(SnapshotError::Unsupported)
    }
    pub fn private(&self) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
    pub fn sync(&self) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
    pub fn read(&self, _: &str, _: u64) -> Result<(Vec<u8>, u32)> {
        Err(SnapshotError::Unsupported)
    }
    pub fn write_new(&self, _: &str, _: &[u8], _: u32) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
    pub fn lock(&self) -> Result<File> {
        Err(SnapshotError::Unsupported)
    }
    pub fn move_new(&self, _: &str, _: &Dir, _: &str) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
    pub fn scan(&self, _: bool) -> Result<Tree> {
        Err(SnapshotError::Unsupported)
    }
    pub fn materialize(&self, _: &[Entry], _: &BTreeMap<String, Vec<u8>>) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
    pub fn apply_directory_modes(&self, _: &[Entry]) -> Result<()> {
        Err(SnapshotError::Unsupported)
    }
}

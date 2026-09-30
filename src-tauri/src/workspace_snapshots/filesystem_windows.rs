//! Pinned ancestor HANDLEs deny write/delete opens; no UNC/device paths or reparses.
use super::super::model::*;
use super::{windows_security as security, Dir, Tree};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{Read, Write},
    os::windows::{fs::OpenOptionsExt, io::AsRawHandle},
    path::{Component, Path, PathBuf, Prefix},
    sync::{Arc, Mutex, OnceLock, Weak},
};
use windows::{
    core::PCWSTR,
    Win32::{Foundation::HANDLE, Security::SECURITY_ATTRIBUTES, Storage::FileSystem::*},
};
#[path = "windows_rename.rs"]
mod native_rename;
const READ: u32 = 0x80000000;
const WRITE: u32 = 0x40000000;
const MAX_ALLOWED: u32 = 0x02000000;
const FLAGS: u32 = 0x02000000 | 0x00200000; // BACKUP_SEMANTICS | OPEN_REPARSE_POINT
fn error<T>(_: T) -> SnapshotError {
    SnapshotError::Boundary
}
fn file_info(file: &File, directory: bool) -> Result<BY_HANDLE_FILE_INFORMATION> {
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe { GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info) }
        .map_err(error)?;
    if info.dwFileAttributes & !(0x10 | 0x80 | 0x27) != 0
        || (info.dwFileAttributes & 0x10 != 0) != directory
        || (!directory && info.nNumberOfLinks != 1)
    {
        return Err(SnapshotError::Boundary);
    }
    Ok(info)
}
fn identity(info: &BY_HANDLE_FILE_INFORMATION) -> String {
    format!(
        "{}:{}:{}",
        info.dwVolumeSerialNumber, info.nFileIndexHigh, info.nFileIndexLow
    )
}
fn opened(path: &Path, access: u32, share: u32) -> Result<File> {
    OpenOptions::new()
        .access_mode(access)
        .share_mode(share)
        .custom_flags(FLAGS)
        .open(path)
        .map_err(error)
}
// Reuse our own pinned handles, rather than weakening sharing to reopen write access.
// Weak entries never prolong a lock; each Dir retains every ancestor HANDLE.
fn opened_directory(path: &Path, write: bool) -> Result<Arc<File>> {
    type Cache = BTreeMap<PathBuf, (bool, Weak<File>)>;
    static CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();
    let mut cache = CACHE
        .get_or_init(|| Mutex::new(BTreeMap::new()))
        .lock()
        .map_err(|_| SnapshotError::Busy)?;
    if let Some((w, weak)) = cache.get(path) {
        if let Some(file) = weak.upgrade() {
            if write && !w {
                return Err(SnapshotError::Busy);
            }
            return Ok(file);
        }
    }
    let file = Arc::new(opened(path, if write { READ | WRITE } else { READ }, 1)?);
    file_info(&file, true)?;
    cache.retain(|_, (_, weak)| weak.strong_count() > 0);
    cache.insert(path.to_owned(), (write, Arc::downgrade(&file)));
    Ok(file)
}
fn streams(path: &Path) -> Result<()> {
    let path = security::wide(path.to_str().ok_or(SnapshotError::Boundary)?);
    let mut data = WIN32_FIND_STREAM_DATA::default();
    let handle = match unsafe {
        FindFirstStreamW(
            PCWSTR(path.as_ptr()),
            FindStreamInfoStandard,
            (&mut data as *mut WIN32_FIND_STREAM_DATA).cast(),
            None,
        )
    } {
        Ok(h) => h,
        Err(e) if e.code().0 as u32 == 0x80070026 => return Ok(()),
        Err(_) => return Err(SnapshotError::Unavailable),
    };
    let result = (|| -> Result<()> {
        loop {
            let end = data
                .cStreamName
                .iter()
                .position(|c| *c == 0)
                .ok_or(SnapshotError::Boundary)?;
            if String::from_utf16(&data.cStreamName[..end]).map_err(error)? != "::$DATA" {
                return Err(SnapshotError::Unsupported);
            }
            match unsafe {
                FindNextStreamW(handle, (&mut data as *mut WIN32_FIND_STREAM_DATA).cast())
            } {
                Ok(()) => {}
                Err(e) if e.code().0 as u32 == 0x80070026 => return Ok(()),
                Err(_) => return Err(SnapshotError::Unavailable),
            }
        }
    })();
    unsafe {
        let _ = FindClose(handle);
    }
    result
}
impl Dir {
    pub fn open(path: &Path) -> Result<Self> {
        let mut parts = path.components();
        let drive = match parts.next() {
            Some(Component::Prefix(p)) => match p.kind() {
                Prefix::Disk(d) | Prefix::VerbatimDisk(d) => d,
                _ => return Err(SnapshotError::Boundary),
            },
            _ => return Err(SnapshotError::Boundary),
        };
        if !matches!(parts.next(), Some(Component::RootDir)) {
            return Err(SnapshotError::Boundary);
        }
        let names: Vec<_> = parts
            .map(|p| match p {
                Component::Normal(s) => {
                    s.to_str().map(str::to_owned).ok_or(SnapshotError::Boundary)
                }
                _ => Err(SnapshotError::Boundary),
            })
            .collect::<Result<_>>()?;
        if names.is_empty() {
            return Err(SnapshotError::Boundary);
        }
        let mut path = PathBuf::from(format!("\\\\?\\{}:\\", drive as char));
        let mut parents = Vec::new();
        let root = opened_directory(&path, false)?;
        file_info(&root, true)?;
        parents.push(root);
        for (index, name) in names.iter().enumerate() {
            safe_component(name)?;
            path.push(name);
            let final_entry = index + 1 == names.len();
            let file = opened_directory(&path, final_entry)?;
            file_info(&file, true)?;
            if final_entry {
                return Ok(Self {
                    file,
                    path,
                    parents,
                });
            }
            parents.push(file);
        }
        Err(SnapshotError::Boundary)
    }
    fn parent_handles(&self) -> Result<Vec<Arc<File>>> {
        let mut parents = self.parents.clone();
        parents.push(self.file.clone());
        Ok(parents)
    }
    fn child_access(&self, name: &str, write: bool) -> Result<Self> {
        safe_component(name)?;
        let path = self.path.join(name);
        let file = opened_directory(&path, write)?;
        file_info(&file, true)?;
        Ok(Self {
            file,
            path,
            parents: self.parent_handles()?,
        })
    }
    pub fn child(&self, name: &str) -> Result<Self> {
        self.child_access(name, false)
    }
    pub fn mkdir(&self, name: &str) -> Result<Self> {
        safe_component(name)?;
        let path = security::wide(
            self.path
                .join(name)
                .to_str()
                .ok_or(SnapshotError::Boundary)?,
        );
        let descriptor = security::private_descriptor()?;
        let attributes = SECURITY_ATTRIBUTES {
            nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor.0 .0,
            bInheritHandle: false.into(),
        };
        unsafe { CreateDirectoryW(PCWSTR(path.as_ptr()), Some(&attributes)) }.map_err(error)?;
        self.sync()?;
        self.child_access(name, true)
    }
    fn mkdir_desired(&self, name: &str, desired: &str) -> Result<Self> {
        safe_component(name)?;
        let path = security::wide(self.path.join(name).to_str().ok_or(SnapshotError::Boundary)?);
        let descriptor = security::parse(desired)?;
        let attributes = SECURITY_ATTRIBUTES {
            nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor.0 .0,
            bInheritHandle: false.into(),
        };
        // Desired security is supplied at creation; never rewrite a preimage's ACL.
        unsafe { CreateDirectoryW(PCWSTR(path.as_ptr()), Some(&attributes)) }.map_err(error)?;
        self.sync()?;
        let child = self.child_access(name, true)?;
        if security::read(&child.file)? != desired {
            return Err(SnapshotError::Unsupported);
        }
        Ok(child)
    }
    pub fn names(&self) -> Result<Vec<String>> {
        let mut names = Vec::new();
        for entry in std::fs::read_dir(&self.path)? {
            names.push(entry?.file_name().into_string().map_err(error)?);
            if names.len() > MAX_ENTRIES + MAX_OBJECTS {
                return Err(SnapshotError::Capacity);
            }
        }
        names.sort();
        Ok(names)
    }
    pub fn identity(&self) -> Result<String> {
        Ok(format!(
            "win:{}:{}",
            identity(&file_info(&self.file, true)?),
            hash(security::read(&self.file)?.as_bytes())
        ))
    }
    pub fn private(&self) -> Result<()> {
        security::private(&self.file)
    }
    pub fn sync(&self) -> Result<()> {
        self.file.sync_all().map_err(|_| SnapshotError::Unavailable)
    }
    fn read_full(&self, name: &str, limit: u64) -> Result<(Vec<u8>, u32, String, u32)> {
        safe_component(name)?;
        let path = self.path.join(name);
        let mut file = opened(&path, READ, 1)?;
        let info = file_info(&file, false)?;
        streams(&path)?;
        security::private(&file)?;
        let size = ((info.nFileSizeHigh as u64) << 32) | info.nFileSizeLow as u64;
        if size > limit {
            return Err(SnapshotError::Capacity);
        }
        let permissions = security::read(&file)?;
        let mut data = Vec::new();
        (&mut file).take(limit + 1).read_to_end(&mut data)?;
        let after = file_info(&file, false)?;
        if data.len() as u64 != size
            || identity(&after) != identity(&info)
            || after.ftLastWriteTime != info.ftLastWriteTime
            || security::read(&file)? != permissions
        {
            return Err(SnapshotError::Changed);
        }
        Ok((
            data,
            if info.dwFileAttributes & 1 != 0 {
                0o444
            } else {
                0o644
            },
            permissions,
            info.dwFileAttributes & 0x27,
        ))
    }
    pub fn read(&self, name: &str, limit: u64) -> Result<(Vec<u8>, u32)> {
        let (data, mode, _, _) = self.read_full(name, limit)?;
        Ok((data, mode))
    }
    pub fn write_new(&self, name: &str, data: &[u8], _: u32) -> Result<()> {
        safe_component(name)?;
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .share_mode(1)
            .custom_flags(FLAGS | 0x80000000)
            .open(self.path.join(name))?;
        file_info(&file, false)?;
        security::private(&file)?;
        file.write_all(data)?;
        file.sync_all()?;
        self.sync()
    }
    pub fn lock(&self) -> Result<File> {
        let path = self.path.join("operation-lock");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .share_mode(3)
            .custom_flags(FLAGS)
            .open(path)?;
        file_info(&file, false)?;
        security::private(&file)?;
        fs2::FileExt::try_lock_exclusive(&file).map_err(|_| SnapshotError::Busy)?;
        Ok(file)
    }
    pub fn move_new(&self, name: &str, to: &Dir, destination: &str) -> Result<()> {
        native_rename::move_new(self, name, to, destination)
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
                let info = file_info(&child.file, true)?;
                streams(&child.path)?;
                security::private(&child.file)?;
                tree.entries.push(Entry {
                    path: path.clone(),
                    directory: true,
                    size: 0,
                    hash: String::new(),
                    mode: 0o755,
                    security: Some(security::read(&child.file)?),
                    attributes: Some(info.dwFileAttributes & 0x27),
                });
                child.walk(&path, false, tree)?;
            } else {
                let (data, mode, security, attributes) = self.read_full(&name, MAX_FILE)?;
                if tree.data.values().map(Vec::len).sum::<usize>() + data.len() > MAX_TOTAL as usize
                {
                    return Err(SnapshotError::Capacity);
                }
                tree.entries.push(Entry {
                    path: path.clone(),
                    directory: false,
                    size: data.len() as u64,
                    hash: hash(&data),
                    mode,
                    security: Some(security),
                    attributes: Some(attributes),
                });
                tree.data.insert(path, data);
            }
        }
        Ok(())
    }
    fn child_path(&self, parts: &[&str], write: bool) -> Result<Self> {
        let mut dir = Self {
            file: self.file.clone(),
            path: self.path.clone(),
            parents: self.parents.clone(),
        };
        for p in parts {
            dir = dir.child_access(p, write)?
        }
        Ok(dir)
    }
    pub fn materialize(&self, entries: &[Entry], data: &BTreeMap<String, Vec<u8>>) -> Result<()> {
        validate_entries(entries)?;
        for entry in entries {
            let parts: Vec<_> = entry.path.split('/').collect();
            let parent = self.child_path(&parts[..parts.len() - 1], true)?;
            let name = parts[parts.len() - 1];
            if entry.directory {
                parent.mkdir_desired(name, entry.security.as_deref().ok_or(SnapshotError::Corrupt)?)?;
            } else {
                let bytes = data.get(&entry.path).ok_or(SnapshotError::Corrupt)?;
                if bytes.len() as u64 != entry.size || hash(bytes) != entry.hash {
                    return Err(SnapshotError::Corrupt);
                };
                parent.write_new(name, bytes, entry.mode)?;
            }
        }
        // Verify exact desired ACLs on staging before originals move. Supported principals
        // are a subset of the private staging ACL; no broad access is granted.
        for entry in entries {
            let parts: Vec<_> = entry.path.split('/').collect();
            let parent = self.child_path(&parts[..parts.len() - 1], false)?;
            let file = opened(&parent.path.join(parts[parts.len() - 1]), MAX_ALLOWED, 1)?;
            file_info(&file, entry.directory)?;
            let desired = entry.security.as_deref().ok_or(SnapshotError::Corrupt)?;
            security::apply(&file, desired)?;
            file.sync_all()?;
        }
        self.sync()
    }
    pub fn apply_directory_modes(&self, entries: &[Entry]) -> Result<()> {
        // Unlike Linux, Windows needs DACL and attributes on files as well as dirs.
        for entry in entries {
            let parts: Vec<_> = entry.path.split('/').collect();
            let parent = self.child_path(&parts[..parts.len() - 1], false)?;
            let file = opened(&parent.path.join(parts[parts.len() - 1]), MAX_ALLOWED, 1)?;
            file_info(&file, entry.directory)?;
            security::apply(
                &file,
                entry.security.as_deref().ok_or(SnapshotError::Corrupt)?,
            )?;
            let attributes = entry.attributes.ok_or(SnapshotError::Corrupt)?;
            let info = FILE_BASIC_INFO {
                FileAttributes: if entry.directory {
                    attributes | 0x10
                } else if attributes == 0 {
                    0x80
                } else {
                    attributes
                },
                ..Default::default()
            };
            unsafe {
                SetFileInformationByHandle(
                    HANDLE(file.as_raw_handle()),
                    FileBasicInfo,
                    (&info as *const FILE_BASIC_INFO).cast(),
                    std::mem::size_of::<FILE_BASIC_INFO>() as u32,
                )
            }
            .map_err(error)?;
            file.sync_all()?;
        }
        self.sync()
    }
}

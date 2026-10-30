//! A1 C5 (SPEC-A1 v5.2 §5 steps 2/4, §5.1, §5.1.1): main-workspace file state
//! and the write transaction shared by integrate and rollback. Paths are the
//! diff's `/`-separated repository paths; every parent component must be a real
//! directory inside the main root (never a symlink, junction or file) and no
//! link is ever followed.
use super::journal::sha_hex;
use std::{
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
};

/// Larger main-workspace files are classified `Other` (never integrated over).
const MAX_FILE: u64 = 16 * 1024 * 1024;

/// The state of one path in the main workspace.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Current {
    Absent,
    File {
        sha256: String,
        exec: bool,
    },
    /// Directory, symlink, special file, unreadable, oversized, or a parent
    /// component that is not a real directory (§5.1.1 row 12).
    Other,
}

/// A repository-relative path integrate may write: no empty, `.` or `..`
/// components, no absolute form, backslash, NUL or (Windows) drive/stream colon.
pub(crate) fn safe_path(rel: &str) -> bool {
    !rel.is_empty()
        && rel.len() <= 4096
        && !rel.starts_with('/')
        && !rel.contains(['\\', '\0'])
        && !(cfg!(windows) && rel.contains(':'))
        && rel
            .split('/')
            .all(|c| !c.is_empty() && c != "." && c != "..")
}
pub(crate) fn join(root: &Path, rel: &str) -> PathBuf {
    let mut path = root.to_path_buf();
    path.extend(rel.split('/'));
    path
}

#[cfg(windows)]
fn reparse(meta: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    // FILE_ATTRIBUTE_REPARSE_POINT: junctions and every other reparse point.
    meta.file_attributes() & 0x400 != 0
}
#[cfg(not(windows))]
fn reparse(_meta: &fs::Metadata) -> bool {
    false
}
fn real_dir(meta: &fs::Metadata) -> bool {
    meta.is_dir() && !meta.file_type().is_symlink() && !reparse(meta)
}
fn regular(meta: &fs::Metadata) -> bool {
    meta.is_file() && !meta.file_type().is_symlink() && !reparse(meta)
}
#[cfg(unix)]
fn exec_bit(meta: &fs::Metadata) -> bool {
    use std::os::unix::fs::PermissionsExt;
    meta.permissions().mode() & 0o111 != 0
}
#[cfg(not(unix))]
fn exec_bit(_meta: &fs::Metadata) -> bool {
    // Windows has no executable bit; comparisons ignore it (`same`).
    false
}

/// The parent chain of `rel`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Parents {
    /// Every parent exists as a real directory.
    Ready,
    /// The listed parents (shallow to deep) are missing; those above are real.
    Missing(Vec<String>),
    /// A parent is a symlink, junction, file or unreadable.
    Blocked,
}
pub(crate) fn parents(root: &Path, rel: &str) -> Parents {
    let parts: Vec<&str> = rel.split('/').collect();
    let mut path = root.to_path_buf();
    for depth in 0..parts.len().saturating_sub(1) {
        path.push(parts[depth]);
        match fs::symlink_metadata(&path) {
            Ok(meta) if real_dir(&meta) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let missing = (depth..parts.len() - 1)
                    .map(|end| parts[..=end].join("/"))
                    .collect();
                return Parents::Missing(missing);
            }
            _ => return Parents::Blocked,
        }
    }
    Parents::Ready
}

pub(crate) fn current(root: &Path, rel: &str) -> Current {
    if !safe_path(rel) {
        return Current::Other;
    }
    match parents(root, rel) {
        Parents::Blocked => return Current::Other,
        Parents::Missing(_) => return Current::Absent,
        Parents::Ready => {}
    }
    let path = join(root, rel);
    let meta = match fs::symlink_metadata(&path) {
        Ok(meta) => meta,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Current::Absent,
        Err(_) => return Current::Other,
    };
    if !regular(&meta) || meta.len() > MAX_FILE {
        return Current::Other;
    }
    match fs::read(&path) {
        Ok(bytes) if bytes.len() as u64 <= MAX_FILE => Current::File {
            sha256: sha_hex(&bytes),
            exec: exec_bit(&meta),
        },
        _ => Current::Other,
    }
}

/// `current` equals the wanted image (`None` = absent). Windows ignores the
/// executable bit (§5.1 mode row: `mode_ignored`).
pub(crate) fn same(current: &Current, want: Option<(&str, bool)>) -> bool {
    match (current, want) {
        (Current::Absent, None) => true,
        (Current::File { sha256, exec }, Some((sha, want_exec))) => {
            sha256 == sha && (cfg!(windows) || *exec == want_exec)
        }
        _ => false,
    }
}

/// Writes `bytes` through a sibling temp file and an atomic rename. On unix the
/// existing file's permission bits are kept with only the executable bits
/// changed; a new file starts from the process umask.
pub(crate) fn write_file(root: &Path, rel: &str, bytes: &[u8], exec: bool) -> io::Result<()> {
    let path = join(root, rel);
    let parent = path.parent().ok_or(io::ErrorKind::InvalidInput)?;
    let name = path
        .file_name()
        .ok_or(io::ErrorKind::InvalidInput)?
        .to_string_lossy()
        .into_owned();
    let tmp = parent.join(format!(
        ".{name}.a1-integrate-{}",
        uuid::Uuid::new_v4().simple()
    ));
    let result = (|| {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&tmp)?;
        file.write_all(bytes)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let base = fs::symlink_metadata(&path)
                .ok()
                .filter(regular)
                .map_or(file.metadata()?.permissions().mode(), |m| {
                    m.permissions().mode()
                })
                & 0o7777;
            let mode = if exec {
                base | ((base & 0o444) >> 2)
            } else {
                base & !0o111
            };
            file.set_permissions(fs::Permissions::from_mode(mode))?;
        }
        #[cfg(not(unix))]
        let _ = exec;
        file.sync_all()?;
        drop(file);
        fs::rename(&tmp, &path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    result
}

/// One file of a transaction: `target` is written (or the path removed when
/// `None`); `prior` is what the path held before, used to undo a failed run.
#[derive(Clone, Debug)]
pub(crate) struct Step {
    pub(crate) path: String,
    pub(crate) target: Option<(Vec<u8>, bool)>,
    pub(crate) prior: Option<(Vec<u8>, bool)>,
    /// Parents to create first, shallow to deep (NB-c, journaled beforehand).
    pub(crate) create_dirs: Vec<String>,
    /// Parents to remove afterwards while empty, given shallow to deep.
    pub(crate) remove_dirs: Vec<String>,
}

#[derive(Debug)]
pub(crate) struct Failed {
    pub(crate) path: String,
    /// Every completed step was undone and every created directory removed.
    pub(crate) restored: bool,
}

fn run_step(root: &Path, step: &Step, created: &mut Vec<String>) -> io::Result<()> {
    for dir in &step.create_dirs {
        match fs::create_dir(join(root, dir)) {
            Ok(()) => created.push(dir.clone()),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                let meta = fs::symlink_metadata(join(root, dir))?;
                if !real_dir(&meta) {
                    return Err(io::ErrorKind::AlreadyExists.into());
                }
            }
            Err(error) => return Err(error),
        }
    }
    // Re-proven right before the write: no parent became a link meanwhile.
    if parents(root, &step.path) != Parents::Ready {
        return Err(io::ErrorKind::InvalidInput.into());
    }
    match &step.target {
        Some((bytes, exec)) => write_file(root, &step.path, bytes, *exec),
        None => match fs::remove_file(join(root, &step.path)) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            other => other,
        },
    }
}
fn undo(root: &Path, steps: &[Step], created: &[String]) -> bool {
    let mut ok = true;
    for step in steps.iter().rev() {
        let done = match &step.prior {
            Some((bytes, exec)) => write_file(root, &step.path, bytes, *exec).is_ok(),
            None => match fs::remove_file(join(root, &step.path)) {
                Err(error) => error.kind() == io::ErrorKind::NotFound,
                Ok(()) => true,
            },
        };
        ok &= done;
    }
    for dir in created.iter().rev() {
        ok &= fs::remove_dir(join(root, dir)).is_ok();
    }
    ok
}

/// Applies every step in order. On the first failure the completed steps are
/// undone in reverse (pre-images, mode and existence) and the directories this
/// run created are removed. On success returns the `remove_dirs` that were not
/// empty and therefore kept (NB-c `dirs_kept`).
pub(crate) fn transact(root: &Path, steps: &[Step]) -> Result<Vec<String>, Failed> {
    let mut created = Vec::new();
    for (index, step) in steps.iter().enumerate() {
        #[cfg(test)]
        let injected = hooks::take(index);
        #[cfg(not(test))]
        let injected = false;
        let result = if injected {
            Err(io::ErrorKind::Other.into())
        } else {
            run_step(root, step, &mut created)
        };
        if result.is_err() {
            let restored = undo(root, &steps[..=index], &created);
            return Err(Failed {
                path: step.path.clone(),
                restored,
            });
        }
    }
    Ok(remove_empty_dirs(root, steps))
}
fn remove_empty_dirs(root: &Path, steps: &[Step]) -> Vec<String> {
    let mut dirs: Vec<&String> = steps.iter().flat_map(|s| s.remove_dirs.iter()).collect();
    dirs.sort_by(|a, b| {
        b.matches('/')
            .count()
            .cmp(&a.matches('/').count())
            .then(b.cmp(a))
    });
    dirs.dedup();
    let mut kept = Vec::new();
    for dir in dirs {
        let path = join(root, dir);
        let is_dir = fs::symlink_metadata(&path).is_ok_and(|m| real_dir(&m));
        if is_dir && fs::remove_dir(&path).is_err() {
            kept.push(dir.clone());
        }
    }
    kept.sort();
    kept
}

#[cfg(test)]
pub(crate) mod hooks {
    use std::cell::Cell;
    thread_local! {
        static FAIL_AT: Cell<Option<usize>> = const { Cell::new(None) };
    }
    /// The next transaction fails when it reaches step `index`.
    pub(crate) fn fail_at(index: usize) {
        FAIL_AT.with(|f| f.set(Some(index)));
    }
    pub(crate) fn take(index: usize) -> bool {
        FAIL_AT.with(|f| {
            if f.get() == Some(index) {
                f.set(None);
                true
            } else {
                false
            }
        })
    }
}

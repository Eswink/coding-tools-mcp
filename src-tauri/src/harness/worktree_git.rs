//! Internal lifecycle adapter backed exclusively by a config-free object database.
//! The legacy argument-shaped interface stays private; it never launches a process.
use super::{
    worktree::WorktreeResult,
    worktree_boundary::{failure, identity, read_file, validate_tree},
    worktree_objects::{self as objects, Source},
};
use std::{
    ffi::OsString,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

pub(super) struct GitOutput {
    pub(super) success: bool,
    pub(super) stdout: Vec<u8>,
}

fn write_new(path: &Path, value: &[u8]) -> WorktreeResult<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| failure("IO_FAILED"))?;
    file.write_all(value)
        .and_then(|_| file.sync_all())
        .map_err(|_| failure("IO_FAILED"))
}
fn ensure_directory(root: &Path, path: &Path) -> WorktreeResult<()> {
    if fs::symlink_metadata(path).is_err() {
        fs::create_dir(path).map_err(|_| failure("IO_FAILED"))?;
    }
    objects::checked_path(root, path)
}
fn registration(source: &Source, managed: &Path, id: &str) -> WorktreeResult<(PathBuf, PathBuf)> {
    if id.len() != 32
        || !id
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
    {
        return Err(failure("INVALID_ID"));
    }
    let target = managed.join(id);
    let metadata = source.git.join("worktrees").join(id);
    objects::checked_path(managed, &target)?;
    objects::checked_path(&source.git, &metadata)?;
    validate_tree(&metadata, 64, 8 * 1024 * 1024)?;
    let link = read_file(&target.join(".git"), 8192)?;
    if !matches_git_link(&link, "gitdir: ", &metadata)
        || read_file(&metadata.join("commondir"), 128)? != b"../..\n"
    {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    let gitdir = read_file(&metadata.join("gitdir"), 8192)?;
    if !matches_git_link(&gitdir, "", &target.join(".git")) {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    Ok((target, metadata))
}
fn registered(source: &Source, managed: &Path) -> WorktreeResult<Vec<(String, PathBuf, PathBuf)>> {
    Ok(registered_in(source, &[managed], None)?
        .into_iter()
        .map(|(_, id, target, metadata)| (id, target, metadata))
        .collect())
}
/// One pass over `.git/worktrees`, keeping entries whose back-pointer names a
/// tree directly under one of `roots` (A1 C4 N1: one listing, filtered by parent).
///
/// A1 C2-ad (NB3): with `skipped` set (the legacy scan only), an entry whose own
/// registration cannot be read or verified is skipped and counted instead of
/// failing the whole pass. The managed path (`None`) stays strict.
fn registered_in(
    source: &Source,
    roots: &[&Path],
    mut skipped: Option<&mut usize>,
) -> WorktreeResult<Vec<(usize, String, PathBuf, PathBuf)>> {
    let parent = source.git.join("worktrees");
    if fs::symlink_metadata(&parent).is_err() {
        return Ok(Vec::new());
    }
    objects::checked_path(&source.git, &parent)?;
    let mut result = Vec::new();
    for (count, entry) in fs::read_dir(&parent)
        .map_err(|_| failure("IO_FAILED"))?
        .enumerate()
    {
        if count >= 256 {
            return Err(failure("OUTPUT_LIMIT"));
        }
        let entry = entry.map_err(|_| failure("IO_FAILED"))?;
        let Some(id) = entry.file_name().to_str().map(str::to_owned) else {
            continue;
        };
        if id.len() != 32
            || !id
                .bytes()
                .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
        {
            continue;
        }
        let one = || -> WorktreeResult<Option<(usize, PathBuf, PathBuf)>> {
            objects::checked_path(&source.git, &entry.path())?;
            let pointer = read_file(&entry.path().join("gitdir"), 8192)?;
            let pointer = std::str::from_utf8(&pointer)
                .map_err(|_| failure("PARSE_FAILED"))?
                .trim_end_matches(['\r', '\n']);
            let Some(index) = roots.iter().position(|root| {
                Path::new(pointer) == Path::new(&git_path_arg(&root.join(&id).join(".git")))
            }) else {
                return Ok(None);
            };
            let (target, metadata) = registration(source, roots[index], &id)?;
            Ok(Some((index, target, metadata)))
        };
        match (one(), skipped.as_deref_mut()) {
            (Ok(Some((index, target, metadata))), _) => result.push((index, id, target, metadata)),
            (Ok(None), _) => {}
            (Err(error), Some(count)) => {
                *count += 1;
                eprintln!(
                    "warning: skipped legacy worktree registration {id}: {}",
                    error.code()
                );
            }
            (Err(error), None) => return Err(error),
        }
    }
    Ok(result)
}
/// A1 C4 (N1): the registered detached trees directly under any of `roots`, as
/// `(root index, id, head)`, from a single registry pass. Every root is pinned.
/// A1 C2-ad (NB3): an entry whose registration or HEAD is broken is skipped and
/// counted in the returned warning total; only the pass itself can fail.
/// `(root index, id, head)` entries plus the count of skipped broken entries.
pub(super) type RegisteredUnder = (Vec<(usize, String, String)>, usize);

pub(super) fn list_registered_under(
    authority: &Path,
    roots: &[PathBuf],
) -> WorktreeResult<RegisteredUnder> {
    let source = objects::open_source(authority)?;
    let mut pins = vec![
        (source.root.clone(), identity(&source.root)?),
        (source.git.clone(), identity(&source.git)?),
        (
            source.git.join("objects"),
            identity(&source.git.join("objects"))?,
        ),
    ];
    for root in roots {
        pins.push((root.clone(), identity(root)?));
    }
    let borrowed: Vec<&Path> = roots.iter().map(PathBuf::as_path).collect();
    let mut result = Vec::new();
    let mut skipped = 0usize;
    for (index, id, _, metadata) in registered_in(&source, &borrowed, Some(&mut skipped))? {
        match read_file(&metadata.join("HEAD"), 128).and_then(|raw| objects::oid(&raw)) {
            Ok(head) => result.push((index, id, head.to_string())),
            Err(error) => {
                skipped += 1;
                eprintln!(
                    "warning: skipped legacy worktree registration {id}: {}",
                    error.code()
                );
            }
        }
    }
    for (path, expected) in pins {
        if identity(&path)? != expected {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
    }
    Ok((result, skipped))
}

pub(super) fn run_git(
    cwd: &Path,
    args: &[OsString],
    authority: &Path,
    managed: Option<&Path>,
) -> WorktreeResult<GitOutput> {
    let source = objects::open_source(authority)?;
    let mut pins = vec![
        (source.root.clone(), identity(&source.root)?),
        (source.git.clone(), identity(&source.git)?),
        (
            source.git.join("objects"),
            identity(&source.git.join("objects"))?,
        ),
    ];
    if let Some(root) = managed {
        pins.push((root.to_owned(), identity(root)?));
    }
    let command = args
        .first()
        .and_then(|value| value.to_str())
        .ok_or_else(|| failure("INVALID_ID"))?;
    let mut stdout = Vec::new();
    match command {
        "rev-parse" if args.len() == 2 && args[1] == "--show-toplevel" && cwd == authority => {
            stdout.extend_from_slice(
                source
                    .root
                    .to_str()
                    .ok_or_else(|| failure("PARSE_FAILED"))?
                    .as_bytes(),
            );
            stdout.push(b'\n');
        }
        "worktree" => {
            let managed = managed.ok_or_else(|| failure("BOUNDARY_VIOLATION"))?;
            match args.get(1).and_then(|value| value.to_str()) {
                Some("list") => {
                    for (_, target, metadata) in registered(&source, managed)? {
                        let head = objects::oid(&read_file(&metadata.join("HEAD"), 128)?)?;
                        stdout.extend_from_slice(
                            format!("worktree {}\0HEAD {}\0detached\0\0", target.display(), head)
                                .as_bytes(),
                        );
                        if stdout.len() > 64 * 1024 {
                            return Err(failure("OUTPUT_LIMIT"));
                        }
                    }
                }
                Some("add") if args.len() == 5 && args[2] == "--detach" && args[4] == "HEAD" => {
                    let raw_target = Path::new(&args[3]);
                    let parent = raw_target
                        .parent()
                        .ok_or_else(|| failure("BOUNDARY_VIOLATION"))?
                        .canonicalize()
                        .map_err(|_| failure("BOUNDARY_VIOLATION"))?;
                    if parent != managed {
                        return Err(failure("BOUNDARY_VIOLATION"));
                    }
                    let id = raw_target
                        .file_name()
                        .and_then(|value| value.to_str())
                        .ok_or_else(|| failure("INVALID_ID"))?;
                    if id.len() != 32
                        || !id
                            .bytes()
                            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
                    {
                        return Err(failure("INVALID_ID"));
                    }
                    let target = managed.join(id);
                    let parent = source.git.join("worktrees");
                    ensure_directory(&source.git, &parent)?;
                    let metadata = parent.join(id);
                    let head = objects::head(&source)?;
                    objects::tree_entries(&source, head)?;
                    fs::create_dir(&metadata)
                        .and_then(|_| fs::create_dir(&target))
                        .map_err(|_| failure("IO_FAILED"))?;
                    write_new(&metadata.join("HEAD"), format!("{head}\n").as_bytes())?;
                    write_new(
                        &metadata.join("managed-origin-head"),
                        format!("{head}\n").as_bytes(),
                    )?;
                    write_new(&metadata.join("commondir"), b"../..\n")?;
                    write_new(
                        &metadata.join("gitdir"),
                        format!("{}\n", git_metadata_path(&target.join(".git"))).as_bytes(),
                    )?;
                    write_new(
                        &target.join(".git"),
                        format!("gitdir: {}\n", git_metadata_path(&metadata)).as_bytes(),
                    )?;
                    objects::checkout(&source, &target, &metadata, head)?;
                    registration(&source, managed, id)?;
                }
                Some("remove") if args.len() == 3 => {
                    let id = Path::new(&args[2])
                        .file_name()
                        .and_then(|value| value.to_str())
                        .ok_or_else(|| failure("INVALID_ID"))?;
                    let (target, metadata) = registration(&source, managed, id)?;
                    if fs::symlink_metadata(metadata.join("locked")).is_ok() {
                        return Err(failure("LOCKED"));
                    }
                    if fs::symlink_metadata(managed.join(format!("{id}.native-profile-pin")))
                        .is_ok()
                    {
                        read_file(&managed.join(format!("{id}.native-profile-pin")), 256)?;
                        return Err(failure("WORKTREE_PINNED"));
                    }
                    if read_file(&metadata.join("HEAD"), 128)?
                        != read_file(&metadata.join("managed-origin-head"), 128)?
                    {
                        return Err(failure("DIRTY"));
                    }
                    if !objects::status(&source, &target, &metadata)?.is_empty() {
                        return Err(failure("DIRTY"));
                    }
                    validate_tree(&target, objects::MAX_ENTRIES + 2, 64 * 1024 * 1024)?;
                    registration(&source, managed, id)?;
                    fs::remove_dir_all(&target).map_err(|_| failure("IO_FAILED"))?;
                    fs::remove_dir_all(&metadata).map_err(|_| failure("IO_FAILED"))?;
                }
                _ => return Err(failure("GIT_FAILED")),
            }
        }
        "status" => {
            let managed = managed.ok_or_else(|| failure("BOUNDARY_VIOLATION"))?;
            let id = cwd
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(|| failure("INVALID_ID"))?;
            let (target, metadata) = registration(&source, managed, id)?;
            if target != cwd {
                return Err(failure("BOUNDARY_VIOLATION"));
            }
            stdout = objects::status(&source, &target, &metadata)?;
        }
        _ => return Err(failure("GIT_FAILED")),
    }
    for (path, expected) in pins {
        if identity(&path)? != expected {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
    }
    Ok(GitOutput {
        success: true,
        stdout,
    })
}
pub(super) fn git_path_arg(path: &Path) -> OsString {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::{OsStrExt, OsStringExt};

        let units = path.as_os_str().encode_wide().collect::<Vec<_>>();
        const VERBATIM: &[u16] = &[92, 92, 63, 92];
        const VERBATIM_UNC: &[u16] = &[92, 92, 63, 92, 85, 78, 67, 92];
        if units.starts_with(VERBATIM_UNC) {
            let mut normalized = vec![92, 92];
            normalized.extend_from_slice(&units[VERBATIM_UNC.len()..]);
            return OsString::from_wide(&normalized);
        }
        if units.starts_with(VERBATIM) {
            return OsString::from_wide(&units[VERBATIM.len()..]);
        }
    }
    path.as_os_str().to_owned()
}

// Git's linked-worktree reader strips the literal "/.git" suffix, including
// Git for Windows. Native Windows separators are valid argv, but not this format.
pub(super) fn git_metadata_path(path: &Path) -> String {
    let native = git_path_arg(path).to_string_lossy().into_owned();
    #[cfg(windows)]
    return native.replace('\\', "/");
    #[cfg(not(windows))]
    native
}

fn matches_git_link(bytes: &[u8], prefix: &str, path: &Path) -> bool {
    let canonical = format!("{prefix}{}\n", git_metadata_path(path));
    let legacy = format!("{prefix}{}\n", git_path_arg(path).to_string_lossy());
    // Preserve only the exact previous broker serialization of this validated
    // path. Do not canonicalize arbitrary metadata paths or rewrite old records.
    bytes == canonical.as_bytes() || bytes == legacy.as_bytes()
}

/// A1 C2-ad (N2 + NB-e, SPEC-A1 v5.1 §1.7): `head` is reachable from a ref of
/// the source repository (main `HEAD`, any loose ref under `.git/refs`, or a
/// `packed-refs` line; annotated tags are peeled). Legacy trees are detached,
/// so an unreachable HEAD may be the only copy of a commit and must not be
/// removed. Any doubt (unreadable ref, missing object, bound hit) is `false`.
pub(super) fn head_reachable_from_refs(authority: &Path, head: &str) -> WorktreeResult<bool> {
    let source = objects::open_source(authority)?;
    let head = objects::oid(head.as_bytes())?;
    let mut tips = Vec::new();
    if let Ok(main) = objects::head(&source) {
        tips.push(main);
    }
    let refs = source.git.join("refs");
    let mut stack = vec![refs.clone()];
    let mut seen = 0usize;
    while let Some(dir) = stack.pop() {
        if objects::checked_path(&source.git, &dir).is_err() {
            continue;
        }
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            seen += 1;
            if seen > 4096 {
                return Ok(false);
            }
            let path = entry.path();
            let Ok(metadata) = fs::symlink_metadata(&path) else {
                continue;
            };
            if metadata.file_type().is_symlink() {
                continue;
            }
            if metadata.is_dir() {
                stack.push(path);
            } else if let Ok(oid) = read_file(&path, 128).and_then(|raw| objects::oid(&raw)) {
                tips.push(oid);
            }
        }
    }
    let packed = source.git.join("packed-refs");
    if fs::symlink_metadata(&packed).is_ok() && objects::checked_path(&source.git, &packed).is_ok()
    {
        if let Ok(bytes) = read_file(&packed, 1024 * 1024) {
            for line in bytes.split(|byte| *byte == b'\n') {
                let line = line.strip_prefix(b"^").unwrap_or(line);
                if let Some(hash) = line.get(..40) {
                    if let Ok(oid) = objects::oid(hash) {
                        tips.push(oid);
                    }
                }
            }
        }
    }
    for tip in tips {
        let Ok(commit) = source
            .repo
            .find_object(tip, None)
            .and_then(|object| object.peel_to_commit())
        else {
            continue;
        };
        let commit = commit.id();
        if commit == head
            || source
                .repo
                .graph_descendant_of(commit, head)
                .unwrap_or(false)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// A1 C2-ad (N2 crash recovery, v5 §1.7 / §4.1): the tree `root/id` is
/// already gone; drop only its own `.git/worktrees/<id>` registration, and only
/// when that registration's back-pointer names exactly that tree and it is not
/// locked (`LOCKED`, NB-l). Never a global prune. Returns whether a
/// registration was removed.
pub(super) fn prune_missing_registration(
    authority: &Path,
    root: &Path,
    id: &str,
) -> WorktreeResult<bool> {
    let source = objects::open_source(authority)?;
    if id.len() != 32
        || !id
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
    {
        return Err(failure("INVALID_ID"));
    }
    let target = root.join(id);
    if fs::symlink_metadata(&target).is_ok() {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    let metadata = source.git.join("worktrees").join(id);
    if fs::symlink_metadata(&metadata).is_err() {
        return Ok(false);
    }
    objects::checked_path(&source.git, &metadata)?;
    // A1 C2-ad2 (NB-l, SPEC-A1 v5.2 §1.7): a locked registration (`git worktree
    // lock`, e.g. a tree on removable media) is never pruned, even if missing.
    if fs::symlink_metadata(metadata.join("locked")).is_ok() {
        return Err(failure("LOCKED"));
    }
    validate_tree(&metadata, 64, 8 * 1024 * 1024)?;
    let gitdir = read_file(&metadata.join("gitdir"), 8192)?;
    if !matches_git_link(&gitdir, "", &target.join(".git")) {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    fs::remove_dir_all(&metadata).map_err(|_| failure("IO_FAILED"))?;
    Ok(true)
}

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
    let expected = format!("gitdir: {}\n", git_path_arg(&metadata).to_string_lossy());
    if link != expected.as_bytes() || read_file(&metadata.join("commondir"), 128)? != b"../..\n" {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    let gitdir = read_file(&metadata.join("gitdir"), 8192)?;
    let expected = format!("{}\n", git_path_arg(&target.join(".git")).to_string_lossy());
    if gitdir != expected.as_bytes() {
        return Err(failure("BOUNDARY_VIOLATION"));
    }
    Ok((target, metadata))
}
fn registered(source: &Source, managed: &Path) -> WorktreeResult<Vec<(String, PathBuf, PathBuf)>> {
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
        objects::checked_path(&source.git, &entry.path())?;
        let pointer = read_file(&entry.path().join("gitdir"), 8192)?;
        let pointer = std::str::from_utf8(&pointer)
            .map_err(|_| failure("PARSE_FAILED"))?
            .trim_end_matches(['\r', '\n']);
        let expected = git_path_arg(&managed.join(&id).join(".git"));
        if Path::new(pointer) != Path::new(&expected) {
            continue;
        }
        let (target, metadata) = registration(source, managed, &id)?;
        result.push((id, target, metadata));
    }
    Ok(result)
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
                        format!("{}\n", git_path_arg(&target.join(".git")).to_string_lossy())
                            .as_bytes(),
                    )?;
                    write_new(
                        &target.join(".git"),
                        format!("gitdir: {}\n", git_path_arg(&metadata).to_string_lossy())
                            .as_bytes(),
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

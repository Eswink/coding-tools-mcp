//! Config-free, network-free Git object access. No Repository::open or subprocesses.
use super::{
    worktree::WorktreeResult,
    worktree_boundary::{failure, identity, read_file, validate_tree},
};
use git2::{Oid, Repository, StatusOptions, StatusShow, TreeWalkMode, TreeWalkResult};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

pub(super) const MAX_ENTRIES: usize = 4096;
const MAX_BLOB: usize = 16 * 1024 * 1024;
const MAX_TREE_BYTES: usize = 64 * 1024 * 1024;
pub(super) struct Source {
    pub root: PathBuf,
    pub git: PathBuf,
    pub repo: Repository,
}

pub(super) fn open_source(root: &Path) -> WorktreeResult<Source> {
    let git = root.join(".git");
    if !git.is_dir() {
        if root.ancestors().skip(1).any(|parent| {
            parent.join(".git/HEAD").is_file() && parent.join(".git/objects").is_dir()
        }) {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
        return Err(failure("NOT_REPOSITORY"));
    }
    checked_path(root, &git)?;
    if fs::symlink_metadata(git.join("HEAD")).is_err() {
        return Err(failure("NOT_REPOSITORY"));
    }
    checked_path(&git, &git.join("HEAD"))?;
    read_file(&git.join("HEAD"), 4096)?;
    let objects = git.join("objects");
    checked_path(&git, &objects)?;
    for forbidden in [
        git.join("commondir"),
        git.join("gitdir"),
        objects.join("info/alternates"),
        objects.join("info/http-alternates"),
    ] {
        if fs::symlink_metadata(forbidden).is_ok() {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
    }
    validate_tree(&objects, 50_000, 256 * 1024 * 1024)?;
    let odb = git2::Odb::new().map_err(|_| failure("GIT_FAILED"))?;
    odb.add_disk_alternate(objects.to_str().ok_or_else(|| failure("PARSE_FAILED"))?)
        .map_err(|_| failure("GIT_FAILED"))?;
    let repo = Repository::from_odb(odb).map_err(|_| failure("GIT_FAILED"))?;
    repo.set_config(&git2::Config::new().map_err(|_| failure("GIT_FAILED"))?)
        .map_err(|_| failure("GIT_FAILED"))?;
    Ok(Source {
        root: root.to_owned(),
        git,
        repo,
    })
}

pub(super) fn checked_path(root: &Path, path: &Path) -> WorktreeResult<()> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| failure("BOUNDARY_VIOLATION"))?;
    let mut cursor = root.to_path_buf();
    identity(&cursor)?;
    for component in relative.components() {
        let Component::Normal(part) = component else {
            return Err(failure("BOUNDARY_VIOLATION"));
        };
        cursor.push(part);
        identity(&cursor)?;
        if cursor
            .canonicalize()
            .map_err(|_| failure("BOUNDARY_VIOLATION"))?
            != cursor
        {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
    }
    Ok(())
}

pub(super) fn oid(bytes: &[u8]) -> WorktreeResult<Oid> {
    let value = std::str::from_utf8(bytes)
        .map_err(|_| failure("PARSE_FAILED"))?
        .trim_end_matches(['\r', '\n']);
    if value.len() != 40 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(failure("PARSE_FAILED"));
    }
    Oid::from_str(value).map_err(|_| failure("PARSE_FAILED"))
}

pub(super) fn head(source: &Source) -> WorktreeResult<Oid> {
    let mut path = source.git.join("HEAD");
    for _ in 0..8 {
        checked_path(&source.git, &path)?;
        let bytes = read_file(&path, 4096)?;
        let value = std::str::from_utf8(&bytes)
            .map_err(|_| failure("PARSE_FAILED"))?
            .trim_end_matches(['\r', '\n']);
        let Some(reference) = value.strip_prefix("ref: ") else {
            return oid(&bytes);
        };
        if !reference.starts_with("refs/")
            || !git2::Reference::is_valid_name(reference)
            || reference.contains('\\')
        {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
        path = source.git.join(reference);
        if fs::symlink_metadata(&path).is_err() {
            let packed_path = source.git.join("packed-refs");
            checked_path(&source.git, &packed_path)?;
            let packed = read_file(&packed_path, 1024 * 1024)?;
            for line in packed.split(|byte| *byte == b'\n') {
                if let Some((hash, name)) = std::str::from_utf8(line)
                    .ok()
                    .and_then(|line| line.split_once(' '))
                {
                    if name == reference {
                        return oid(hash.as_bytes());
                    }
                }
            }
            return Err(failure("GIT_FAILED"));
        }
    }
    Err(failure("BOUNDARY_VIOLATION"))
}

fn safe_tree_path(value: &str) -> bool {
    !value.is_empty()
        && !value.contains(['\\', ':'])
        && value.split('/').all(|part| {
            let upper = part.split('.').next().unwrap_or("").to_ascii_uppercase();
            let reserved = matches!(upper.as_str(), "CON" | "PRN" | "AUX" | "NUL")
                || (upper.len() == 4
                    && (upper.starts_with("COM") || upper.starts_with("LPT"))
                    && matches!(upper.as_bytes()[3], b'1'..=b'9'));
            !reserved
                && !part.to_ascii_lowercase().starts_with(".git~")
                && !part.is_empty()
                && part != "."
                && part != ".."
                && !part.eq_ignore_ascii_case(".git")
                && !part.ends_with(['.', ' '])
        })
}

pub(super) fn tree_entries(
    source: &Source,
    head: Oid,
) -> WorktreeResult<BTreeMap<Vec<u8>, (Oid, u32)>> {
    let odb = source.repo.odb().map_err(|_| failure("GIT_FAILED"))?;
    if odb.read_header(head).map_err(|_| failure("GIT_FAILED"))?.0 > MAX_BLOB {
        return Err(failure("OUTPUT_LIMIT"));
    }
    let commit = source
        .repo
        .find_commit(head)
        .map_err(|_| failure("GIT_FAILED"))?;
    if odb
        .read_header(commit.tree_id())
        .map_err(|_| failure("GIT_FAILED"))?
        .0
        > 1024 * 1024
    {
        return Err(failure("OUTPUT_LIMIT"));
    }
    let tree = commit.tree().map_err(|_| failure("GIT_FAILED"))?;
    let mut entries = BTreeMap::new();
    let mut count = 0;
    let mut total = 0usize;
    let mut rejected = false;
    let result = tree.walk(TreeWalkMode::PreOrder, |prefix, entry| {
        count += 1;
        let Ok(name) = entry.name() else {
            rejected = true;
            return TreeWalkResult::Abort;
        };
        let name = format!("{prefix}{name}");
        if count > MAX_ENTRIES || !safe_tree_path(&name) {
            rejected = true;
            return TreeWalkResult::Abort;
        }
        if entry.kind() == Some(git2::ObjectType::Tree) {
            if !odb
                .read_header(entry.id())
                .is_ok_and(|(size, _)| size <= 1024 * 1024)
            {
                rejected = true;
                return TreeWalkResult::Abort;
            }
            return TreeWalkResult::Ok;
        }
        if !matches!(entry.filemode(), 0o100644 | 0o100755) {
            rejected = true;
            return TreeWalkResult::Abort;
        }
        let Ok((size, _)) = odb.read_header(entry.id()) else {
            rejected = true;
            return TreeWalkResult::Abort;
        };
        total = total.saturating_add(size);
        if size > MAX_BLOB || total > MAX_TREE_BYTES {
            rejected = true;
            return TreeWalkResult::Abort;
        }
        entries.insert(name.into_bytes(), (entry.id(), entry.filemode() as u32));
        TreeWalkResult::Ok
    });
    if rejected || result.is_err() {
        return Err(failure("OUTPUT_LIMIT"));
    }
    Ok(entries)
}

pub(super) fn configured_index(
    source: &Source,
    target: &Path,
    metadata: &Path,
) -> WorktreeResult<git2::Index> {
    let index_path = metadata.join("index");
    if fs::symlink_metadata(&index_path).is_ok() {
        checked_path(metadata, &index_path)?;
        read_file(&index_path, 8 * 1024 * 1024)?;
    }
    let mut index = git2::Index::open(&index_path).map_err(|_| failure("GIT_FAILED"))?;
    source
        .repo
        .set_workdir(target, false)
        .and_then(|_| source.repo.set_index(&mut index))
        .map_err(|_| failure("GIT_FAILED"))?;
    Ok(index)
}

pub(super) fn checkout(
    source: &Source,
    target: &Path,
    metadata: &Path,
    head: Oid,
) -> WorktreeResult<()> {
    tree_entries(source, head)?;
    let _index = configured_index(source, target, metadata)?;
    let tree = source
        .repo
        .find_commit(head)
        .and_then(|commit| commit.tree())
        .map_err(|_| failure("GIT_FAILED"))?;
    let mut options = git2::build::CheckoutBuilder::new();
    options.safe().disable_filters(true).target_dir(target);
    source
        .repo
        .checkout_tree(tree.as_object(), Some(&mut options))
        .map_err(|_| failure("GIT_FAILED"))
}

pub(super) fn status(source: &Source, target: &Path, metadata: &Path) -> WorktreeResult<Vec<u8>> {
    validate_tree(target, MAX_ENTRIES + 2, MAX_TREE_BYTES as u64)?;
    checked_path(metadata, &metadata.join("HEAD"))?;
    let baseline = tree_entries(source, oid(&read_file(&metadata.join("HEAD"), 128)?)?)?;
    let index = configured_index(source, target, metadata)?;
    let indexed: BTreeMap<_, _> = index
        .iter()
        .map(|entry| (entry.path, (entry.id, entry.mode)))
        .collect();
    let mut output = Vec::new();
    if baseline != indexed {
        output.extend_from_slice(b"M  index\0");
        return Ok(output);
    }
    let mut options = StatusOptions::new();
    options
        .show(StatusShow::Workdir)
        .include_untracked(true)
        .recurse_untracked_dirs(true)
        .include_ignored(true)
        .recurse_ignored_dirs(true)
        .include_unmodified(false)
        .update_index(false);
    let entries = source
        .repo
        .statuses(Some(&mut options))
        .map_err(|_| failure("GIT_FAILED"))?;
    for entry in entries.iter() {
        output.extend_from_slice(b"?? ");
        output.extend_from_slice(entry.path_bytes());
        output.push(0);
        if output.len() > 64 * 1024 {
            return Err(failure("OUTPUT_LIMIT"));
        }
    }
    Ok(output)
}

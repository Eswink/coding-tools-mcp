//! A1 C5 (SPEC-A1 v5.2 §2.2/§5): the worker diff behind `subagent_collect` and
//! `subagent_integrate`, plus the main-root HEAD/branch/fingerprint reads used by
//! the rollback window (§5.4). Config-free git2 only: the source repository is
//! opened from its object database with an empty Config, so no repository or
//! worktree config (core.fsmonitor, core.hooksPath, filter drivers, ...) is read
//! and no subprocess is ever spawned.
use super::super::{
    worktree_boundary::{failure, read_file},
    worktree_objects::{checked_path, head, oid, open_source, Source},
};
use super::{SnapshotTarget, WorktreeManager, WorktreeResult};
use git2::{Delta, DiffOptions, FileMode, Oid};
use sha2::{Digest, Sha256};
use std::path::Path;

const MAX_CHANGES: usize = 4096;
const MAX_FILE: u64 = 16 * 1024 * 1024;
const MAX_POST_TOTAL: u64 = 64 * 1024 * 1024;
/// Patch text handed to the main agent in chunks.
pub(crate) const MAX_PATCH: usize = 8 * 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ChangeKind {
    Added,
    Modified,
    Deleted,
}
impl ChangeKind {
    pub(crate) fn label(self) -> &'static str {
        match self {
            Self::Added => "added",
            Self::Modified => "modified",
            Self::Deleted => "deleted",
        }
    }
}

/// One regular-file change the integrate step may apply. `pre` is the
/// `base_head` blob (absent for added files), `post` the raw worktree bytes
/// (absent for deleted files). Executable bits are booleans.
#[derive(Clone, Debug)]
pub(crate) struct FileChange {
    pub(crate) path: String,
    pub(crate) kind: ChangeKind,
    pub(crate) pre: Option<(Vec<u8>, bool)>,
    pub(crate) post: Option<(Vec<u8>, bool)>,
}

#[derive(Clone, Debug, Default)]
pub(crate) struct WorkerDiff {
    pub(crate) patch: Vec<u8>,
    pub(crate) sha256: String,
    pub(crate) changes: Vec<FileChange>,
    /// Paths kept out by the export policy (reason as in §2.2).
    pub(crate) withheld: Vec<(String, &'static str)>,
    /// Paths integrate refuses as a whole (§5.1: symlink, submodule, mode).
    pub(crate) unsupported: Vec<(String, &'static str)>,
}

fn sha_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn exec(mode: FileMode) -> Option<bool> {
    match mode {
        FileMode::Blob => Some(false),
        FileMode::BlobExecutable => Some(true),
        _ => None,
    }
}

impl WorktreeManager {
    fn main_source(&self) -> WorktreeResult<Source> {
        open_source(&self.repository_root)
    }

    /// The worker's changes against `base_head`: tree-to-workdir with untracked
    /// files, no renames, ignored files excluded by the worktree's own
    /// `.gitignore` files only. `policy` is the shared export policy (§2.2).
    pub(crate) fn worker_diff(
        &self,
        target: &SnapshotTarget,
        base_head: &str,
        policy: impl Fn(&str) -> Option<&'static str>,
    ) -> WorktreeResult<WorkerDiff> {
        target.verify()?;
        let base = oid(base_head.as_bytes())?;
        let source = self.main_source()?;
        let tree = source
            .repo
            .find_commit(base)
            .and_then(|commit| commit.tree())
            .map_err(|_| failure("GIT_FAILED"))?;
        // The source repository is opened from its odb alone, so it has no
        // gitdir; an empty in-memory index keeps libgit2 from looking for one.
        source
            .repo
            .set_workdir(&target.root, false)
            .and_then(|_| source.repo.set_index(&mut git2::Index::new()?))
            .map_err(|_| failure("GIT_FAILED"))?;
        let mut options = DiffOptions::new();
        options
            .include_untracked(true)
            .recurse_untracked_dirs(true)
            .show_untracked_content(true)
            .include_ignored(false)
            .include_typechange(true)
            .show_binary(true)
            .ignore_filemode(cfg!(windows))
            .update_index(false);
        let diff = source
            .repo
            .diff_tree_to_workdir(Some(&tree), Some(&mut options))
            .map_err(|_| failure("GIT_FAILED"))?;
        if diff.deltas().len() > MAX_CHANGES {
            return Err(failure("OUTPUT_LIMIT"));
        }
        let odb = source.repo.odb().map_err(|_| failure("GIT_FAILED"))?;
        let mut out = WorkerDiff::default();
        let mut manifest = Vec::new();
        let mut post_total = 0u64;
        for (index, delta) in diff.deltas().enumerate() {
            let path = delta
                .new_file()
                .path()
                .or_else(|| delta.old_file().path())
                .and_then(Path::to_str)
                .ok_or_else(|| failure("PARSE_FAILED"))?
                .replace('\\', "/");
            let old_mode = delta.old_file().mode();
            let new_mode = delta.new_file().mode();
            let modes = [old_mode, new_mode];
            if modes.contains(&FileMode::Link) {
                out.withheld.push((path.clone(), "symlink"));
                out.unsupported.push((path, "symlink"));
                continue;
            }
            if modes.contains(&FileMode::Commit) || delta.status() == Delta::Typechange {
                out.unsupported.push((path, "submodule"));
                continue;
            }
            if let Some(reason) = policy(&path) {
                out.withheld.push((path, reason));
                continue;
            }
            let kind = match delta.status() {
                Delta::Added | Delta::Untracked => ChangeKind::Added,
                Delta::Modified => ChangeKind::Modified,
                Delta::Deleted => ChangeKind::Deleted,
                _ => {
                    out.unsupported.push((path, "mode"));
                    continue;
                }
            };
            let pre = match kind {
                ChangeKind::Added => None,
                _ => {
                    let exec = exec(old_mode).ok_or_else(|| failure("PARSE_FAILED"))?;
                    let blob = odb
                        .read(delta.old_file().id())
                        .map_err(|_| failure("GIT_FAILED"))?;
                    Some((blob.data().to_vec(), exec))
                }
            };
            let post = match kind {
                ChangeKind::Deleted => None,
                _ => {
                    let Some(mut exec) = exec(new_mode) else {
                        out.unsupported.push((path, "mode"));
                        continue;
                    };
                    if cfg!(windows) {
                        // Windows has no executable bit; keep the base mode.
                        exec = pre.as_ref().is_some_and(|(_, e)| *e);
                    }
                    let file = target.root.join(&path);
                    checked_path(&target.root, &file)?;
                    let bytes = read_file(&file, MAX_FILE)?;
                    post_total += bytes.len() as u64;
                    if post_total > MAX_POST_TOTAL {
                        return Err(failure("OUTPUT_LIMIT"));
                    }
                    Some((bytes, exec))
                }
            };
            if let Some(patch) =
                git2::Patch::from_diff(&diff, index).map_err(|_| failure("GIT_FAILED"))?
            {
                let mut patch = patch;
                let buf = patch.to_buf().map_err(|_| failure("GIT_FAILED"))?;
                out.patch.extend_from_slice(&buf);
                if out.patch.len() > MAX_PATCH {
                    return Err(failure("OUTPUT_LIMIT"));
                }
            }
            // The sha binds the raw post-image bytes too, so a worktree change
            // that a filtered patch would not show still makes the diff stale.
            manifest.extend_from_slice(path.as_bytes());
            manifest.push(0);
            manifest.extend_from_slice(kind.label().as_bytes());
            manifest.push(0);
            if let Some((bytes, exec)) = &post {
                manifest.extend_from_slice(sha_hex(bytes).as_bytes());
                manifest.push(if *exec { b'x' } else { b'-' });
            }
            manifest.push(b'\n');
            out.changes.push(FileChange {
                path,
                kind,
                pre,
                post,
            });
        }
        target.verify()?;
        let mut digest = Sha256::new();
        digest.update(b"ctm-worker-diff-v1\0");
        digest.update((out.patch.len() as u64).to_be_bytes());
        digest.update(&out.patch);
        digest.update(&manifest);
        out.sha256 = format!("{:x}", digest.finalize());
        Ok(out)
    }

    /// Main-root HEAD (40 hex) and current branch (`refs/heads/..`, empty when
    /// detached), read without any Git config (§5.4 condition ④).
    pub(crate) fn main_head_branch(&self) -> WorktreeResult<(String, String)> {
        let source = self.main_source()?;
        let head_oid = head(&source)?;
        let raw = read_file(&source.git.join("HEAD"), 4096)?;
        let value = std::str::from_utf8(&raw)
            .map_err(|_| failure("PARSE_FAILED"))?
            .trim_end_matches(['\r', '\n']);
        let branch = value.strip_prefix("ref: ").unwrap_or("").to_owned();
        Ok((head_oid.to_string(), branch))
    }

    /// A content fingerprint of the main workspace (HEAD + every changed or
    /// untracked path with its blob id). Advisory only (§5 step 2).
    pub(crate) fn main_fingerprint(&self) -> WorktreeResult<String> {
        let source = self.main_source()?;
        let head_oid = head(&source)?;
        let tree = source
            .repo
            .find_commit(head_oid)
            .and_then(|commit| commit.tree())
            .map_err(|_| failure("GIT_FAILED"))?;
        source
            .repo
            .set_workdir(&self.repository_root, false)
            .and_then(|_| source.repo.set_index(&mut git2::Index::new()?))
            .map_err(|_| failure("GIT_FAILED"))?;
        let mut options = DiffOptions::new();
        options
            .include_untracked(true)
            .recurse_untracked_dirs(true)
            .ignore_filemode(cfg!(windows))
            .update_index(false);
        let diff = source
            .repo
            .diff_tree_to_workdir(Some(&tree), Some(&mut options))
            .map_err(|_| failure("GIT_FAILED"))?;
        if diff.deltas().len() > MAX_CHANGES {
            return Err(failure("OUTPUT_LIMIT"));
        }
        let mut digest = Sha256::new();
        digest.update(b"ctm-main-fingerprint-v1\0");
        digest.update(head_oid.as_bytes());
        for delta in diff.deltas() {
            let path = delta
                .new_file()
                .path()
                .or_else(|| delta.old_file().path())
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();
            let file = self.repository_root.join(&path);
            let content = std::fs::symlink_metadata(&file)
                .ok()
                .filter(|m| m.is_file())
                .and_then(|_| read_file(&file, MAX_FILE).ok())
                .map(|bytes| sha_hex(&bytes))
                .unwrap_or_default();
            digest.update(path.as_bytes());
            digest.update([0, delta.status() as u8, 0]);
            digest.update(content.as_bytes());
            digest.update(b"\n");
        }
        Ok(format!("{:x}", digest.finalize()))
    }

    /// The main repository root this manager is pinned to (integrate target).
    pub(crate) fn repository_root(&self) -> &Path {
        &self.repository_root
    }
}

/// Git blob id of `bytes` (no filters), for tests and diagnostics.
#[allow(dead_code)]
pub(crate) fn blob_id(bytes: &[u8]) -> Option<Oid> {
    Oid::hash_object(git2::ObjectType::Blob, bytes).ok()
}

//! A1 C2-ad (N2, SPEC-A1 v5 §1.7 + v5.1 NB-e/NB-i): owner-confirmed local
//! cleanup of legacy `chat-v1/<key>/worktrees-v1/<ws>/<id>` trees.
//!
//! Only the native UI reaches this module (no MCP tool, no remote caller). It
//! never migrates a tree, never uses `--force`, never prunes globally and never
//! removes a dirty tree or one whose detached HEAD no ref reaches.
use super::super::worktree_git::{
    head_reachable_from_refs, interrupted_registration, prune_missing_registration, run_git,
};
use super::{error, native, ManagedWorktree, WorktreeManager, WorktreeResult};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

/// Journal entries kept (oldest dropped first).
const JOURNAL_LIMIT: usize = 64;
const JOURNAL_DIR: &str = "legacy-cleanup-journal";

/// One legacy tree offered for cleanup. `path` is the canonical tree path; it
/// is part of the confirmation digest but only shown to the local owner.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct LegacyCandidate {
    pub id: String,
    pub display_path: String,
    pub head: String,
    pub head_short: String,
    pub clean: bool,
    /// A1 C14 (SCOPE A′ 1): an interrupted delete whose tree is already gone
    /// and whose registration no longer verifies; only its own leftover Git
    /// metadata remains. Part of the confirmation digest.
    pub interrupted: bool,
    /// A1 C14 S1b (nit 2): preview-only hint, `LOCKED` or `PINNED`, when the
    /// confirm would refuse this candidate with zero deletion. Not part of the
    /// confirmation digest.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hint: Option<&'static str>,
    #[serde(skip)]
    pub(crate) path: PathBuf,
    #[serde(skip)]
    root: PathBuf,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum LegacyState {
    Planned,
    Removed,
    SkippedDirty,
    SkippedUnreachable,
    Failed,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct LegacyOutcome {
    pub id: String,
    pub state: LegacyState,
    /// `DIRTY`, `UNREACHABLE_HEAD`, or the failure code (e.g. `LOCKED`, NB-l;
    /// `REFS_LIMIT`, NB-r).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
}

/// A1 C2-ad2 (NB-c2, SPEC-A1 v5.2 §1.7): a legacy tree left out of the
/// preview because its path could not be canonicalized. It is never offered,
/// so it can neither be selected nor change the confirmation digest.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct LegacyWarning {
    pub id: String,
    pub code: &'static str,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct JournalEntry {
    id: String,
    path: String,
    head: String,
    digest: String,
    state: LegacyState,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    code: Option<String>,
    at_unix: u64,
    /// Asia/Shanghai (UTC+8) wall time, `YYYY-MM-DD HH:MM:SS +08:00`.
    at_beijing: String,
}

#[derive(Debug, Default, Deserialize, Serialize)]
struct JournalDoc {
    version: u32,
    entries: Vec<JournalEntry>,
}

/// `<store_root>/agents-v1/<ws>/legacy-cleanup-journal` (an AuthDocument, like
/// the integrate journal of v5 §5.3), bounded to the newest 64 entries.
pub(crate) struct LegacyJournal {
    disk: crate::data::AuthDocument,
    doc: JournalDoc,
}

fn store_failed() -> super::WorktreeError {
    error(
        "STORE_UNAVAILABLE",
        "Legacy cleanup journal is unavailable.",
    )
}

impl LegacyJournal {
    pub(crate) fn open(manager: &WorktreeManager) -> WorktreeResult<Self> {
        let dir = manager
            .harness_root
            .join("agents-v1")
            .join(&manager.workspace_id)
            .join(JOURNAL_DIR);
        let disk = crate::data::AuthDocument::open(&dir).map_err(|_| store_failed())?;
        let doc = disk
            .load::<JournalDoc>()
            .map_err(|_| store_failed())?
            .unwrap_or(JournalDoc {
                version: 1,
                entries: Vec::new(),
            });
        if doc.version != 1 || doc.entries.len() > JOURNAL_LIMIT {
            return Err(store_failed());
        }
        Ok(Self { disk, doc })
    }
    fn record(
        &mut self,
        candidate: &LegacyCandidate,
        digest: &str,
        state: LegacyState,
        code: Option<&str>,
    ) -> WorktreeResult<()> {
        let at_unix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |d| d.as_secs());
        let entry = JournalEntry {
            id: candidate.id.clone(),
            path: candidate.path.to_string_lossy().into_owned(),
            head: candidate.head.clone(),
            digest: digest.to_owned(),
            state,
            code: code.map(str::to_owned),
            at_unix,
            at_beijing: beijing(at_unix),
        };
        // A planned entry is replaced by its own final state (same id + digest).
        match self.doc.entries.iter_mut().rev().find(|e| {
            e.id == entry.id && e.digest == entry.digest && e.state == LegacyState::Planned
        }) {
            Some(planned) if state != LegacyState::Planned => *planned = entry,
            _ => self.doc.entries.push(entry),
        }
        let excess = self.doc.entries.len().saturating_sub(JOURNAL_LIMIT);
        self.doc.entries.drain(..excess);
        self.disk.save(&self.doc).map_err(|_| store_failed())
    }
    /// `(id, state, code)` of every entry, oldest first.
    #[cfg(test)]
    pub(crate) fn states(&self) -> Vec<(String, LegacyState, Option<String>)> {
        self.doc
            .entries
            .iter()
            .map(|e| (e.id.clone(), e.state, e.code.clone()))
            .collect()
    }
}

/// `YYYY-MM-DD HH:MM:SS +08:00` for a unix time (fixed UTC+8, no DST).
fn beijing(unix: u64) -> String {
    let local = unix + 8 * 3600;
    let (days, secs) = ((local / 86_400) as i64, local % 86_400);
    // Civil-from-days (Howard Hinnant), proleptic Gregorian.
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02} {:02}:{:02}:{:02} +08:00",
        secs / 3600,
        secs / 60 % 60,
        secs % 60
    )
}

/// sha256 over the sorted `(id, canonical path, HEAD)` list (v5 §1.7 step 2).
/// A1 C14 (SCOPE A′ 3): an interrupted candidate's row carries a fourth
/// `"interrupted"` field, so a kind change changes the digest; rows of
/// ordinary trees (and so every digest without interrupted rows) are unchanged.
/// C13d: `hint` is never part of this digest (summary-only).
pub(crate) fn legacy_digest(candidates: &[LegacyCandidate]) -> String {
    let mut rows: Vec<Vec<String>> = candidates
        .iter()
        .map(|c| {
            let mut row = vec![
                c.id.clone(),
                c.path.to_string_lossy().into_owned(),
                c.head.clone(),
            ];
            if c.interrupted {
                row.push("interrupted".to_owned());
            }
            row
        })
        .collect();
    rows.sort();
    let bytes = serde_json::to_vec(&rows).unwrap_or_default();
    format!("{:x}", Sha256::digest(bytes))
}

impl WorktreeManager {
    /// The legacy trees of this main root, each with a clean/dirty flag.
    /// Recovers interrupted (`planned`) journal entries first.
    pub(crate) fn legacy_candidates(
        &self,
        journal: &mut LegacyJournal,
    ) -> WorktreeResult<Vec<LegacyCandidate>> {
        self.legacy_preview(journal)
            .map(|(candidates, _)| candidates)
    }

    /// [`Self::legacy_candidates`] plus the NB-c2 warnings of trees left out.
    pub(crate) fn legacy_preview(
        &self,
        journal: &mut LegacyJournal,
    ) -> WorktreeResult<(Vec<LegacyCandidate>, Vec<LegacyWarning>)> {
        let _guard = native::lock()?;
        self.recover_legacy_journal(journal)?;
        self.legacy_candidates_locked(journal)
    }

    fn legacy_candidates_locked(
        &self,
        journal: &LegacyJournal,
    ) -> WorktreeResult<(Vec<LegacyCandidate>, Vec<LegacyWarning>)> {
        let (rooted, _) = self.legacy_scan_rooted()?;
        let mut result = Vec::new();
        let mut warnings = Vec::new();
        for (item, root) in rooted {
            let ManagedWorktree {
                id,
                display_path,
                head,
                ..
            } = item;
            // NB-c2: one tree whose path cannot be canonicalized (vanished,
            // unreadable component) is skipped with a warning; the rest of the
            // preview stands. A canonical path outside its root still fails.
            let path = match canonical_tree(&root, &id) {
                Ok(path) => path,
                Err(_) => {
                    eprintln!("warning: skipped legacy worktree {id}: CANONICALIZE_FAILED");
                    warnings.push(LegacyWarning {
                        id,
                        code: "CANONICALIZE_FAILED",
                    });
                    continue;
                }
            };
            if path.parent() != Some(root.as_path()) {
                return Err(super::boundary_error());
            }
            let clean = self.legacy_tree_clean(&root, &path).unwrap_or(false);
            result.push(LegacyCandidate {
                head_short: head.chars().take(12).collect(),
                id,
                display_path,
                head,
                clean,
                interrupted: false,
                hint: None,
                path,
                root,
            });
        }
        // A1 C14 (SCOPE A′ 1): interrupted deletes, bound by their journal entry.
        let mut seen = Vec::new();
        for entry in journal.doc.entries.iter().rev() {
            if seen.contains(&entry.id) {
                continue;
            }
            seen.push(entry.id.clone());
            if entry.state != LegacyState::Failed || result.iter().any(|c| c.id == entry.id) {
                continue;
            }
            if let Some(root) = self.interrupted_root(&entry.id, &entry.path) {
                if !super::valid_head(&entry.head) {
                    continue;
                }
                result.push(LegacyCandidate {
                    display_path: format!("legacy/{}", entry.id),
                    head_short: entry.head.chars().take(12).collect(),
                    head: entry.head.clone(),
                    clean: false,
                    interrupted: true,
                    hint: None,
                    path: PathBuf::from(&entry.path),
                    id: entry.id.clone(),
                    root,
                });
            }
        }
        result.sort_by(|a, b| a.id.cmp(&b.id));
        for c in &mut result {
            c.hint = self.legacy_hint(c);
        }
        Ok((result, warnings))
    }

    /// A1 C14 (SCOPE A′ 1/2/7): the legacy root of an interrupted delete of
    /// `id` journalled at `path`, or `None`. `root = path.parent()` must be an
    /// existing real directory `<harness>/chat-v1/<64 hex>/worktrees-v1/<ws>`
    /// equal to its own canonical form (checked before [`Self::legacy_manager`],
    /// which would otherwise create directories), and `path` must equal
    /// `canonical(root)/id` in the journal's own serialization. Then
    /// [`interrupted_registration`] must hold. Any mismatch (Windows `\\?\`
    /// prefix or case included) is `None`: fail closed, not listed.
    fn interrupted_root(&self, id: &str, path: &str) -> Option<PathBuf> {
        if !super::valid_id(id) {
            return None;
        }
        // A1 C14 S1b (nit 1) / S1c (soft nit 3): an id that is live (or present
        // in any form) under the managed root is never an interrupted legacy
        // delete. Fail closed: only NotFound means "absent / continue"; any
        // other symlink_metadata error (EACCES, …) is treated as present.
        match fs::symlink_metadata(self.managed_root.join(id)) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            _ => return None,
        }
        let root = Path::new(path).parent()?.to_path_buf();
        let hex = |s: &str| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit());
        let ws = root.file_name()?.to_str()?;
        let v1 = root.parent()?;
        let key_dir = v1.parent()?;
        if ws != self.workspace_id
            || v1.file_name()?.to_str()? != "worktrees-v1"
            || !hex(key_dir.file_name()?.to_str()?)
            || key_dir.parent()? != self.harness_root.join("chat-v1").as_path()
        {
            return None;
        }
        for dir in [key_dir, v1, root.as_path()] {
            let meta = fs::symlink_metadata(dir).ok()?;
            if !meta.is_dir() || super::is_link_or_reparse(&meta) {
                return None;
            }
        }
        let canonical = root.canonicalize().ok()?;
        if canonical != root {
            return None;
        }
        if canonical.join(id).to_string_lossy() != path {
            return None;
        }
        self.legacy_manager(&root).ok()?;
        interrupted_registration(&self.repository_root, &root, id).then_some(root)
    }

    /// A1 C14 S1b (nit 2): `LOCKED` / `PINNED` preview hint, mirroring the
    /// refusals of the delete path (registration `locked` file; pin file next
    /// to the tree under its legacy root). Display only.
    ///
    /// C13d PINNED mapping (hint ↔ error code): the preview hint string is
    /// `"PINNED"`, while the delete-path refusal code is `WORKTREE_PINNED`
    /// (see `worktree_git`). They stay distinct on purpose — do not rename the
    /// hint to match the code, and do not fold the code into the hint.
    fn legacy_hint(&self, c: &LegacyCandidate) -> Option<&'static str> {
        if let Ok(meta) =
            super::super::worktree_git::managed_metadata_dir(&self.repository_root, &c.id)
        {
            if fs::symlink_metadata(meta.join("locked")).is_ok() {
                return Some("LOCKED");
            }
        }
        if fs::symlink_metadata(c.root.join(format!("{}.native-profile-pin", c.id))).is_ok() {
            return Some("PINNED");
        }
        None
    }

    fn legacy_tree_clean(&self, root: &Path, path: &Path) -> WorktreeResult<bool> {
        let status = run_git(
            path,
            &[
                OsString::from("status"),
                OsString::from("--porcelain=v1"),
                OsString::from("--untracked-files=all"),
                OsString::from("--ignored"),
                OsString::from("-z"),
            ],
            &self.repository_root,
            Some(root),
        )?;
        Ok(status.success && status.stdout.is_empty())
    }

    /// The manager whose managed root is this legacy root (`chat-v1/<key>`).
    fn legacy_manager(&self, root: &Path) -> WorktreeResult<WorktreeManager> {
        let harness = root
            .parent()
            .and_then(Path::parent)
            .filter(|h| h.parent() == Some(self.harness_root.join("chat-v1").as_path()))
            .ok_or_else(super::boundary_error)?;
        let manager = WorktreeManager::new(&self.repository_root, harness, &self.workspace_id)?;
        if manager.managed_root != root {
            return Err(super::boundary_error());
        }
        Ok(manager)
    }

    /// Removes the owner-confirmed `selected` legacy trees. `digest` must match
    /// the current candidate list (any change voids the confirmation). Each id
    /// is journalled `planned`, re-verified (still registered, still under its
    /// legacy root, HEAD unchanged), skipped when its HEAD is unreachable from
    /// every ref (`UNREACHABLE_HEAD`, NB-e) or when dirty (`DIRTY`), and else
    /// removed by the same rule as [`WorktreeManager::remove_clean`]: only that
    /// tree and its own `.git/worktrees/<id>`; never `--force`, never a prune.
    pub(crate) fn cleanup_legacy(
        &self,
        journal: &mut LegacyJournal,
        selected: &[String],
        digest: &str,
    ) -> WorktreeResult<Vec<LegacyOutcome>> {
        let _guard = native::lock()?;
        self.recover_legacy_journal(journal)?;
        let (candidates, _) = self.legacy_candidates_locked(journal)?;
        if legacy_digest(&candidates) != digest {
            return Err(error(
                "STALE_CONFIRMATION",
                "The legacy worktree list changed after confirmation; confirm again.",
            ));
        }
        let mut unique = selected.to_vec();
        unique.sort();
        unique.dedup();
        if unique.is_empty()
            || unique.len() != selected.len()
            || !unique
                .iter()
                .all(|id| candidates.iter().any(|c| &c.id == id))
        {
            return Err(error(
                "INVALID_ARGUMENT",
                "Select confirmed legacy worktrees only.",
            ));
        }
        let mut outcomes = Vec::new();
        for id in selected {
            let candidate = candidates
                .iter()
                .find(|c| &c.id == id)
                .ok_or_else(super::boundary_error)?;
            journal.record(candidate, digest, LegacyState::Planned, None)?;
            let (state, code) = self.remove_one_legacy(candidate);
            journal.record(candidate, digest, state, code)?;
            outcomes.push(LegacyOutcome {
                id: id.clone(),
                state,
                code,
            });
        }
        Ok(outcomes)
    }

    fn remove_one_legacy(
        &self,
        candidate: &LegacyCandidate,
    ) -> (LegacyState, Option<&'static str>) {
        if candidate.interrupted {
            return self.remove_one_interrupted(candidate);
        }
        // Re-verify: registered, back-pointer under the same legacy root, same HEAD.
        let current = match self.legacy_scan_rooted() {
            Ok((rooted, _)) => rooted,
            Err(e) => return (LegacyState::Failed, Some(e.code())),
        };
        if !current.iter().any(|(item, root)| {
            item.id == candidate.id && item.head == candidate.head && *root == candidate.root
        }) {
            return (LegacyState::Failed, Some("CHANGED"));
        }
        match head_reachable_from_refs(&self.repository_root, &candidate.head) {
            Ok(true) => {}
            Ok(false) => return (LegacyState::SkippedUnreachable, Some("UNREACHABLE_HEAD")),
            Err(e) => return (LegacyState::Failed, Some(e.code())),
        }
        let manager = match self.legacy_manager(&candidate.root) {
            Ok(manager) => manager,
            Err(e) => return (LegacyState::Failed, Some(e.code())),
        };
        // A1 C12b D2: legacy trees are never worker-owned and were re-verified
        // above, so a marker left by an interrupted cleanup may be resumed.
        match manager.remove_clean_locked(&candidate.id, true) {
            Ok(()) => {
                // Only an empty `worktrees-v1/<ws>`; `chat-v1/<key>` itself stays.
                let _ = fs::remove_dir(&candidate.root);
                (LegacyState::Removed, None)
            }
            Err(e) if e.code() == "DIRTY" => (LegacyState::SkippedDirty, Some("DIRTY")),
            Err(e) => (LegacyState::Failed, Some(e.code())),
        }
    }

    /// A1 C14 (SCOPE A′ 3): finish an owner-confirmed interrupted delete. The
    /// binding is re-verified under the same lifecycle lock, then the delete
    /// resumes through `legacy_manager(root).remove_clean_locked(id, true)`,
    /// whose LOCKED / PINNED / gitdir back-pointer refusals all still apply.
    /// HEAD reachability is not consulted: the checkout is already gone.
    fn remove_one_interrupted(
        &self,
        candidate: &LegacyCandidate,
    ) -> (LegacyState, Option<&'static str>) {
        let path = candidate.path.to_string_lossy();
        if self.interrupted_root(&candidate.id, &path).as_deref() != Some(candidate.root.as_path())
        {
            return (LegacyState::Failed, Some("CHANGED"));
        }
        let manager = match self.legacy_manager(&candidate.root) {
            Ok(manager) => manager,
            Err(e) => return (LegacyState::Failed, Some(e.code())),
        };
        match manager.remove_clean_locked(&candidate.id, true) {
            Ok(()) => {
                let _ = fs::remove_dir(&candidate.root);
                (LegacyState::Removed, None)
            }
            Err(e) => (LegacyState::Failed, Some(e.code())),
        }
    }

    /// Crash recovery (v5 §1.7 step 4): a `planned` entry whose tree is gone has
    /// only its own registration pruned and becomes `removed`; one whose tree
    /// still exists becomes `failed` and is never retried automatically.
    fn recover_legacy_journal(&self, journal: &mut LegacyJournal) -> WorktreeResult<()> {
        let planned: Vec<JournalEntry> = journal
            .doc
            .entries
            .iter()
            .filter(|e| e.state == LegacyState::Planned)
            .cloned()
            .collect();
        for entry in planned {
            let path = PathBuf::from(&entry.path);
            let root = path.parent().map(Path::to_path_buf).unwrap_or_default();
            let candidate = LegacyCandidate {
                id: entry.id.clone(),
                display_path: format!("legacy/{}", entry.id),
                head_short: String::new(),
                head: entry.head.clone(),
                clean: false,
                path: path.clone(),
                root: root.clone(),
                interrupted: false,
                hint: None,
            };
            let (state, code) = if fs::symlink_metadata(&path).is_err() {
                match prune_missing_registration(&self.repository_root, &root, &entry.id) {
                    Ok(_) => (LegacyState::Removed, None),
                    Err(e) => (LegacyState::Failed, Some(e.code())),
                }
            } else {
                (LegacyState::Failed, Some("INTERRUPTED"))
            };
            journal.record(&candidate, &entry.digest, state, code)?;
        }
        Ok(())
    }
}

fn canonical_tree(root: &Path, id: &str) -> std::io::Result<PathBuf> {
    #[cfg(test)]
    if canonicalize_hooks::fails(id) {
        return Err(std::io::Error::other("injected"));
    }
    root.join(id).canonicalize()
}

/// Test seam (NB-c2): make `canonical_tree` fail for one id on this thread.
#[cfg(test)]
pub(crate) mod canonicalize_hooks {
    use std::cell::RefCell;
    thread_local! {
        static FAIL: RefCell<Option<String>> = const { RefCell::new(None) };
    }
    pub(crate) fn fail_for(id: Option<&str>) {
        FAIL.with(|f| *f.borrow_mut() = id.map(str::to_owned));
    }
    pub(super) fn fails(id: &str) -> bool {
        FAIL.with(|f| f.borrow().as_deref() == Some(id))
    }
}

#[cfg(test)]
#[path = "worktree_legacy_tests.rs"]
mod tests;

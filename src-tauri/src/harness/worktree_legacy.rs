//! A1 C2-ad (N2, SPEC-A1 v5 §1.7 + v5.1 NB-e/NB-i): owner-confirmed local
//! cleanup of legacy `chat-v1/<key>/worktrees-v1/<ws>/<id>` trees.
//!
//! Only the native UI reaches this module (no MCP tool, no remote caller). It
//! never migrates a tree, never uses `--force`, never prunes globally and never
//! removes a dirty tree or one whose detached HEAD no ref reaches.
use super::super::worktree_git::{head_reachable_from_refs, prune_missing_registration, run_git};
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
    /// `DIRTY`, `UNREACHABLE_HEAD`, or the failure code.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<&'static str>,
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
pub(crate) fn legacy_digest(candidates: &[LegacyCandidate]) -> String {
    let mut rows: Vec<(&str, String, &str)> = candidates
        .iter()
        .map(|c| {
            (
                c.id.as_str(),
                c.path.to_string_lossy().into_owned(),
                c.head.as_str(),
            )
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
        let _guard = native::lock()?;
        self.recover_legacy_journal(journal)?;
        self.legacy_candidates_locked()
    }

    fn legacy_candidates_locked(&self) -> WorktreeResult<Vec<LegacyCandidate>> {
        let (rooted, _) = self.legacy_scan_rooted()?;
        let mut result = Vec::new();
        for (item, root) in rooted {
            let ManagedWorktree {
                id,
                display_path,
                head,
                ..
            } = item;
            let path = root
                .join(&id)
                .canonicalize()
                .map_err(|_| super::boundary_error())?;
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
                path,
                root,
            });
        }
        Ok(result)
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
        let candidates = self.legacy_candidates_locked()?;
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
        match manager.remove_clean_locked(&candidate.id) {
            Ok(()) => {
                // Only an empty `worktrees-v1/<ws>`; `chat-v1/<key>` itself stays.
                let _ = fs::remove_dir(&candidate.root);
                (LegacyState::Removed, None)
            }
            Err(e) if e.code() == "DIRTY" => (LegacyState::SkippedDirty, Some("DIRTY")),
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

#[cfg(test)]
#[path = "worktree_legacy_tests.rs"]
mod tests;

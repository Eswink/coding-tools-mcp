//! A1 C5 (SPEC-A1 v5.2 §5.1.1, v5.1 NB-c): the per-file rule table shared by
//! crash recovery (`prepared` / `rolling_back` → back to pre) and the owner's
//! rollback request (stricter: every file must still be the post-image).
use super::journal::{JournalEntry, PostImage, PreImage};
use super::mainfs::{self, Current, Parents, Step};
use std::path::Path;

/// What crash recovery does with one entry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Action {
    /// Write the pre-image back (content, executable bit, existence).
    Restore,
    /// Already at pre: nothing to write.
    Keep,
    /// «其他 / journal 损坏»: the whole journal goes to `needs_attention`.
    Attention,
}

/// One row of the §5.1.1 table for one journal entry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Verdict {
    /// The table row (1-12).
    pub(crate) row: u8,
    /// The «崩溃恢复动作» column.
    pub(crate) crash: Action,
    /// The «rollback 请求» column: allowed (`true`) or `ROLLBACK_CONFLICT`.
    pub(crate) rollback: bool,
}
const fn verdict(row: u8, crash: Action, rollback: bool) -> Verdict {
    Verdict {
        row,
        crash,
        rollback,
    }
}

fn pre_of(pre: &PreImage) -> Option<(&str, bool)> {
    Some((pre.sha256.as_str(), pre.exec))
}
fn post_of(post: &PostImage) -> Option<(&str, bool)> {
    Some((post.sha256.as_str(), post.exec))
}

/// Classifies one entry against the main workspace without writing anything.
pub(crate) fn classify(root: &Path, entry: &JournalEntry) -> Verdict {
    use Action::{Attention, Keep, Restore};
    let current = mainfs::current(root, &entry.path);
    let deleted = entry.pre.is_some() && entry.post.is_none();
    if deleted && mainfs::parents(root, &entry.path) == Parents::Blocked {
        // Row 5 with a link/file parent: «其他», never rebuilt through it.
        return verdict(5, Attention, false);
    }
    if current == Current::Other {
        return verdict(12, Attention, false);
    }
    match (&entry.pre, &entry.post) {
        (None, None) => verdict(11, Attention, false),
        (Some(pre), Some(post)) => {
            let at_pre = mainfs::same(&current, pre_of(pre));
            let at_post = mainfs::same(&current, post_of(post));
            match (at_pre, at_post) {
                // pre == post (never produced by a diff): rows 1 and 2 both hold;
                // nothing to write and no conflict (v5.1 NB-c).
                (true, true) => verdict(1, Keep, true),
                (false, true) => verdict(1, Restore, true),
                (true, false) => verdict(2, Keep, false),
                (false, false) if current == Current::Absent => verdict(4, Attention, false),
                (false, false) => verdict(3, Attention, false),
            }
        }
        (Some(pre), None) => {
            if current == Current::Absent {
                // NB-c: every missing parent is re-created inside the root.
                verdict(5, Restore, true)
            } else if mainfs::same(&current, pre_of(pre)) {
                verdict(6, Keep, false)
            } else {
                verdict(7, Attention, false)
            }
        }
        (None, Some(post)) => {
            if mainfs::same(&current, post_of(post)) {
                verdict(8, Restore, true)
            } else if current == Current::Absent {
                verdict(9, Keep, false)
            } else {
                verdict(10, Attention, false)
            }
        }
    }
}

/// The steps that bring every `Restore` entry back to its pre-image, in
/// journal order. `None` when a pre-image no longer decodes (journal corrupt).
pub(crate) fn restore_steps(
    root: &Path,
    entries: &[JournalEntry],
    verdicts: &[Verdict],
) -> Option<Vec<Step>> {
    let mut steps = Vec::new();
    for (entry, verdict) in entries.iter().zip(verdicts) {
        if verdict.crash != Action::Restore {
            continue;
        }
        let target = match &entry.pre {
            Some(pre) => Some((pre.bytes().ok()?, pre.exec)),
            None => None,
        };
        let create_dirs = match (&entry.pre, mainfs::parents(root, &entry.path)) {
            (Some(_), Parents::Missing(dirs)) => dirs,
            _ => Vec::new(),
        };
        steps.push(Step {
            path: entry.path.clone(),
            target,
            prior: mainfs::read(root, &entry.path),
            create_dirs,
            // Row 8: the parents integrate created go while they are empty.
            remove_dirs: if entry.pre.is_none() {
                entry.created_dirs.clone()
            } else {
                Vec::new()
            },
        });
    }
    Some(steps)
}

//! A1 C2-ad (N2 + NB-e, SPEC-A1 v5 §1.7, T17): owner-confirmed local cleanup
//! of legacy chat-v1 trees.
use super::super::{WorktreeManager, MAX_MANAGED_WORKTREES};
use super::*;
use std::{fs, path::Path, process::Command};

const WS: &str = "0123456789abcdef0123456789abcdef";

fn git(dir: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .current_dir(dir)
        .args(args)
        .output()
        .unwrap();
    assert!(output.status.success(), "git {args:?}: {output:?}");
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

struct Fixture {
    repo: tempfile::TempDir,
    harness: tempfile::TempDir,
    main: WorktreeManager,
}
impl Fixture {
    fn new() -> Self {
        let repo = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        git(repo.path(), &["init", "-q"]);
        git(
            repo.path(),
            &["config", "user.email", "tests@example.invalid"],
        );
        git(repo.path(), &["config", "user.name", "Legacy Tests"]);
        fs::write(repo.path().join("README.md"), "baseline\n").unwrap();
        git(repo.path(), &["add", "README.md"]);
        git(repo.path(), &["commit", "-q", "-m", "initial"]);
        let main = WorktreeManager::new(repo.path(), harness.path(), WS).unwrap();
        Self {
            repo,
            harness,
            main,
        }
    }
    /// A legacy tree under `chat-v1/<key>`; returns (id, tree path).
    fn legacy(&self, key: &str) -> (String, PathBuf) {
        let root = self.harness.path().join("chat-v1").join(key);
        fs::create_dir_all(&root).unwrap();
        let manager = WorktreeManager::new(self.repo.path(), &root, WS).unwrap();
        let id = manager.create_detached().unwrap().id;
        let path = root.join("worktrees-v1").join(WS).join(&id);
        (id, path)
    }
    fn registration(&self, id: &str) -> PathBuf {
        self.repo.path().join(".git").join("worktrees").join(id)
    }
    fn journal(&self) -> LegacyJournal {
        LegacyJournal::open(&self.main).unwrap()
    }
    fn preview(&self) -> (Vec<LegacyCandidate>, String) {
        let candidates = self.main.legacy_candidates(&mut self.journal());
        assert!(candidates.is_ok(), "preview failed: {candidates:?}");
        let candidates = candidates.unwrap();
        let digest = legacy_digest(&candidates);
        (candidates, digest)
    }
}

#[test]
fn a_clean_reachable_legacy_tree_is_removed_with_only_its_own_registration() {
    let f = Fixture::new();
    let (a, a_path) = f.legacy(&"ab".repeat(32));
    let (b, b_path) = f.legacy(&"cd".repeat(32));
    let (candidates, digest) = f.preview();
    assert_eq!(candidates.len(), 2);
    assert!(candidates
        .iter()
        .all(|c| c.clean && c.display_path == format!("legacy/{}", c.id)));
    let mut journal = f.journal();
    let out = f
        .main
        .cleanup_legacy(&mut journal, std::slice::from_ref(&a), &digest)
        .unwrap();
    assert_eq!(
        out,
        vec![LegacyOutcome {
            id: a.clone(),
            state: LegacyState::Removed,
            code: None
        }]
    );
    drop(journal); // the journal is single-holder (AuthDocument lock)
    assert!(!a_path.exists() && !f.registration(&a).exists());
    // The emptied `worktrees-v1/<ws>` goes; `chat-v1/<key>` stays.
    assert!(!a_path.parent().unwrap().exists());
    assert!(f
        .harness
        .path()
        .join("chat-v1")
        .join("ab".repeat(32))
        .is_dir());
    // The other tree and its registration are untouched.
    assert!(b_path.join("README.md").is_file() && f.registration(&b).is_dir());
    assert_eq!(
        f.main
            .legacy_list()
            .unwrap()
            .into_iter()
            .map(|i| i.id)
            .collect::<Vec<_>>(),
        vec![b]
    );
    assert_eq!(
        f.journal().states(),
        vec![(a, LegacyState::Removed, None)],
        "the planned entry is replaced by its final state"
    );
}

#[test]
fn a_dirty_legacy_tree_is_skipped_and_its_files_are_untouched() {
    let f = Fixture::new();
    let (id, path) = f.legacy(&"ab".repeat(32));
    fs::write(path.join("README.md"), "local edit\n").unwrap();
    fs::write(path.join("notes.txt"), "untracked\n").unwrap();
    let (candidates, digest) = f.preview();
    assert!(!candidates[0].clean);
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
        .unwrap();
    assert_eq!(out[0].state, LegacyState::SkippedDirty);
    assert_eq!(out[0].code, Some("DIRTY"));
    assert_eq!(
        fs::read_to_string(path.join("README.md")).unwrap(),
        "local edit\n"
    );
    assert_eq!(
        fs::read_to_string(path.join("notes.txt")).unwrap(),
        "untracked\n"
    );
    assert!(f.registration(&id).is_dir());
    assert_eq!(
        f.journal().states(),
        vec![(id, LegacyState::SkippedDirty, Some("DIRTY".into()))]
    );
}

/// NB-e (v5.1 §1.7): a detached legacy HEAD that no ref reaches may be the
/// only copy of a commit; it is skipped (`UNREACHABLE_HEAD`), never removed,
/// and other worktrees are unaffected. Peeled tags and packed refs count.
#[test]
fn an_unreachable_legacy_head_is_skipped_and_other_worktrees_are_unaffected() {
    let f = Fixture::new();
    fs::write(f.repo.path().join("README.md"), "second\n").unwrap();
    git(f.repo.path(), &["commit", "-qam", "second"]);
    let lost = git(f.repo.path(), &["rev-parse", "HEAD"]);
    let (orphan, orphan_path) = f.legacy(&"ab".repeat(32));
    git(f.repo.path(), &["reset", "-q", "--hard", "HEAD~1"]);
    let (kept, kept_path) = f.legacy(&"cd".repeat(32));
    let main_tree = f.main.create_detached().unwrap();
    let (candidates, digest) = f.preview();
    assert!(candidates.iter().any(|c| c.id == orphan && c.head == lost));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), &[orphan.clone(), kept.clone()], &digest)
        .unwrap();
    assert_eq!(
        out.iter()
            .map(|o| (o.id.clone(), o.state, o.code))
            .collect::<Vec<_>>(),
        vec![
            (
                orphan.clone(),
                LegacyState::SkippedUnreachable,
                Some("UNREACHABLE_HEAD")
            ),
            (kept.clone(), LegacyState::Removed, None),
        ]
    );
    assert!(orphan_path.join("README.md").is_file() && f.registration(&orphan).is_dir());
    assert_eq!(
        fs::read_to_string(orphan_path.join("README.md")).unwrap(),
        "second\n"
    );
    assert!(!kept_path.exists() && !f.registration(&kept).exists());
    assert_eq!(f.main.list().unwrap(), vec![main_tree]);
    assert_eq!(
        fs::read_to_string(f.repo.path().join("README.md")).unwrap(),
        "baseline\n"
    );
    // An annotated tag (peeled), then packed into packed-refs, makes it reachable.
    git(f.repo.path(), &["tag", "-a", "keep", "-m", "keep", &lost]);
    git(f.repo.path(), &["pack-refs", "--all"]);
    assert!(!f.repo.path().join(".git/refs/tags/keep").exists());
    let reachable = head_reachable_from_refs(f.repo.path(), &lost).map_err(|e| e.code());
    assert_eq!(reachable, Ok(true));
}

#[test]
fn a_legacy_tree_appearing_after_confirmation_voids_the_digest() {
    let f = Fixture::new();
    let (id, path) = f.legacy(&"ab".repeat(32));
    let (_, digest) = f.preview();
    let _late = f.legacy(&"cd".repeat(32));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest);
    assert_eq!(out.map_err(|e| e.code()), Err("STALE_CONFIRMATION"));
    assert!(path.is_dir() && f.registration(&id).is_dir());
    assert!(f.journal().states().is_empty(), "nothing was planned");
    // Unknown or duplicate ids are refused even with a fresh digest.
    let (_, digest) = f.preview();
    for ids in [vec!["f".repeat(32)], vec![id.clone(), id.clone()], vec![]] {
        let out = f.main.cleanup_legacy(&mut f.journal(), &ids, &digest);
        assert_eq!(
            out.map_err(|e| e.code()),
            Err("INVALID_ARGUMENT"),
            "{ids:?}"
        );
    }
    assert!(path.is_dir());
}

/// v5 §1.7 step 4: a crash after `planned` is recovered on the next open; a
/// gone tree only loses its own registration, a present one becomes `failed`.
#[test]
fn an_interrupted_planned_entry_is_recovered_without_a_global_prune() {
    let f = Fixture::new();
    let (gone, gone_path) = f.legacy(&"ab".repeat(32));
    let (stays, stays_path) = f.legacy(&"cd".repeat(32));
    let (other, _) = f.legacy(&"ef".repeat(32));
    let (candidates, digest) = f.preview();
    let mut journal = f.journal();
    for id in [&gone, &stays] {
        let c = candidates.iter().find(|c| &c.id == id).unwrap();
        journal
            .record(c, &digest, LegacyState::Planned, None)
            .unwrap();
    }
    drop(journal); // crash: the process ends with both entries `planned`
                   // Crash point: the tree was deleted, its registration was not.
    fs::remove_dir_all(&gone_path).unwrap();
    // An unrelated stale registration must survive (no global prune).
    let (stale, stale_path) = f.legacy(&"12".repeat(32));
    fs::remove_dir_all(&stale_path).unwrap();
    let (after, _) = f.preview();
    assert_eq!(
        f.journal().states(),
        vec![
            (gone.clone(), LegacyState::Removed, None),
            (
                stays.clone(),
                LegacyState::Failed,
                Some("INTERRUPTED".into())
            ),
        ]
    );
    assert!(!f.registration(&gone).exists());
    assert!(stays_path.is_dir() && f.registration(&stays).is_dir());
    assert!(f.registration(&other).is_dir() && f.registration(&stale).is_dir());
    assert!(after.iter().any(|c| c.id == stays) && after.iter().any(|c| c.id == other));
}

#[test]
fn eight_legacy_trees_fill_the_slots_with_legacy_slots_and_one_cleanup_frees_one() {
    let f = Fixture::new();
    let ids: Vec<String> = (0..MAX_MANAGED_WORKTREES)
        .map(|n| f.legacy(&format!("{n:x}").repeat(64)).0)
        .collect();
    for result in [
        f.main.create_detached().map(|_| ()),
        f.main.reserve_slot().map(|_| ()),
    ] {
        let error = result.unwrap_err();
        assert_eq!((error.code(), error.legacy_slots()), ("CAPACITY", Some(8)));
    }
    let (_, digest) = f.preview();
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), &ids[..1], &digest)
        .unwrap();
    assert_eq!(out[0].state, LegacyState::Removed);
    assert!(f.main.create_detached().is_ok());
    let error = f.main.create_detached().unwrap_err();
    assert_eq!(
        (error.code(), error.legacy_slots()),
        ("CAPACITY", None),
        "7 legacy + 1 main"
    );
}

/// A1 C2-ad2 (NB-l, SPEC-A1 v5.2 §1.7): crash recovery never prunes a locked
/// registration (`.git/worktrees/<id>/locked`) even when its tree is gone; the
/// entry becomes `failed` with `LOCKED` and the registration stays.
#[test]
fn recovery_never_prunes_a_locked_registration() {
    let f = Fixture::new();
    let (locked, locked_path) = f.legacy(&"ab".repeat(32));
    let (plain, plain_path) = f.legacy(&"cd".repeat(32));
    let (candidates, digest) = f.preview();
    let mut journal = f.journal();
    for id in [&locked, &plain] {
        let c = candidates.iter().find(|c| &c.id == id).unwrap();
        journal
            .record(c, &digest, LegacyState::Planned, None)
            .unwrap();
    }
    drop(journal);
    fs::remove_dir_all(&locked_path).unwrap();
    fs::remove_dir_all(&plain_path).unwrap();
    fs::write(
        f.registration(&locked).join("locked"),
        "on removable media\n",
    )
    .unwrap();
    let _ = f.preview();
    assert_eq!(
        f.journal().states(),
        vec![
            (locked.clone(), LegacyState::Failed, Some("LOCKED".into())),
            (plain.clone(), LegacyState::Removed, None),
        ]
    );
    assert!(f.registration(&locked).join("locked").is_file());
    assert!(!f.registration(&plain).exists());
    let direct = prune_missing_registration(f.repo.path(), locked_path.parent().unwrap(), &locked)
        .map_err(|e| e.code());
    assert_eq!(direct, Err("LOCKED"));
}

/// A1 C2-ad2 (NB-r, SPEC-A1 v5.2 T17): past the ref scan bounds the answer is
/// its own code `REFS_LIMIT`, never `UNREACHABLE_HEAD`, and nothing is removed.
#[test]
fn too_many_loose_refs_fail_with_refs_limit_not_unreachable() {
    let f = Fixture::new();
    let (id, path) = f.legacy(&"ab".repeat(32));
    let head = git(f.repo.path(), &["rev-parse", "HEAD"]);
    let tags = f.repo.path().join(".git/refs/tags/bulk");
    fs::create_dir_all(&tags).unwrap();
    for n in 0..=crate::harness::worktree_git::REF_SCAN_LIMIT {
        fs::write(tags.join(format!("t{n}")), format!("{head}\n")).unwrap();
    }
    let reachable = head_reachable_from_refs(f.repo.path(), &head).map_err(|e| e.code());
    assert_eq!(reachable, Err("REFS_LIMIT"));
    let (_, digest) = f.preview();
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
        .unwrap();
    assert_eq!(
        (out[0].state, out[0].code),
        (LegacyState::Failed, Some("REFS_LIMIT"))
    );
    assert!(path.join("README.md").is_file() && f.registration(&id).is_dir());
}

#[test]
fn an_oversized_packed_refs_fails_with_refs_limit_not_unreachable() {
    let f = Fixture::new();
    let head = git(f.repo.path(), &["rev-parse", "HEAD"]);
    let mut packed =
        format!("# pack-refs with: peeled fully-peeled sorted \n{head} refs/tags/keep\n");
    let limit = crate::harness::worktree_git::PACKED_REFS_LIMIT as usize;
    while packed.len() <= limit {
        packed.push_str(&format!("{head} refs/tags/pad{}\n", packed.len()));
    }
    fs::write(f.repo.path().join(".git/packed-refs"), packed).unwrap();
    let reachable = head_reachable_from_refs(f.repo.path(), &head).map_err(|e| e.code());
    assert_eq!(reachable, Err("REFS_LIMIT"));
    // At the bound exactly it is still scanned.
    let mut exact = format!("{head} refs/tags/keep\n");
    exact.push_str(&"#".repeat(limit - exact.len() - 1));
    exact.push('\n');
    assert_eq!(exact.len(), limit);
    fs::write(f.repo.path().join(".git/packed-refs"), exact).unwrap();
    let reachable = head_reachable_from_refs(f.repo.path(), &head).map_err(|e| e.code());
    assert_eq!(reachable, Ok(true));
}

/// A1 C2-ad2 (NB-c2, SPEC-A1 v5.2 §1.7): one candidate whose path cannot be
/// canonicalized is left out with a warning; the preview of the others stands
/// and the skipped id cannot be selected.
#[test]
fn a_candidate_that_fails_to_canonicalize_is_skipped_with_a_warning() {
    let f = Fixture::new();
    let (bad, bad_path) = f.legacy(&"ab".repeat(32));
    let (good, good_path) = f.legacy(&"cd".repeat(32));
    canonicalize_hooks::fail_for(Some(&bad));
    let preview = f.main.legacy_preview(&mut f.journal());
    assert!(preview.is_ok(), "preview failed: {preview:?}");
    let (candidates, warnings) = preview.unwrap();
    assert_eq!(
        candidates.iter().map(|c| c.id.clone()).collect::<Vec<_>>(),
        vec![good.clone()]
    );
    assert_eq!(
        warnings,
        vec![LegacyWarning {
            id: bad.clone(),
            code: "CANONICALIZE_FAILED"
        }]
    );
    let digest = legacy_digest(&candidates);
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&bad), &digest);
    assert_eq!(out.map_err(|e| e.code()), Err("INVALID_ARGUMENT"));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&good), &digest)
        .map_err(|e| e.code());
    canonicalize_hooks::fail_for(None);
    assert_eq!(out.map(|o| o[0].state), Ok(LegacyState::Removed));
    assert!(bad_path.join("README.md").is_file() && !good_path.exists());
}

#[test]
fn journal_times_are_asia_shanghai() {
    assert_eq!(beijing(0), "1970-01-01 08:00:00 +08:00");
    assert_eq!(beijing(1_793_404_800), "2026-10-31 08:00:00 +08:00");
}

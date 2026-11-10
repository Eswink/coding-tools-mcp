//! A1 C2-ad (N2 + NB-e, SPEC-A1 v5 §1.7, T17): owner-confirmed local cleanup
//! of legacy chat-v1 trees.
use super::super::{WorktreeManager, MAX_MANAGED_WORKTREES};
use super::*;
use std::{fs, path::Path, process::Command};

const WS: &str = "0123456789abcdef0123456789abcdef";

fn git(dir: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        // Git >= 2.47 detaches auto maintenance after `commit`; newer Git (2.55+)
        // can still hold objects/maintenance.lock after the command returns, and
        // the production boundary scan of .git/objects then fails closed
        // (BOUNDARY_VIOLATION). Same fixture rule as worktree_tests.rs.
        .args(["-c", "maintenance.auto=false"])
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

/// A1 C12b D2: a legacy cleanup interrupted after its marker (step 0, target
/// partly deleted) is finished by the next confirmed cleanup, not DIRTY forever.
#[test]
fn c12b_d2_interrupted_legacy_cleanup_is_finished_on_retry() {
    let f = Fixture::new();
    let (id, path) = f.legacy(&"ab".repeat(32));
    let (_, digest) = f.preview();
    WorktreeManager::set_delete_fail_at_for_test(Some(0));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
        .unwrap();
    WorktreeManager::set_delete_fail_at_for_test(None);
    assert_eq!(out[0].state, LegacyState::Failed);
    assert!(f.registration(&id).join("managed-removing").is_file());
    fs::remove_file(path.join("README.md")).expect("partial target delete");
    let (_, digest) = f.preview();
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
        .unwrap();
    assert_eq!(out[0].state, LegacyState::Removed, "{out:?}");
    assert!(!path.exists() && !f.registration(&id).exists());
    assert!(f.main.legacy_list().unwrap().is_empty());
}

// ---- A1 C14 (SCOPE A′ 1–5): owner-confirmed interrupted legacy deletes ----

/// (target, metadata, marker, gitdir, HEAD) existence, for "nothing deleted".
fn c14_snapshot(f: &Fixture, id: &str, path: &Path) -> [bool; 5] {
    let meta = f.registration(id);
    [
        fs::symlink_metadata(path).is_ok(),
        meta.exists(),
        meta.join("managed-removing").exists(),
        meta.join("gitdir").exists(),
        meta.join("HEAD").exists(),
    ]
}

/// A legacy tree whose confirmed cleanup was interrupted at delete step `k`.
fn c14_interrupted(f: &Fixture, key: &str, k: usize) -> (String, PathBuf) {
    let (id, path) = f.legacy(key);
    let (_, digest) = f.preview();
    WorktreeManager::set_delete_fail_at_for_test(Some(k));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest);
    WorktreeManager::set_delete_fail_at_for_test(None);
    let out = out.unwrap();
    assert_eq!(out[0].state, LegacyState::Failed, "k={k}: {out:?}");
    assert!(f.registration(&id).join("managed-removing").is_file());
    (id, path)
}

fn c14_set_journal_path(f: &Fixture, id: &str, path: &str) {
    let mut j = f.journal();
    let e = j.doc.entries.iter_mut().rev().find(|e| e.id == id).unwrap();
    e.path = path.to_owned();
    j.disk.save(&j.doc).unwrap();
}

/// Not offered, cannot be forced, and not one file of the leftover deleted.
fn c14_assert_refused(f: &Fixture, id: &str, path: &Path) {
    let before = c14_snapshot(f, id, path);
    let (candidates, digest) = f.preview();
    assert!(candidates.iter().all(|c| c.id != id), "{candidates:?}");
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), &[id.to_owned()], &digest);
    assert_eq!(out.unwrap_err().code(), "INVALID_ARGUMENT");
    assert_eq!(c14_snapshot(f, id, path), before);
}

#[test]
fn c14_interrupted_legacy_k1_to_k5_is_offered_and_finished_on_confirmation() {
    for k in 1..=5 {
        let f = Fixture::new();
        let (id, path) = c14_interrupted(&f, &"ab".repeat(32), k);
        let (candidates, digest) = f.preview();
        let c = candidates.iter().find(|c| c.id == id).expect("offered");
        assert!(c.interrupted && !c.clean, "k={k}");
        let out = f
            .main
            .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
            .unwrap();
        assert_eq!(out[0].state, LegacyState::Removed, "k={k}: {out:?}");
        assert!(!f.registration(&id).exists(), "k={k}: metadata cleared");
        assert!(fs::symlink_metadata(&path).is_err());
        assert_eq!(f.main.slots_in_use_for_test(), (0, 0), "k={k}");
        let states = f.journal().states();
        assert_eq!(
            states.last().unwrap(),
            &(id.clone(), LegacyState::Removed, None),
            "k={k}"
        );
        assert!(f.preview().0.is_empty(), "k={k}");
    }
}

#[test]
fn c14_marker_without_journal_is_not_offered() {
    let f = Fixture::new();
    let (id, path) = f.legacy(&"ab".repeat(32));
    fs::write(
        f.registration(&id).join("managed-removing"),
        b"coding-tools-managed-removing\n",
    )
    .unwrap();
    fs::remove_dir_all(&path).unwrap();
    c14_assert_refused(&f, &id, &path);
}

#[test]
fn c14_failed_journal_without_marker_or_with_wrong_marker_is_not_offered() {
    for wrong in [None, Some("coding-tools-managed-removing\r\nextra")] {
        let f = Fixture::new();
        let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
        let marker = f.registration(&id).join("managed-removing");
        match wrong {
            None => fs::remove_file(&marker).unwrap(),
            Some(body) => fs::write(&marker, body).unwrap(),
        }
        c14_assert_refused(&f, &id, &path);
    }
}

#[test]
fn c14_journal_path_must_bind_the_canonical_legacy_root() {
    let other_ws = "fedcba9876543210fedcba9876543210";
    for variant in 0..4 {
        let f = Fixture::new();
        let key = "ab".repeat(32);
        let (id, path) = c14_interrupted(&f, &key, 2);
        let chat = f.harness.path().join("chat-v1");
        let root = path.parent().unwrap().canonicalize().unwrap();
        let forged = match variant {
            // a root outside `chat-v1` (same layout below it)
            0 => {
                let r = f
                    .harness
                    .path()
                    .join("not-chat")
                    .join("cd".repeat(32))
                    .join("worktrees-v1")
                    .join(WS);
                fs::create_dir_all(&r).unwrap();
                r.canonicalize().unwrap().join(&id)
            }
            // wrong workspace
            1 => {
                let r = chat.join(&key).join("worktrees-v1").join(other_ws);
                fs::create_dir_all(&r).unwrap();
                r.canonicalize().unwrap().join(&id)
            }
            // non-64hex key
            2 => {
                let r = chat.join("zz".repeat(32)).join("worktrees-v1").join(WS);
                fs::create_dir_all(&r).unwrap();
                r.canonicalize().unwrap().join(&id)
            }
            // journal.path != canonical(root)/id serialization
            _ => PathBuf::from(format!("{}/./{id}", root.display())),
        };
        c14_set_journal_path(&f, &id, &forged.to_string_lossy());
        c14_assert_refused(&f, &id, &path);
    }
}

#[cfg(unix)]
#[test]
fn c14_journal_root_reached_through_a_symlink_is_refused() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let root = path.parent().unwrap().canonicalize().unwrap();
    let link_key = f
        .harness
        .path()
        .join("chat-v1")
        .join("ef".repeat(32))
        .join("worktrees-v1");
    fs::create_dir_all(&link_key).unwrap();
    std::os::unix::fs::symlink(&root, link_key.join(WS)).unwrap();
    let forged = link_key.join(WS).join(&id);
    c14_set_journal_path(&f, &id, &forged.to_string_lossy());
    c14_assert_refused(&f, &id, &path);
}

/// At k=1 the readable gitdir is the binding: a journal naming another (valid)
/// legacy root is refused. (At k>=2 gitdir is gone and the journal is the
/// owner proof by SCOPE A′ 2.)
#[test]
fn c14_k1_journal_naming_another_valid_legacy_root_is_refused() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 1);
    let r = f
        .harness
        .path()
        .join("chat-v1")
        .join("cd".repeat(32))
        .join("worktrees-v1")
        .join(WS);
    fs::create_dir_all(&r).unwrap();
    let forged = r.canonicalize().unwrap().join(&id);
    c14_set_journal_path(&f, &id, &forged.to_string_lossy());
    c14_assert_refused(&f, &id, &path);
}

#[test]
fn c14_k1_gitdir_pointing_elsewhere_is_refused() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 1);
    let gitdir = f.registration(&id).join("gitdir");
    assert!(gitdir.is_file(), "k=1 leaves gitdir");
    fs::write(&gitdir, format!("{}/.git\n", f.repo.path().display())).unwrap();
    c14_assert_refused(&f, &id, &path);
}

#[test]
fn c14_target_present_dirty_partial_or_origin_unreadable_is_not_offered() {
    for variant in 0..3 {
        let f = Fixture::new();
        let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 1);
        fs::create_dir_all(&path).unwrap();
        match variant {
            0 => fs::write(path.join("dirty.txt"), "local\n").unwrap(),
            1 => {} // partial: an empty leftover directory
            _ => {
                fs::write(path.join(".git"), "gitdir: elsewhere\n").unwrap();
                let _ = fs::remove_file(f.registration(&id).join("managed-origin-head"));
            }
        }
        c14_assert_refused(&f, &id, &path);
        assert!(path.is_dir());
    }
}

#[test]
fn c14_locked_or_pinned_interrupted_entry_is_refused_without_deleting() {
    for pinned in [false, true] {
        let f = Fixture::new();
        let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
        if pinned {
            let pin = path
                .parent()
                .unwrap()
                .join(format!("{id}.native-profile-pin"));
            fs::write(pin, "pin\n").unwrap();
        } else {
            fs::write(f.registration(&id).join("locked"), "busy\n").unwrap();
        }
        let before = c14_snapshot(&f, &id, &path);
        let (candidates, digest) = f.preview();
        let c = candidates.iter().find(|c| c.id == id).expect("listed");
        let hint = if pinned { "PINNED" } else { "LOCKED" };
        assert_eq!(c.hint, Some(hint), "pinned={pinned}");
        let json = serde_json::to_value(c).unwrap();
        assert_eq!(json["hint"], hint, "pinned={pinned}");
        let out = f
            .main
            .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&id), &digest)
            .unwrap();
        assert_eq!(out[0].state, LegacyState::Failed, "pinned={pinned}");
        let want = if pinned { "WORKTREE_PINNED" } else { "LOCKED" };
        assert_eq!(out[0].code, Some(want), "pinned={pinned}");
        assert_eq!(c14_snapshot(&f, &id, &path), before, "pinned={pinned}");
    }
}

#[test]
fn c13d_hint_does_not_change_legacy_or_approval_digest() {
    // C13d: hint is summary-only. Mutating hint must leave list_digest (and thus
    // approval_digest, which hashes only list_digest + ids) unchanged.
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let pin = path
        .parent()
        .unwrap()
        .join(format!("{id}.native-profile-pin"));
    fs::write(&pin, "pin\n").unwrap();
    let (mut candidates, digest) = f.preview();
    let c = candidates.iter().find(|c| c.id == id).expect("listed");
    assert_eq!(c.hint, Some("PINNED"));
    let with_hint = legacy_digest(&candidates);
    assert_eq!(with_hint, digest);
    for c in &mut candidates {
        c.hint = None;
    }
    let without = legacy_digest(&candidates);
    assert_eq!(
        without, with_hint,
        "clearing hint must not change list_digest"
    );
    for c in &mut candidates {
        c.hint = Some("LOCKED");
    }
    assert_eq!(
        legacy_digest(&candidates),
        with_hint,
        "swapping hint must not change list_digest"
    );
    // approval_digest binds list_digest + ids only — same list_digest ⇒ same approval.
    let ids = vec![id.clone()];
    let a = crate::commands::legacy_cleanup::approval_digest(&with_hint, &ids);
    let b = crate::commands::legacy_cleanup::approval_digest(&without, &ids);
    assert_eq!(a, b);
}

#[test]
fn c14_stale_digest_and_unselected_candidates() {
    let f = Fixture::new();
    let (a, a_path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let (b, b_path) = c14_interrupted(&f, &"cd".repeat(32), 3);
    // A digest computed without the interrupted marker is stale.
    let (mut candidates, digest) = f.preview();
    assert_eq!(candidates.len(), 2);
    for c in &mut candidates {
        c.interrupted = false;
    }
    let stale = legacy_digest(&candidates);
    assert_ne!(stale, digest);
    let before = (c14_snapshot(&f, &a, &a_path), c14_snapshot(&f, &b, &b_path));
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&a), &stale);
    assert_eq!(out.unwrap_err().code(), "STALE_CONFIRMATION");
    assert_eq!(
        (c14_snapshot(&f, &a, &a_path), c14_snapshot(&f, &b, &b_path)),
        before
    );
    // Only the selected one is finished.
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&a), &digest)
        .unwrap();
    assert_eq!(out.len(), 1);
    assert_eq!(out[0].state, LegacyState::Removed);
    assert_eq!(c14_snapshot(&f, &b, &b_path), before.1);
}

#[test]
fn c14_failed_entries_are_never_resumed_automatically() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let states = f.journal().states();
    let before = c14_snapshot(&f, &id, &path);
    let (_, digest) = f.preview();
    let _ = f.preview();
    let out = f.main.cleanup_legacy(&mut f.journal(), &[], &digest);
    assert_eq!(out.unwrap_err().code(), "INVALID_ARGUMENT");
    assert_eq!(f.journal().states(), states);
    assert_eq!(c14_snapshot(&f, &id, &path), before);
}

#[test]
fn c14_managed_leftovers_k1_to_k5_stay_counted_and_owner_remove_finishes() {
    for k in 1..=5 {
        let f = Fixture::new();
        let id = f.main.create_detached().unwrap().id;
        WorktreeManager::set_delete_fail_at_for_test(Some(k));
        let out = f.main.remove_clean_owned(&id);
        WorktreeManager::set_delete_fail_at_for_test(None);
        assert!(out.is_err(), "k={k}");
        assert_eq!(f.main.slots_in_use_for_test().0, 1, "k={k}: counted");
        assert!(f.preview().0.iter().all(|c| c.id != id), "k={k}");
        f.main.remove_clean_owned(&id).unwrap();
        assert_eq!(f.main.slots_in_use_for_test().0, 0, "k={k}");
        assert!(!f.registration(&id).exists(), "k={k}");
    }
}

#[test]
fn c14_evicted_journal_entry_falls_back_to_managed_counting() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let fake = LegacyCandidate {
        id: "0".repeat(32),
        display_path: String::new(),
        head_short: String::new(),
        head: "0".repeat(40),
        clean: false,
        path: PathBuf::from("/nonexistent"),
        root: PathBuf::from("/"),
        interrupted: false,
        hint: None,
    };
    let mut j = f.journal();
    for n in 0..JOURNAL_LIMIT {
        j.record(&fake, &format!("d{n}"), LegacyState::Failed, None)
            .unwrap();
    }
    drop(j);
    assert!(f.journal().states().iter().all(|(i, ..)| i != &id));
    assert!(f.preview().0.iter().all(|c| c.id != id));
    assert_eq!(c14_snapshot(&f, &id, &path)[2], true);
    assert_eq!(f.main.slots_in_use_for_test().0, 1, "still holds a slot");
    // `worktree_remove`'s owner path still finishes it.
    f.main.remove_clean_owned(&id).unwrap();
    assert!(!f.registration(&id).exists());
    assert_eq!(f.main.slots_in_use_for_test().0, 0);
}

/// A1 C14 S1b (nit 1) / S1c soft nit 3: an interrupted entry whose id is also
/// present under the managed root (real dir or dangling symlink) is never
/// offered, cannot be forced, and nothing is deleted. `interrupted_root` only
/// continues on `ErrorKind::NotFound`; any other `symlink_metadata` error is
/// fail-closed as present (EACCES cannot be unit-mocked here without root).
#[test]
fn c14_interrupted_id_present_under_managed_root_is_not_offered() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let (candidates, _) = f.preview();
    assert!(candidates
        .iter()
        .any(|c| c.id == id && c.interrupted && c.hint.is_none()));
    let squat = f.main.managed_root.join(&id);
    fs::create_dir_all(&squat).unwrap();
    c14_assert_refused(&f, &id, &path);
    assert!(squat.is_dir());
}

/// A1 C14 S1c soft nit 3: a dangling symlink occupying `managed_root/<id>` is
/// still "present" (symlink_metadata Ok), so the interrupted id is not offered.
#[test]
fn c14_interrupted_id_dangling_symlink_under_managed_root_is_not_offered() {
    let f = Fixture::new();
    let (id, path) = c14_interrupted(&f, &"ab".repeat(32), 2);
    let (candidates, _) = f.preview();
    assert!(candidates
        .iter()
        .any(|c| c.id == id && c.interrupted && c.hint.is_none()));
    let squat = f.main.managed_root.join(&id);
    #[cfg(unix)]
    std::os::unix::fs::symlink("/no/such/c14-s1c-target", &squat).unwrap();
    #[cfg(not(unix))]
    fs::create_dir_all(&squat).unwrap();
    c14_assert_refused(&f, &id, &path);
    assert!(fs::symlink_metadata(&squat).is_ok());
}

/// A1 C14 S1b (Grok probe): forged marker + Failed journal entry pointing at a
/// live managed tree's id, with its gitdir deleted, is neither listed nor removed.
#[test]
fn c14_forged_journal_at_live_managed_tree_without_gitdir_is_refused() {
    let f = Fixture::new();
    // A real legacy root so the forged path passes the root-shape checks.
    let (_, legacy_path) = f.legacy(&"ab".repeat(32));
    let root = legacy_path.parent().unwrap().canonicalize().unwrap();
    let live = f.main.create_detached().unwrap();
    let live_path = f.main.managed_root.join(&live.id);
    fs::write(live_path.join("keep.txt"), "keep\n").unwrap();
    let forged = LegacyCandidate {
        id: live.id.clone(),
        display_path: String::new(),
        head_short: String::new(),
        head: git(&live_path, &["rev-parse", "HEAD"]),
        clean: false,
        path: root.join(&live.id),
        root: root.clone(),
        interrupted: false,
        hint: None,
    };
    f.journal()
        .record(&forged, "forged", LegacyState::Failed, None)
        .unwrap();
    let meta = f.registration(&live.id);
    fs::write(
        meta.join("managed-removing"),
        "coding-tools-managed-removing\n",
    )
    .unwrap();
    fs::remove_file(meta.join("gitdir")).unwrap();
    let before = c14_snapshot(&f, &live.id, &live_path);
    let (candidates, digest) = f.preview();
    assert!(candidates.iter().all(|c| c.id != live.id), "{candidates:?}");
    let out = f
        .main
        .cleanup_legacy(&mut f.journal(), std::slice::from_ref(&live.id), &digest);
    assert_eq!(out.unwrap_err().code(), "INVALID_ARGUMENT");
    assert_eq!(c14_snapshot(&f, &live.id, &live_path), before);
    assert!(meta.is_dir() && live_path.join("keep.txt").is_file());
}

/// G1-RE2 (ubuntu-22.04 `Fixture::new` BOUNDARY_VIOLATION): the legacy fixture's
/// Git commands must not leave a detached `git maintenance` writing
/// `.git/objects/maintenance.lock` while `WorktreeManager::new` scans it.
#[test]
fn legacy_fixture_git_commands_do_not_start_background_maintenance() {
    const CHILD: &str = "LEGACY_FIXTURE_MAINTENANCE_CHILD";
    if std::env::var_os(CHILD).is_some() {
        let f = Fixture::new();
        // Even an ambient repository preference must not re-enable it.
        git(f.repo.path(), &["config", "maintenance.auto", "true"]);
        fs::write(f.repo.path().join("README.md"), "second\n").unwrap();
        git(f.repo.path(), &["commit", "-qam", "second"]);
        return;
    }
    let root = tempfile::tempdir().unwrap();
    let trace = root.path().join("git-events.jsonl");
    let module = module_path!().split_once("::").unwrap().1;
    let output = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            &format!("{module}::legacy_fixture_git_commands_do_not_start_background_maintenance"),
            "--nocapture",
        ])
        .env(CHILD, "1")
        .env("GIT_TRACE2_EVENT", &trace)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("1 passed"));
    let events: Vec<serde_json::Value> = fs::read_to_string(trace)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert!(events
        .iter()
        .any(|event| event["event"] == "cmd_name" && event["name"] == "commit"));
    assert!(
        !events.iter().any(|event| {
            event["event"] == "child_start"
                && event["argv"]
                    .as_array()
                    .is_some_and(|args| args.iter().any(|arg| arg == "maintenance"))
        }),
        "legacy fixture Git spawned maintenance after writing repository metadata"
    );
}

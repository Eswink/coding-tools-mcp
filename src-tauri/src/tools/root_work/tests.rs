use super::*;
fn fixture() -> (Arc<tempfile::TempDir>, Arc<ToolContext>) {
    // The process-private encrypted ledger deliberately retains Busy/Restore
    // records across cold tracker reopen. Retain their workspace directories for
    // the same lifetime too: deleting them lets filesystems recycle their inode
    // identities into unrelated fixtures, correctly tripping the physical fence.
    static ROOTS: OnceLock<Mutex<Vec<Arc<tempfile::TempDir>>>> = OnceLock::new();
    let root = Arc::new(tempfile::tempdir().unwrap());
    ROOTS
        .get_or_init(Default::default)
        .lock()
        .unwrap()
        .push(root.clone());
    let workspace = root.path().join("workspace");
    let store = root.path().join("store");
    std::fs::create_dir(&workspace).unwrap();
    std::fs::create_dir(&store).unwrap();
    let ctx = Arc::new(ToolContext::for_test(workspace, store).unwrap());
    (root, ctx)
}
#[test]
fn every_context_for_the_same_root_shares_quiescence_even_with_another_harness() {
    let (root, ctx) = fixture();
    let other = root.path().join("other");
    std::fs::create_dir(&other).unwrap();
    let second = ToolContext::for_test(ctx.workspace.root().into(), other).unwrap();
    assert!(Arc::ptr_eq(
        ctx.root_work.as_ref().unwrap(),
        second.root_work.as_ref().unwrap()
    ));
    let guard = ctx.root_work.as_ref().unwrap().register().unwrap();
    assert!(second.root_work.as_ref().unwrap().restore().is_err());
    drop(guard);
    assert!(second.root_work.as_ref().unwrap().restore().is_ok());
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn lost_blocking_waiter_cannot_publish_root_quiescence() {
    let (_root, ctx) = fixture();
    let tracker = ctx.root_work.as_ref().unwrap().clone();
    let (started, observed) = tokio::sync::oneshot::channel();
    let (release, held) = std::sync::mpsc::channel();
    let future = blocking_context(ctx, move |_| {
        let _ = started.send(());
        held.recv().unwrap();
    });
    let waiter = tokio::spawn(future);
    observed.await.unwrap();
    waiter.abort();
    let _ = waiter.await;
    assert!(tracker.restore().is_err());
    release.send(()).unwrap();
    tokio::time::timeout(std::time::Duration::from_secs(2), async {
        loop {
            if let Ok(guard) = tracker.restore() {
                drop(guard);
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
}
#[test]
fn queued_registration_blocks_restore_and_cancellation_retires_without_effects() {
    let (_root, ctx) = fixture();
    let tracker = ctx.root_work.as_ref().unwrap().clone();
    let queued = blocking_context(ctx, |_| panic!("must not execute"));
    assert!(tracker.restore().is_err());
    drop(queued);
    assert!(tracker.restore().is_ok());
}
#[test]
fn running_guard_loss_persists_unknown_across_restart() {
    let (root, ctx) = fixture();
    let path = ctx.workspace.root().to_path_buf();
    let _store = root.path().join("store");
    let tracker = ctx.root_work.as_ref().unwrap().clone();
    let mut work = tracker.register().unwrap();
    work.begin().unwrap();
    drop(work);
    assert!(tracker.restore().is_err());
    drop(tracker);
    drop(ctx);
    assert!(RootWorkTracker::for_workspace(&path).is_err());
}
#[test]
fn restore_fences_new_admission_and_uncertain_mutation_survives_restart() {
    let (root, ctx) = fixture();
    let path = ctx.workspace.root().to_path_buf();
    let _store = root.path().join("store");
    let tracker = ctx.root_work.as_ref().unwrap().clone();
    let mut restore = tracker.restore().unwrap();
    assert!(tracker.register().is_err());
    restore.before_write().unwrap();
    drop(restore);
    assert!(tracker.register().is_err());
    drop(tracker);
    drop(ctx);
    assert!(RootWorkTracker::for_workspace(&path).is_err());
}
#[test]
fn clean_restore_releases_a_new_generation_and_stale_scope_cannot_fork() {
    let (_root, ctx) = fixture();
    let tracker = ctx.root_work.as_ref().unwrap();
    let mut work = tracker.register().unwrap();
    work.begin().unwrap();
    let stale = work.scope();
    work.complete();
    let mut restore = tracker.restore().unwrap();
    restore.before_write().unwrap();
    restore.commit().unwrap();
    drop(restore);
    assert!(stale.fork().is_err());
    assert!(tracker.register().is_ok());
}
#[test]
fn actual_file_dispatch_uses_root_fence_and_never_changes_root() {
    let (_root, ctx) = fixture();
    std::fs::write(ctx.workspace.root().join("a.txt"), "selected-root").unwrap();
    let out = crate::tools::call_tool(&ctx, "read_file", &json!({"path":"a.txt"}));
    assert_eq!(out["ok"], true);
    let guard = ctx.root_work.as_ref().unwrap().restore().unwrap();
    let denied = crate::tools::call_tool(&ctx, "read_file", &json!({"path":"a.txt"}));
    assert_eq!(denied["error"]["code"], "NATIVE_ROOT_UNAVAILABLE");
    drop(guard);
    assert_eq!(
        crate::tools::call_tool(&ctx, "read_file", &json!({"path":"a.txt"}))["ok"],
        true
    );
}
#[test]
fn restore_fences_overlapping_live_roots_and_durable_unknown_parent() {
    let (root, parent) = fixture();
    let child = parent.workspace.root().join("child");
    std::fs::create_dir(&child).unwrap();
    let nested = ToolContext::for_test(child.clone(), root.path().join("store")).unwrap();
    let tracker = nested.root_work.as_ref().unwrap();
    let parent_tracker = parent.root_work.as_ref().unwrap();
    let mut busy = parent_tracker.register().unwrap();
    busy.begin().unwrap();
    assert!(tracker.restore().is_err());
    busy.complete();
    let restore = tracker.restore().unwrap();
    assert!(parent_tracker.register().is_err());
    drop(restore);
    let mut uncertain = parent_tracker.register().unwrap();
    uncertain.begin().unwrap();
    drop(uncertain);
    drop(nested);
    drop(parent);
    assert!(RootWorkTracker::for_workspace(&child).is_err());
}
#[test]
fn an_idle_approved_root_replacement_is_never_adopted() {
    let (root, ctx) = fixture();
    let path = ctx.workspace.root().to_path_buf();
    std::fs::rename(&path, root.path().join("retained-original")).unwrap();
    std::fs::create_dir(&path).unwrap();
    let tracker = ctx.root_work.as_ref().unwrap();
    assert!(tracker.register().is_err());
    assert!(tracker.restore().is_err());
    assert!(RootWorkTracker::for_workspace(&path).is_err());
}
#[test]
fn exclusive_broker_scope_rejects_other_chains_and_allows_own_descendants() {
    let (_root, ctx) = fixture();
    let tracker = ctx.root_work.as_ref().unwrap();
    let mut other = tracker.register().unwrap();
    other.begin().unwrap();
    let refused = dispatch(
        &ctx,
        |scoped| json!({"exclusive":exclusive_context(scoped).is_ok()}),
    )
    .unwrap();
    assert_eq!(refused["exclusive"], false);
    other.complete();
    let result = dispatch(&ctx, |scoped| {
        let _exclusive = exclusive_context(scoped).unwrap();
        assert!(tracker.register().is_err());
        let mut child = scoped.root_scope.as_ref().unwrap().fork().unwrap();
        child.begin().unwrap();
        child.complete();
        json!({"ok":true})
    })
    .unwrap();
    assert_eq!(result["ok"], true);
    assert!(tracker.restore().is_ok());
}
#[test]
fn managed_reads_are_native_persistent_and_cannot_inherit_trusted_external_reading() {
    let (root, ctx) = fixture();
    let outside = root.path().join("outside.txt");
    std::fs::write(&outside, "outside-canary").unwrap();
    assert_eq!(
        crate::tools::call_tool(&ctx, "read_file", &json!({"path":outside}))["ok"],
        true
    );
    ctx.root_work
        .as_ref()
        .unwrap()
        .confine_managed_reads()
        .unwrap();
    let path = ctx.workspace.root().to_path_buf();
    drop(ctx);
    let new_store = root.path().join("different-harness");
    std::fs::create_dir(&new_store).unwrap();
    let managed = ToolContext::for_test(path.clone(), new_store).unwrap();
    for path in [
        outside.to_string_lossy().into_owned(),
        "../outside.txt".into(),
    ] {
        assert_eq!(
            crate::tools::call_tool(&managed, "read_file", &json!({"path":path}))["ok"],
            false
        );
    }
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(root.path(), path.join("escape")).unwrap();
        assert_eq!(
            crate::tools::call_tool(&managed, "read_file", &json!({"path":"escape/outside.txt"}))
                ["ok"],
            false
        );
    }
    std::fs::write(path.join("inside.txt"), "selected-root").unwrap();
    assert_eq!(
        crate::tools::call_tool(&managed, "read_file", &json!({"path":"inside.txt"}))["ok"],
        true
    );
}

#[test]
fn uncertain_fixture_identity_survives_cleanup_without_blocking_unrelated_roots() {
    for restoring in [false, true] {
        let (root, ctx) = fixture();
        let path = ctx.workspace.root().to_path_buf();
        let identity = RootIdentity::open(&path).unwrap().key;
        let tracker = ctx.root_work.as_ref().unwrap();
        if restoring {
            let mut restore = tracker.restore().unwrap();
            restore.before_write().unwrap();
            drop(restore);
        } else {
            let mut work = tracker.register().unwrap();
            work.begin().unwrap();
            drop(work);
        }
        drop(ctx);
        drop(root);
        // Dropping a fixture must not free its persisted physical identity for
        // reuse by another test while its unresolved ledger is still alive.
        assert_eq!(RootIdentity::open(&path).unwrap().key, identity);
        assert!(RootWorkTracker::for_workspace(&path).is_err());
        let (_other_root, other) = fixture();
        assert!(other.root_work.as_ref().unwrap().register().is_ok());
        assert!(RootWorkTracker::for_workspace(&path).is_err());
    }
}

fn native_namespace(root: &Path) -> PathBuf {
    // The native store itself may not exist yet; its process tempdir does.
    let native = crate::harness::Harness::default_root().unwrap();
    let store = native
        .parent()
        .unwrap()
        .canonicalize()
        .unwrap()
        .join(native.file_name().unwrap());
    let root = root.canonicalize().unwrap();
    store.join("native-root-work-v1").join(format!(
        "{:x}",
        Sha256::digest(root.to_string_lossy().as_bytes())
    ))
}

#[test]
fn clean_deleted_roots_are_reclaimed_and_a_new_root_is_still_admitted_after_513() {
    let mut leftovers = Vec::with_capacity(513);
    for _ in 0..513 {
        let temp = tempfile::tempdir().unwrap();
        let workspace = temp.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        let tracker = RootWorkTracker::for_workspace(&workspace)
            .expect("planting a Clean leftover must succeed");
        let namespace = native_namespace(&workspace);
        assert!(
            namespace.join("auth.json").is_file(),
            "planted leftover must have a durable Clean document"
        );
        drop(tracker);
        leftovers.push(namespace);
        drop(temp);
    }
    assert_eq!(leftovers.len(), 513);

    let fresh = tempfile::tempdir().unwrap();
    let workspace = fresh.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let tracker = RootWorkTracker::for_workspace(&workspace)
        .expect("a new root must still be admitted after 513 deleted Clean leftovers");
    assert!(
        tracker.register().is_ok(),
        "the new root must be usable, not NATIVE_ROOT_UNAVAILABLE"
    );
    for namespace in &leftovers {
        assert!(
            std::fs::symlink_metadata(namespace).is_err(),
            "deleted Clean leftovers must be reclaimed"
        );
    }
}

#[test]
fn a_non_clean_entry_whose_root_was_deleted_is_not_reclaimed() {
    let busy = tempfile::tempdir().unwrap();
    let busy_workspace = busy.path().join("workspace");
    std::fs::create_dir(&busy_workspace).unwrap();
    let tracker = RootWorkTracker::for_workspace(&busy_workspace).unwrap();
    let namespace = native_namespace(&busy_workspace);
    let mut work = tracker.register().unwrap();
    work.begin().unwrap();
    drop(work);
    drop(tracker);
    assert!(namespace.join("auth.json").is_file());

    // Create the new root while the Busy workspace still exists so the new
    // directory cannot inherit the retired inode and trip the physical fence.
    let fresh = tempfile::tempdir().unwrap();
    let workspace = fresh.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let fresh_root = workspace.canonicalize().unwrap();
    drop(busy);

    let admitted = RootWorkTracker::for_workspace(&fresh_root)
        .expect("an unrelated new root must still be admitted");
    assert!(admitted.register().is_ok());
    assert!(
        namespace.join("auth.json").is_file(),
        "a non-Clean leftover must remain in the ledger after its root is deleted"
    );
}

#[test]
fn a_clean_entry_with_a_replaced_root_identity_is_reclaimed_when_not_live() {
    let temp = tempfile::tempdir().unwrap();
    let workspace = temp.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let path = workspace.canonicalize().unwrap();
    let tracker = RootWorkTracker::for_workspace(&path).unwrap();
    let namespace = native_namespace(&path);
    let original = RootIdentity::open(&path).unwrap().key;
    drop(tracker);
    assert!(namespace.join("auth.json").is_file());

    std::fs::rename(&path, temp.path().join("retained-original")).unwrap();
    std::fs::create_dir(&path).unwrap();
    let replacement = RootIdentity::open(&path).unwrap().key;
    assert_ne!(original, replacement);

    let admitted = RootWorkTracker::for_workspace(&path)
        .expect("a Clean leftover whose identity no longer matches must be reclaimed");
    assert!(admitted.register().is_ok());
    assert!(namespace.join("auth.json").is_file());
}

fn plant_kept_clean_ledger_entry(parent: &Path) -> tempfile::TempDir {
    // Plant a well-formed Clean leftover into an isolated ledger parent, not
    // the process-shared test host store. The workspace root is kept alive so
    // the entry is not reclaimable and counts toward the remaining cap.
    let temp = tempfile::tempdir().unwrap();
    let workspace = temp.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let root = workspace.canonicalize().unwrap();
    let identity = RootIdentity::open(&root).unwrap();
    let binding = format!("{:x}", Sha256::digest(root.to_string_lossy().as_bytes()));
    let namespace = parent.join(&binding);
    let mut disk = crate::data::AuthDocument::open(&namespace).unwrap();
    disk.save(&Document {
        version: 1,
        binding,
        root,
        identity: identity.key,
        ancestors: identity.ancestors.clone(),
        epoch: 1,
        phase: Phase::Clean,
        managed_reads: false,
    })
    .unwrap();
    drop(disk);
    temp
}

#[test]
fn remaining_cap_allows_512_kept_entries_and_fail_closes_on_the_513th() {
    let parent = tempfile::tempdir().unwrap();
    let mut kept_roots = Vec::with_capacity(513);
    for _ in 0..512 {
        kept_roots.push(plant_kept_clean_ledger_entry(parent.path()));
    }
    let fresh = tempfile::tempdir().unwrap();
    let workspace = fresh.path().join("workspace");
    std::fs::create_dir(&workspace).unwrap();
    let root = workspace.canonicalize().unwrap();
    let anchor = RootIdentity::open(&root).unwrap();
    let registry = HashMap::new();
    assert!(
        persisted_conflict(parent.path(), &root, &anchor, &registry).is_ok(),
        "512 remaining non-reclaimable entries must still admit a new root"
    );

    kept_roots.push(plant_kept_clean_ledger_entry(parent.path()));
    assert!(
        persisted_conflict(parent.path(), &root, &anchor, &registry).is_err(),
        "the 513th remaining entry must fail-close"
    );
    assert_eq!(kept_roots.len(), 513);
}

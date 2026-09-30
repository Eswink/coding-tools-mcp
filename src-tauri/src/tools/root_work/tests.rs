use super::*;
fn fixture() -> (tempfile::TempDir, Arc<ToolContext>) {
    let root = tempfile::tempdir().unwrap();
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

use super::*;
use crate::{
    commands::{managed_workspace, native_owner::OwnerApproval},
    workspace::WorkspaceProfile,
};
fn isolated(name: &str) -> bool {
    if std::env::var("NATIVE_AUTHORITY_TEST_CHILD").as_deref() == Ok("1") {
        return false;
    }
    let home = tempfile::tempdir().unwrap();
    let out = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            &format!("commands::workspace_snapshots::native_tests::{name}"),
            "--test-threads=1",
        ])
        .env("NATIVE_AUTHORITY_TEST_CHILD", "1")
        .env("HOME", home.path())
        .env("XDG_DATA_HOME", home.path().join("data"))
        .env("XDG_CONFIG_HOME", home.path().join("config"))
        .env("LOCALAPPDATA", home.path().join("data"))
        .env("APPDATA", home.path().join("config"))
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
    true
}
struct Fixture {
    root: tempfile::TempDir,
    state: AppState,
    source: WorkspaceProfile,
    manager: WorktreeManager,
    target: SnapshotTarget,
    profile: WorkspaceProfile,
}
impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("source");
        std::fs::create_dir(&path).unwrap();
        let repo = git2::Repository::init(&path).unwrap();
        std::fs::write(path.join("tracked.txt"), "committed contents").unwrap();
        let mut index = repo.index().unwrap();
        index.add_path(Path::new("tracked.txt")).unwrap();
        index.write().unwrap();
        let oid = index.write_tree().unwrap();
        let tree = repo.find_tree(oid).unwrap();
        let sig = git2::Signature::now("Native fixture", "native-fixture@example.invalid").unwrap();
        repo.commit(Some("HEAD"), &sig, &sig, "fixture", &tree, &[])
            .unwrap();
        drop(tree);
        drop(index);
        drop(repo);
        std::fs::write(path.join("source-only.txt"), "not granted to managed root").unwrap();
        let state = AppState::new().unwrap();
        let source = WorkspaceProfile::new(
            path.to_string_lossy().into_owned(),
            Some("native source".into()),
        );
        state
            .with_workspaces(|store| {
                crate::app_state::bootstrap_workspace(store, &source.id)?;
                store.add(source.clone())
            })
            .unwrap();
        let harness = Harness::new(path.clone(), Harness::default_root().unwrap()).unwrap();
        let manager =
            WorktreeManager::new(&path, harness.store_root(), harness.workspace_id()).unwrap();
        let item = manager.create_detached().unwrap();
        let target = manager.snapshot_target(&item.id).unwrap();
        let digest = managed_workspace::registration_digest(&source.id, &target).unwrap();
        assert!(managed_workspace::register_approved(
            &state,
            &source.id,
            &target,
            &OwnerApproval::for_test("managed_workspace", &"0".repeat(64))
        )
        .is_err());
        let profile = managed_workspace::register_approved(
            &state,
            &source.id,
            &target,
            &OwnerApproval::for_test("managed_workspace", &digest),
        )
        .unwrap();
        Self {
            root,
            state,
            source,
            manager,
            target,
            profile,
        }
    }
}
#[tokio::test]
async fn selected_managed_root_uses_real_listener_and_never_inherits_source_authority() {
    if isolated("selected_managed_root_uses_real_listener_and_never_inherits_source_authority") {
        return;
    }
    let f = Fixture::new();
    assert_ne!(f.profile.id, f.source.id);
    assert_eq!(Path::new(&f.profile.path), f.target.root);
    assert_eq!(
        f.state
            .with_workspaces(|s| Ok(s.get(&f.source.id).unwrap().path.clone()))
            .unwrap(),
        f.source.path
    );
    assert_eq!(
        f.state
            .with_runtime(|r| Ok(r.mcp_status(&f.profile).state))
            .unwrap(),
        "stopped"
    );
    assert!(
        crate::cloud_connection::ConnectionStore::for_workspace(&f.profile.id, &f.target.root)
            .unwrap()
            .summary()
            .unwrap()
            .is_none()
    );
    crate::commands::runtime::start_mcp_service(&f.state, &f.profile.id)
        .await
        .unwrap();
    let lease = f
        .state
        .with_runtime(|r| Ok(r.mcp_context_lease(&f.profile.id).unwrap()))
        .unwrap();
    let ctx = lease.with_live(Arc::clone).unwrap();
    assert_eq!(ctx.workspace.root(), f.target.root);
    assert_eq!(
        crate::tools::call_tool(&ctx, "read_file", &json!({"path":"tracked.txt"}))["ok"],
        true
    );
    assert_eq!(
        crate::tools::call_tool(
            &ctx,
            "read_file",
            &json!({"path":f.root.path().join("source/source-only.txt")})
        )["ok"],
        false
    );
    crate::commands::runtime::stop_mcp_service(&f.state, &f.profile.id)
        .await
        .unwrap();
    assert!(!lease.is_live());
    assert_eq!(
        f.manager
            .native_profile(&f.target.worktree_id)
            .unwrap()
            .as_deref(),
        Some(f.profile.id.as_str())
    );
    assert!(f.manager.remove_clean(&f.target.worktree_id).is_err());
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn exact_native_restore_lease_waits_for_real_work_and_restores_saved_tree() {
    if isolated("exact_native_restore_lease_waits_for_real_work_and_restores_saved_tree") {
        return;
    }
    let f = Fixture::new();
    let store = store(&f.target, true).unwrap().unwrap();
    let captured = store.capture(&f.target).unwrap();
    std::fs::write(f.target.root.join("tracked.txt"), "changed").unwrap();
    let plan = store.plan_restore(&f.target, &captured.id).unwrap();
    assert!(NativeRestoreLease::acquire(
        &f.state,
        f.target.clone(),
        &plan,
        OwnerApproval::for_test("snapshot_restore", &"0".repeat(64))
    )
    .await
    .is_err());
    let ctx = Arc::new(
        crate::tools::ToolContext::for_test(
            f.target.root.clone(),
            Harness::default_root().unwrap(),
        )
        .unwrap(),
    );
    let (ready, started) = tokio::sync::oneshot::channel();
    let (release, held) = std::sync::mpsc::channel();
    let work = crate::tools::root_work::blocking_context(ctx.clone(), move |_| {
        let _ = ready.send(());
        held.recv().unwrap();
    });
    let actual = tokio::spawn(work);
    started.await.unwrap();
    assert!(NativeRestoreLease::acquire(
        &f.state,
        f.target.clone(),
        &plan,
        OwnerApproval::for_test("snapshot_restore", &plan.approval_digest)
    )
    .await
    .is_err());
    release.send(()).unwrap();
    actual.await.unwrap().unwrap();
    let _source = managed_workspace::source_lease(&f.state, &f.source.id).unwrap();
    let mut lease = NativeRestoreLease::acquire(
        &f.state,
        f.target.clone(),
        &plan,
        OwnerApproval::for_test("snapshot_restore", &plan.approval_digest),
    )
    .await
    .unwrap();
    assert_eq!(
        crate::tools::call_tool(&ctx, "read_file", &json!({"path":"tracked.txt"}))["error"]["code"],
        "NATIVE_ROOT_UNAVAILABLE"
    );
    let report = f
        .manager
        .with_lifecycle(|| Ok(store.restore(&f.target, &plan, |plan| lease.validate(plan))))
        .unwrap()
        .unwrap();
    assert!(report.retained_backup);
    lease.finish().unwrap();
    drop(lease);
    assert_eq!(
        std::fs::read_to_string(f.target.root.join("tracked.txt")).unwrap(),
        "committed contents"
    );
    assert_eq!(
        crate::tools::call_tool(&ctx, "read_file", &json!({"path":"tracked.txt"}))["ok"],
        true
    );
}

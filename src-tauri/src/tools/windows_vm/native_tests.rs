//! Two explicitly opted-in VM cases. These assertions do not qualify production.
use super::*;
use base64::{engine::general_purpose::STANDARD, Engine};
use coding_tools_cloud_agent::work::{WorkDrain, WorkGuard};
use serde_json::{json, Value};
use std::io::Write;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

static SERIAL: Mutex<()> = Mutex::new(());
static FIRST_DRAINED: AtomicBool = AtomicBool::new(false);

fn bundle() -> CiBundle {
    assert_eq!(std::env::var("CTM_VM_SESSION_NATIVE").as_deref(), Ok("1"));
    let root = PathBuf::from(std::env::var_os("CTM_VM_SESSION_ROOT").expect("owned CI root"));
    assert!(root.is_absolute());
    let manifest: Value =
        serde_json::from_slice(&std::fs::read(root.join("bundle.json")).unwrap()).unwrap();
    assert_eq!(manifest["node"], "v22.23.3");
    assert_eq!(manifest["pwsh"], "7.6.6");
    CiBundle {
        exe: root.join("trusted-code/broker.exe"),
        sha256: manifest["broker_sha256"].as_str().unwrap().into(),
        source: manifest["source"].as_str().unwrap().into(),
        root,
    }
}

fn scopes(
    root: &Path,
) -> (
    ToolContext,
    WorkDrain,
    WorkGuard,
    super::super::root_work::RootWorkGuard,
) {
    let private = root.join(format!("guards-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir(&private).unwrap();
    let workspace = private.join("synthetic-root");
    let harness = private.join("harness");
    std::fs::create_dir(&workspace).unwrap();
    std::fs::create_dir(&harness).unwrap();
    let mut ctx = ToolContext::for_test(workspace, harness).unwrap();
    let cloud = WorkDrain::new();
    let mut cloud_parent = cloud.register().unwrap();
    let mut root_parent = ctx.root_work.as_ref().unwrap().register().unwrap();
    cloud_parent.begin().unwrap();
    root_parent.begin().unwrap();
    ctx.native_work = Some(cloud_parent.scope());
    ctx.root_scope = Some(root_parent.scope());
    (ctx, cloud, cloud_parent, root_parent)
}

async fn guest_ready(observer: &CompletionObserver) -> Arc<Completion> {
    tokio::time::timeout(Duration::from_secs(240), observer.wait_for_guest())
        .await
        .expect("guest did not become ready")
        .expect("VM failed before guest result")
}

fn held(ctx: &ToolContext, cloud: &WorkDrain, observer: &CompletionObserver) {
    assert_eq!(observer.snapshot().outcome, Outcome::Pending);
    assert_eq!(cloud.status().outstanding, 1);
    assert!(!cloud.status().unconfirmed);
    assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
}

async fn drained(
    ctx: &ToolContext,
    cloud: &WorkDrain,
    observer: &CompletionObserver,
) -> Arc<Completion> {
    let result = tokio::time::timeout(Duration::from_secs(180), observer.wait())
        .await
        .expect("VM did not finish owned teardown")
        .expect("owner disappeared");
    assert_ne!(result.outcome, Outcome::Uncertain, "{:?}", result.errors);
    assert_eq!(result.state, State::Retired);
    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert_eq!(result.ownership, OwnershipStatus::Retired);
    let launch = result.launch.as_ref().expect("actual Rust launch receipt");
    assert!(launch.clean_success(), "{launch:?}");
    assert_eq!(launch.retained, launch.observed);
    assert!(launch.create_call_entered && launch.create_call_returned && launch.child_created);
    assert!(launch.create_event && launch.image_hfile_present && launch.image_handle_closed);
    assert!(launch.identity_match && launch.first_continue_succeeded);
    assert!(launch.pre_admission_empty && launch.prepare_released && launch.start_attempted);
    assert!(launch.exit_event_continued && launch.process_signaled);
    assert_eq!(launch.exit_code, Some(0));
    assert!(launch.local_handles_retired && launch.pin_retired);
    assert!(launch.native_errors.is_empty() && launch.errors.is_empty());
    assert!(launch.host_io.as_ref().expect("actual workers").clean());
    tokio::time::timeout(Duration::from_secs(5), cloud.wait())
        .await
        .unwrap();
    assert_eq!(cloud.status().outstanding, 0);
    assert!(!cloud.status().unconfirmed);
    assert!(ctx.root_work.as_ref().unwrap().restore().is_ok());
    let cleanup = result.cleanup.as_ref().expect("host cleanup receipt");
    assert!(cleanup.terminate_ok && cleanup.whole_vm_exited && cleanup.exit_ok);
    assert!(cleanup.close_ok && cleanup.guest_io_joined && cleanup.owned_data_retained);
    assert!(cleanup.errors.is_empty());
    assert!(
        !cleanup.network_denial_proven
            && !cleanup.workspace_integration
            && !cleanup.production_admission
    );
    assert!(!result.vm_id.is_empty() && !result.runtime_id.is_empty());
    assert_eq!(
        result.trace,
        vec![
            (0, Kind::Prepared),
            (1, Kind::Creating),
            (2, Kind::Running),
            (3, Kind::Guest),
            (4, Kind::Cleanup)
        ]
    );
    result
}

fn evidence(root: &Path, name: &str, source: &str, result: &Completion, lost_waiter: bool) {
    let value = json!({
        "source": source, "session": result.session, "vm_id": result.vm_id,
        "runtime_id": result.runtime_id, "outcome": format!("{:?}", result.outcome),
        "state": format!("{:?}", result.state), "guest": result.guest, "cleanup": result.cleanup,
        "validated_events": result.trace,
        "launch": result.launch, "local_ownership": result.ownership,
        "caller_wait_lost": lost_waiter, "paired_fences_held_before_teardown": true,
        "paired_fences_drained": true, "network_denial_proven": false,
        "workspace_integration": false, "production_admission": false,
        "production_launch_authority": false, "general_dll_authority": false,
        "descendant_containment_by_debugger": false, "hard_syscall_deadline": false,
    });
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(root.join(name))
        .unwrap();
    file.write_all(&serde_json::to_vec_pretty(&value).unwrap())
        .unwrap();
    file.sync_all().unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires reviewed owned Windows CI bundle and explicit native opt-in"]
async fn native_01_stock_runtimes_quarantine() {
    let _serial = SERIAL.lock().unwrap();
    assert!(
        !FIRST_DRAINED.load(Ordering::Acquire),
        "first VM already ran in this process"
    );
    let bundle = bundle();
    let root = bundle.root.clone();
    let source = bundle.source.clone();
    let (ctx, cloud, cloud_parent, root_parent) = scopes(&root);
    let session = WindowsVmSession::start(&ctx, bundle, Fixture::Runtimes).unwrap();
    let observer = session.observer();
    assert_eq!(
        cloud.status().outstanding,
        2,
        "registration must precede returned session"
    );
    cloud_parent.complete();
    root_parent.complete();
    cloud.seal();
    let ready = guest_ready(&observer).await;
    held(&ctx, &cloud, &observer);
    // Timing out drops the actual waiting future while the controller stays alive.
    assert!(
        tokio::time::timeout(Duration::from_millis(50), observer.wait())
            .await
            .is_err()
    );
    held(&ctx, &cloud, &observer);
    let guest = ready.guest.as_ref().unwrap();
    let session_root = root.join(format!("session-{}", ready.session));
    let output_before_exit = session_root.join("quarantine/returned.bin").exists();
    session.finish();
    let result = drained(&ctx, &cloud, &observer).await;
    assert_eq!(result.outcome, Outcome::Completed);
    assert!(!output_before_exit, "output precedes whole VM exit");
    assert!(!guest.child_alive);
    let mut names: Vec<_> = guest.cases.iter().map(|case| case.name.as_str()).collect();
    names.sort_unstable();
    assert_eq!(names, ["cmd", "node", "pwsh", "windows-powershell"]);
    assert!(guest
        .cases
        .iter()
        .all(|case| case.passed && case.exit_code == 23 && case.stderr.is_empty()));
    let cleanup = result.cleanup.as_ref().unwrap();
    assert_eq!(cleanup.quarantine, super::protocol::Quarantine::Written);
    let input = format!("ctm-synthetic:{}", result.session).into_bytes();
    let returned = std::fs::read(session_root.join("quarantine/returned.bin")).unwrap();
    assert_eq!(
        std::fs::read(session_root.join("synthetic-source/input.bin")).unwrap(),
        input
    );
    assert_eq!(returned, input.to_ascii_uppercase());
    assert_eq!(STANDARD.decode(&guest.data_base64).unwrap(), returned);
    assert_eq!(
        cleanup.input_sha256,
        format!("{:x}", Sha256::digest(&input))
    );
    assert_eq!(
        cleanup.output_sha256,
        format!("{:x}", Sha256::digest(&returned))
    );
    evidence(&root, "native-01.json", &source, &result, true);
    FIRST_DRAINED.store(true, Ordering::Release);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires first case drained in same serial test binary and native opt-in"]
async fn native_02_cancel_live_descendant() {
    let _serial = SERIAL.lock().unwrap();
    assert!(
        FIRST_DRAINED.load(Ordering::Acquire),
        "first VM lacked complete proof; do not boot another"
    );
    let bundle = bundle();
    let root = bundle.root.clone();
    let source = bundle.source.clone();
    let (ctx, cloud, cloud_parent, root_parent) = scopes(&root);
    let session = WindowsVmSession::start(&ctx, bundle, Fixture::LiveChild).unwrap();
    let observer = session.observer();
    cloud_parent.complete();
    root_parent.complete();
    cloud.seal();
    let ready = guest_ready(&observer).await;
    let child_was_live = ready.guest.as_ref().unwrap().child_alive;
    held(&ctx, &cloud, &observer);
    drop(session); // Losing the controller requests cancellation; the detached owner remains.
    let result = drained(&ctx, &cloud, &observer).await;
    assert!(
        child_was_live,
        "descendant must be live before cancellation"
    );
    assert_eq!(result.outcome, Outcome::Cancelled);
    let cleanup = result.cleanup.as_ref().unwrap();
    assert_eq!(cleanup.quarantine, super::protocol::Quarantine::Withheld);
    assert!(cleanup.output_sha256.is_empty());
    let session_root = root.join(format!("session-{}", result.session));
    assert!(!session_root.join("quarantine/returned.bin").exists());
    assert_eq!(
        std::fs::read(session_root.join("synthetic-source/input.bin")).unwrap(),
        format!("ctm-synthetic:{}", result.session).into_bytes()
    );
    evidence(&root, "native-02.json", &source, &result, false);
}

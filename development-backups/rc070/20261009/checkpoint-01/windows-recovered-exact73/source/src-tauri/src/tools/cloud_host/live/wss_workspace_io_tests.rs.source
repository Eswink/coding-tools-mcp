//! Future Windows CI cases through the actual public Agent/native caller.
//! No test-issued permission, fabricated source or VM/output retirement seal.
use super::*;

fn require_owned_ci_fixture() -> std::path::PathBuf {
    assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"));
    assert_eq!(std::env::var("RUNNER_OS").as_deref(), Ok("Windows"));
    assert_eq!(
        std::env::var("CTM_NATIVE_WORKSPACE_IO_FIXTURE").as_deref(),
        Ok("owned-temporary-ci")
    );
    let sha = std::env::var("GITHUB_SHA").expect("actual committed candidate SHA required");
    assert_eq!(
        crate::tools::windows_vm::input::native_source(),
        Ok(sha.as_str())
    );
    let root = std::path::PathBuf::from(std::env::var("RUNNER_TEMP").unwrap());
    assert!(root.is_absolute());
    assert!(root.is_dir());
    root.canonicalize().unwrap()
}

fn temporary_workspace(h: &Harness, runner_temp: &std::path::Path) -> std::path::PathBuf {
    assert!(h
        ._root
        .path()
        .canonicalize()
        .unwrap()
        .starts_with(runner_temp));
    assert_eq!(
        std::fs::read(h._root.path().join(".native-cloud-fixture")).unwrap(),
        b"owned"
    );
    let workspace = h._root.path().join("workspace");
    std::fs::create_dir(workspace.join("results")).unwrap();
    workspace
}

fn arguments() -> Value {
    json!({"cmd":"Get-Content native-canary.txt", "workspace_io":{
        "input":"native-canary.txt", "output_parent":"results", "output_leaf":"new-result.txt"}})
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn actual_claimed_three_scope_input_preflight_closes_without_vm_or_output() {
    let runner_temp = require_owned_ci_fixture();
    let h = Harness::start().await;
    let workspace = temporary_workspace(&h, &runner_temp);
    let before = std::fs::read(workspace.join("native-canary.txt")).unwrap();
    let scopes: Vec<String> = ["exec.run", "files.read", "files.write"]
        .into_iter()
        .map(str::to_owned)
        .collect();
    let pending = h
        .rpc(
            7800,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":scopes}),
        )
        .await;
    assert_eq!(pending["authorization"]["status"], "pending");
    let id = pending["authorization"]["id"].as_str().unwrap();
    h.host
        .tools
        .authorizer
        .decide("native-wss", id, true, &scopes)
        .unwrap();
    h.wait("eligible_a", true).await;
    let result = h.rpc(7801, "native-A", "exec_command", arguments()).await;
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "SANDBOX_REQUIRED");
    assert_eq!(
        result["input_checked"], true,
        "actual input owner was not reached"
    );
    assert_eq!(result["source_handles_closed"], true);
    assert_eq!(
        result["diagnostic_reason"],
        "WINDOWS_WORKSPACE_VM_UNAVAILABLE"
    );
    assert_eq!(result["outcome_unknown"], false);
    assert_eq!(result["vm_started"], false);
    assert_eq!(result["output_attempted"], false);
    assert_eq!(result["production_qualified"], false);
    assert!(!result.to_string().contains("native-cloud-real-file-canary"));
    assert_eq!(
        std::fs::read(workspace.join("native-canary.txt")).unwrap(),
        before
    );
    assert!(!workspace.join("results/new-result.txt").exists());
    assert_eq!(
        std::fs::read_dir(workspace.join("results"))
            .unwrap()
            .count(),
        0
    );
    assert_eq!(h.host.tools.context.execution_gate.snapshot().in_flight, 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn actual_read_only_chat_cannot_admit_explicit_workspace_io_or_create_output() {
    let runner_temp = require_owned_ci_fixture();
    let h = Harness::start().await;
    let workspace = temporary_workspace(&h, &runner_temp);
    let before = std::fs::read(workspace.join("native-canary.txt")).unwrap();
    h.approve("native-A", "eligible_a").await;
    let result = h.rpc(7810, "native-A", "exec_command", arguments()).await;
    assert_ne!(result["ok"], true);
    assert_ne!(result["input_checked"], true);
    assert!(!result.to_string().contains("native-cloud-real-file-canary"));
    assert_eq!(
        std::fs::read(workspace.join("native-canary.txt")).unwrap(),
        before
    );
    assert_eq!(
        std::fs::read_dir(workspace.join("results"))
            .unwrap()
            .count(),
        0
    );
    assert_eq!(h.host.tools.context.execution_gate.snapshot().in_flight, 0);
}

/// Future sealed Windows fixture only. The actual HostAgent claims the request,
/// the native authorizer commits three scopes, and the same owned grant/input
/// remains alive through creation-returned HCS_SYSTEM cleanup. No output issuer.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn actual_claimed_creation_owned_hcs_lifecycle_keeps_output_denied() {
    let runner_temp = require_owned_ci_fixture();
    let fixture_root = runner_temp.join("ctm-native-created-owner");
    let config_path = fixture_root.join("approved-vm-config.json");
    let meta =
        std::fs::symlink_metadata(&config_path).expect("approved owned runner fixture missing");
    assert!(meta.is_file() && !meta.file_type().is_symlink());
    assert!(meta.len() <= 65_536);
    assert_eq!(fixture_root.canonicalize().unwrap(), fixture_root);
    let config = std::fs::read_to_string(config_path).unwrap();
    let hash = std::env::var("CTM_CREATED_HCS_FIXTURE_CONFIG_SHA256")
        .expect("source-reviewed approved CI configuration hash required");
    let fixture = crate::tools::windows_vm::input::owned_run::hcs::CreationFixture::for_current_disposable_runner(config, &hash).unwrap();
    let h = Harness::start().await;
    let workspace = temporary_workspace(&h, &runner_temp);
    let before = std::fs::read(workspace.join("native-canary.txt")).unwrap();
    let scopes: Vec<String> = ["exec.run", "files.read", "files.write"]
        .into_iter()
        .map(str::to_owned)
        .collect();
    let pending = h
        .rpc(
            7820,
            "native-A",
            "request_chat_authorization",
            json!({"scopes":scopes}),
        )
        .await;
    let id = pending["authorization"]["id"].as_str().unwrap();
    h.host
        .tools
        .authorizer
        .decide("native-wss", id, true, &scopes)
        .unwrap();
    h.wait("eligible_a", true).await;
    crate::tools::windows_vm::input::owned_run::hcs::register_creation_fixture(
        h.host.tools.id,
        arguments(),
        fixture,
    )
    .unwrap();
    let result = h.rpc(7821, "native-A", "exec_command", arguments()).await;
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "SANDBOX_REQUIRED");
    assert_eq!(result["creation_attempted"], true);
    assert_eq!(result["create_completed"], true);
    assert_eq!(result["start_completed"], true);
    assert_eq!(result["whole_exit_observed"], true);
    assert_eq!(result["source_handles_closed"], true);
    assert_eq!(result["guest_process_started"], false);
    assert_eq!(result["output_attempted"], false);
    assert_eq!(result["production_qualified"], false);
    assert_eq!(
        std::fs::read(workspace.join("native-canary.txt")).unwrap(),
        before
    );
    assert_eq!(
        std::fs::read_dir(workspace.join("results"))
            .unwrap()
            .count(),
        0
    );
    assert_eq!(h.host.tools.context.execution_gate.snapshot().in_flight, 0);
}

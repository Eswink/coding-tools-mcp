//! Synthetic OAuth/local approval: six HTTP cases and one direct dispatcher case.
//! Test-only split; original eleven golden probes stay unchanged.
use super::{chat_fixture as fixture, PublicOrigin};
use serde_json::{json, Value};
use std::{path::PathBuf, time::Duration};

#[path = "linux_sandbox_deadline.rs"]
mod deadline;
#[path = "linux_sandbox_lifecycle_support.rs"]
mod support;
use support::*;

#[tokio::test]
async fn authenticated_environment_and_child_boundary_are_truthful() {
    let s = LifecycleServer::start();
    s.approve();
    let env = s.rpc("check_exec_environment", json!({})).await;
    assert_eq!(env["ok"], true, "{env}");
    assert_eq!(env["filesystem_sandbox"]["required"], true, "{env}");
    assert_eq!(
        env["filesystem_sandbox"].get("available"),
        Some(&Value::Null),
        "{env}"
    );
    assert_eq!(env["filesystem_sandbox"]["enforced"], false, "{env}");
    assert_eq!(
        env["filesystem_sandbox"]["availability_check"], "per_child_before_exec",
        "{env}"
    );
    assert_eq!(env["workspace_exec_sandbox_enforced"], false, "{env}");
    assert_eq!(env["network_allowed"], false, "{env}");
    assert_eq!(env["global_tmp_write"], "denied", "{env}");
    let builtin = s.rpc("exec_command", json!({"cmd": "pwd"})).await;
    assert_eq!(builtin["ok"], true, "{builtin}");
    assert_eq!(builtin["child_process"], false, "{builtin}");
    assert_eq!(builtin["sandbox_enforced"], false, "{builtin}");
    assert_eq!(builtin["execution_boundary"], "policy_only", "{builtin}");
    let first = s
        .rpc(
            "exec_command",
            json!({"cmd": "python3 lifecycle_probe.py inside", "timeout_ms": 8000,
                   "yield_time_ms": 1000}),
        )
        .await;
    assert_initial_boundary(&first);
    let terminal = s.collect_terminal(first).await;
    s.close().await;
    require_real_child(&terminal);
    assert_eq!(terminal["stdout"], "LIFECYCLE_CHILD_OK\n", "{terminal}");
}

#[tokio::test]
async fn authenticated_child_environment_stdin_and_temp_are_confined() {
    assert_eq!(
        std::env::var("CTM_LIFECYCLE_HOST_ONLY").as_deref(),
        Ok("synthetic-host-value"),
        "PROBE_SETUP: runner must seed the synthetic host environment"
    );
    let s = LifecycleServer::start();
    s.approve();
    let outside = s.workspace.parent().unwrap().join("outside-temp-marker");
    let input = "batch input\n中文 ✅\n";
    let first = s
        .rpc(
            "exec_command",
            json!({"cmd": format!("python3 lifecycle_probe.py environment '{}'", outside.display()),
                   "stdin": input, "timeout_ms": 8000, "yield_time_ms": 1000}),
        )
        .await;
    assert_initial_boundary(&first);
    let terminal = s.collect_terminal(first).await;
    require_real_child(&terminal);
    let output: Value = serde_json::from_str(terminal["stdout"].as_str().unwrap()).unwrap();
    assert_eq!(output["input"], input, "{output}");
    assert_eq!(output["env"]["PATH"], "/usr/bin:/bin", "{output}");
    for name in ["HOME", "TMPDIR"] {
        assert_eq!(output["env"][name], s.workspace.display().to_string());
    }
    assert_eq!(output["env"]["LANG"], "C.UTF-8", "{output}");
    assert_eq!(output["env"]["PYTHONUTF8"], "1", "{output}");
    assert!(output["env"]["CTM_LIFECYCLE_HOST_ONLY"].is_null());
    let temporary = PathBuf::from(output["temporary"].as_str().unwrap());
    assert_eq!(temporary.parent(), Some(s.workspace.as_path()));
    assert_eq!(std::fs::read(temporary).unwrap(), b"workspace-temp");
    assert_eq!(output["outside_denied"], true, "{output}");
    assert!(!outside.exists(), "outside temporary write escaped");
    assert_eq!(terminal["stdin_open"], false, "{terminal}");
    s.close().await;
}

#[tokio::test]
async fn authenticated_zero_yield_input_completes_without_replay() {
    let s = LifecycleServer::start();
    s.approve();
    let input = "zero-yield exact bytes\n中文 ✅\n";
    let first = s
        .rpc(
            "exec_command",
            json!({"cmd": "python3 lifecycle_probe.py yielded", "stdin": input,
                   "timeout_ms": 8000, "yield_time_ms": 0}),
        )
        .await;
    assert_initial_boundary(&first);
    assert_eq!(first["status"], "running", "{first}");
    let id = first["session_id"].as_str().unwrap().to_owned();
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    while !s.workspace.join("ready").exists() {
        assert!(
            tokio::time::Instant::now() < deadline,
            "PROBE_SETUP: child did not consume input/EOF"
        );
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    let running = s
        .rpc(
            "write_stdin",
            json!({"session_id": id, "chars": "", "yield_time_ms": 0}),
        )
        .await;
    assert_eq!(running["ok"], true, "{running}");
    assert_eq!(running["session_id"], id, "{running}");
    assert_eq!(running["status"], "running", "{running}");
    assert_eq!(running["stdin_open"], false, "{running}");
    std::fs::write(s.workspace.join("release"), "release").unwrap();
    let terminal = s.collect_terminal(running).await;
    require_real_child(&terminal);
    assert_eq!(terminal["session_id"], id, "{terminal}");
    let output: Value = serde_json::from_str(terminal["stdout"].as_str().unwrap()).unwrap();
    assert_eq!(output, json!({"input": input, "eof": true}));
    assert_eq!(terminal["stdin_open"], false, "{terminal}");
    let late = s
        .rpc(
            "write_stdin",
            json!({"session_id": id, "chars": "must-not-be-written", "yield_time_ms": 0}),
        )
        .await;
    assert_eq!(late["ok"], false, "{late}");
    assert_eq!(late["error"]["code"], "SESSION_CLOSED", "{late}");
    assert_eq!(
        std::fs::read_to_string(s.workspace.join("executed")).unwrap(),
        "x"
    );
    s.close().await;
}

async fn require_host_io<T>(step: impl std::future::Future<Output = std::io::Result<T>>) -> T {
    tokio::time::timeout(Duration::from_secs(2), step)
        .await
        .expect("PROBE_SETUP: host loopback deadline")
        .expect("PROBE_SETUP: host loopback operation")
}

#[tokio::test]
async fn authenticated_dangerous_mode_still_denies_network() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let s = LifecycleServer::start_with_permission_mode("dangerous");
    s.approve();
    let env = s.rpc("check_exec_environment", json!({})).await;
    assert_eq!(env["permission_mode"], "dangerous", "{env}");
    assert_eq!(env["ok"], true, "{env}");
    assert_eq!(env["network_allowed"], false, "{env}");
    assert_eq!(env["filesystem_sandbox"]["required"], true, "{env}");
    assert_eq!(env["filesystem_sandbox"]["enforced"], false, "{env}");
    assert_eq!(
        env["filesystem_sandbox"].get("available"),
        Some(&Value::Null)
    );
    let first = s
        .rpc(
            "exec_command",
            json!({"cmd": "python3 lifecycle_probe.py inside", "timeout_ms": 8000,
                   "yield_time_ms": 1000}),
        )
        .await;
    assert_initial_boundary(&first);
    let control = s.collect_terminal(first).await;
    require_real_child(&control);
    assert_eq!(control["stdout"], "LIFECYCLE_CHILD_OK\n", "{control}");

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mut host = require_host_io(tokio::net::TcpStream::connect(address)).await;
    require_host_io(host.write_all(b"HOST_CONTROL")).await;
    let (mut accepted, _) = require_host_io(listener.accept()).await;
    let mut payload = [0; 12];
    require_host_io(accepted.read_exact(&mut payload)).await;
    assert_eq!(&payload, b"HOST_CONTROL");
    drop(host);
    drop(accepted);
    let script = r#"import json, pathlib, socket, sys
root = pathlib.Path(__file__).parent
with (root / 'network-attempted').open('a') as marker:
    marker.write('x')
stage = 'socket'
result = {'denied': False}
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        stage = 'connect'
        connection.connect(('127.0.0.1', int(sys.argv[1])))
        connection.sendall(b'CHILD_MUST_NOT_ARRIVE')
except PermissionError as error:
    result = {'denied': True, 'errno': error.errno, 'stage': stage}
print(json.dumps(result), flush=True)
"#;
    std::fs::write(s.workspace.join("network_probe.py"), script).unwrap();
    let first = s
        .rpc(
            "exec_command",
            json!({"cmd": format!("python3 network_probe.py {}", address.port()),
                   "timeout_ms": 8000, "yield_time_ms": 1000}),
        )
        .await;
    assert_initial_boundary(&first);
    let terminal = s.collect_terminal(first).await;
    require_real_child(&terminal);
    assert_eq!(terminal["process_may_be_running"], false, "{terminal}");
    let output: Value = serde_json::from_str(terminal["stdout"].as_str().unwrap()).unwrap();
    assert_eq!(output["denied"], true, "{output}");
    assert_eq!(output["errno"], 1, "expected kernel EPERM: {output}");
    assert!(matches!(
        output["stage"].as_str(),
        Some("socket" | "connect")
    ));
    assert_eq!(
        std::fs::read_to_string(s.workspace.join("network-attempted")).unwrap(),
        "x"
    );
    assert!(
        tokio::time::timeout(Duration::from_secs(1), listener.accept())
            .await
            .is_err(),
        "sandboxed child connected to the host listener"
    );
    s.close().await;
}

#[test]
fn approved_primary_missing_policy_fails_closed_without_hooks() {
    use std::sync::Arc;
    let workspace = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    let mut ctx =
        crate::tools::ToolContext::for_test(workspace.path().into(), harness.path().into())
            .unwrap();
    assert!(ctx.root_work.is_ok(), "PROBE_SETUP: native root authority");
    assert!(
        ctx.linux_sandbox.as_ref().is_ok(),
        "PROBE_SETUP: valid pinned policy"
    );
    let profile = uuid::Uuid::new_v4().to_string();
    let principal = super::principal::verify(
        &fixture::token(),
        fixture::KEY,
        fixture::ORIGIN,
        &format!("{}/mcp", fixture::ORIGIN),
    )
    .unwrap();
    let request = super::chat::RemoteRequest::verified(
        &profile,
        &workspace.path().display().to_string(),
        principal,
        &json!({"openai/session": "primary-policy-owner"}),
        fixture::KEY,
    );
    request
        .service
        .attach_storage(&profile, storage.path(), harness.path())
        .unwrap();
    fixture::approve(&profile, workspace.path(), "primary-policy-owner");
    request
        .service
        .local_authority_snapshot(&request, &ctx.execution_gate)
        .expect("PROBE_SETUP: local authority must be usable");
    ctx.remote_request = Some(request);
    let hooks = ctx.policy_hooks.status();
    assert_eq!(hooks["enabled"], false);
    assert_eq!(hooks["count"], 0);
    assert_eq!(hooks["recovery_required"], false);
    let marker = workspace.path().join("primary-effect");
    std::fs::write(
        workspace.path().join("primary_probe.py"),
        "open('primary-effect', 'a').write('x')\nprint('PRIMARY_CHILD_OK', flush=True)\n",
    )
    .unwrap();
    let args = json!({"cmd": "python3 primary_probe.py", "filesystem_scope": "workspace",
                      "timeout_ms": 8000, "yield_time_ms": 8000});
    let valid_policy = ctx.linux_sandbox.clone();
    let missing_root = workspace.path().join("nonexistent-policy-root");
    assert!(!missing_root.exists());
    let invalid_policy = coding_tools_local_agent::LinuxSandbox::new(&missing_root);
    assert_eq!(
        invalid_policy.as_ref().unwrap_err().kind,
        coding_tools_local_agent::SandboxErrorKind::InvalidRoot
    );
    ctx.linux_sandbox = Arc::new(invalid_policy);
    let denied = crate::tools::call_tool(&ctx, "exec_command", &args);
    eprintln!("PRIMARY_POLICY_DENIAL: {denied}");
    assert_eq!(denied["ok"], false, "{denied}");
    assert_eq!(denied["error"]["code"], "SANDBOX_SETUP_FAILED", "{denied}");
    assert_eq!(denied["error"]["category"], "security", "{denied}");
    assert_eq!(denied["error"]["retryable"], false, "{denied}");
    assert!(denied["session_id"].is_null(), "{denied}");
    assert_ne!(denied["sandbox_enforced"], true, "{denied}");
    assert_ne!(denied["command_ok"], true, "{denied}");
    assert!(
        !marker.exists(),
        "missing policy allowed a primary side effect"
    );
    assert_eq!(ctx.policy_hooks.status(), hooks);

    ctx.linux_sandbox = valid_policy;
    let control = crate::tools::call_tool(&ctx, "exec_command", &args);
    eprintln!("PRIMARY_POLICY_CONTROL: {control}");
    assert_initial_boundary(&control);
    require_real_child(&control);
    assert_eq!(control["stdout"], "PRIMARY_CHILD_OK\n", "{control}");
    assert_eq!(control["process_may_be_running"], false, "{control}");
    assert_eq!(std::fs::read_to_string(marker).unwrap(), "x");
    assert_eq!(ctx.policy_hooks.status(), hooks);
    super::chat::service().revoke(&profile, None);
}

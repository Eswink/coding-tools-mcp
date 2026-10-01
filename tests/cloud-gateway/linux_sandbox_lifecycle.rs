//! Synthetic OAuth/local approval over the real MCP listener, not live ChatGPT proof.
//! Injected by the sibling runner only. Original eleven golden probes stay unchanged.
use super::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};
use serde_json::{json, Value};
use std::{net::TcpListener, path::PathBuf, time::Duration};

const SCRIPT: &str = r#"import json, os, pathlib, sys, tempfile, time
root = pathlib.Path(__file__).parent
mode = sys.argv[1]
if mode == 'inside':
    print('LIFECYCLE_CHILD_OK', flush=True)
elif mode == 'environment':
    data = sys.stdin.read()
    fd, temporary = tempfile.mkstemp(prefix='lifecycle-')
    os.write(fd, b'workspace-temp')
    os.close(fd)
    denied = False
    try:
        pathlib.Path(sys.argv[2]).write_text('must-not-exist')
    except PermissionError:
        denied = True
    keys = ['PATH', 'HOME', 'TMPDIR', 'LANG', 'PYTHONUTF8', 'CTM_LIFECYCLE_HOST_ONLY']
    print(json.dumps({'input': data, 'env': {k: os.environ.get(k) for k in keys},
                      'temporary': temporary, 'outside_denied': denied}), flush=True)
elif mode == 'yielded':
    data = sys.stdin.read()
    with (root / 'executed').open('a') as f:
        f.write('x')
    (root / 'ready').write_text('ready')
    until = time.monotonic() + 8
    while not (root / 'release').exists():
        if time.monotonic() >= until:
            raise TimeoutError('fixture release deadline exceeded')
        time.sleep(0.01)
    print(json.dumps({'input': data, 'eof': True}), flush=True)
else:
    raise ValueError('unknown lifecycle fixture mode')
"#;

struct LifecycleServer {
    _root: tempfile::TempDir,
    workspace: PathBuf,
    profile: String,
    url: String,
    client: reqwest::Client,
    stop: Option<crate::mcp::ShutdownSender>,
    task: Option<tauri::async_runtime::JoinHandle<()>>,
}

impl LifecycleServer {
    fn start() -> Self {
        let root = tempfile::tempdir().expect("PROBE_SETUP: fixture directory");
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        std::fs::write(workspace.join("lifecycle_probe.py"), SCRIPT).unwrap();
        let profile = uuid::Uuid::new_v4().to_string();
        let socket = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = socket.local_addr().unwrap().port();
        let (stop, task, _gate) = crate::mcp::spawn_listener_from_bound(
            socket,
            workspace.clone(),
            profile.clone(),
            AuthConfig {
                oauth_client_id: "test-client".into(),
                ..Default::default()
            },
            PublicOrigin::managed(fixture::ORIGIN).unwrap(),
            None,
            Some("synthetic-password".into()),
            Some(fixture::KEY.into()),
            RuntimeConfig {
                permission_mode: "safe".into(),
                ..Default::default()
            },
        )
        .expect("PROBE_SETUP: actual listener startup");
        Self {
            _root: root,
            workspace,
            profile,
            url: format!("http://127.0.0.1:{port}/mcp"),
            client: fixture::client(),
            stop: Some(stop),
            task: Some(task),
        }
    }

    fn approve(&self) {
        fixture::approve(&self.profile, &self.workspace, "lifecycle-owner");
    }

    async fn rpc(&self, name: &str, args: Value) -> Value {
        let response = self
            .client
            .post(&self.url)
            .json(&fixture::request(name, args, "lifecycle-owner"))
            .send()
            .await
            .expect("PROBE_SETUP: actual HTTP request");
        assert_eq!(response.status(), 200, "PROBE_SETUP: HTTP status");
        assert!(response.headers().get("www-authenticate").is_none());
        let body: Value = response.json().await.expect("PROBE_SETUP: JSON body");
        let out = &body["result"]["structuredContent"];
        assert!(out.is_object(), "PROBE_SETUP: tool envelope: {body}");
        eprintln!("LIFECYCLE_RPC {name}: {out}");
        out.clone()
    }

    async fn collect_terminal(&self, initial: Value) -> Value {
        let mut raw = initial;
        let id = raw["session_id"].as_str().map(str::to_owned);
        let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
        loop {
            assert_eq!(raw["ok"], true, "PROBE_SETUP: command/snapshot: {raw}");
            if raw["status"] == "exited"
                && (raw["exit_code"] != 0
                    || raw["stdout"].as_str().is_some_and(|s| s.ends_with('\n')))
            {
                return raw;
            }
            assert!(
                tokio::time::Instant::now() < deadline,
                "PROBE_SETUP: child did not complete: {raw}"
            );
            let id = id.as_ref().expect("PROBE_SETUP: retained session identity");
            raw = self
                .rpc(
                    "write_stdin",
                    json!({"session_id": id, "chars": "", "yield_time_ms": 20}),
                )
                .await;
            // Keep the unmodified wire response. Never graft initial metadata here.
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }

    async fn close(mut self) {
        super::chat::service().revoke(&self.profile, None);
        let old = std::mem::replace(&mut self.client, reqwest::Client::new());
        drop(old);
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(task) = self.task.take() {
            tokio::time::timeout(Duration::from_secs(5), task)
                .await
                .expect("PROBE_SETUP: listener shutdown deadline")
                .unwrap();
        }
    }
}

impl Drop for LifecycleServer {
    fn drop(&mut self) {
        let _ = std::fs::write(self.workspace.join("release"), "cleanup");
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        // The yielded fixture also self-exits after eight seconds without the host runtime.
    }
}

fn assert_initial_boundary(out: &Value) {
    assert_eq!(out["ok"], true, "PROBE_SETUP: child admission: {out}");
    assert_eq!(out["child_process"], true, "{out}");
    assert_eq!(out["sandbox_required"], true, "{out}");
    assert_eq!(out["sandbox_enforced"], true, "{out}");
    assert_eq!(out["execution_boundary"], "landlock_seccomp", "{out}");
}

fn require_real_child(out: &Value) {
    assert_eq!(out["ok"], true, "PROBE_SETUP: child result: {out}");
    assert_eq!(out["command_ok"], true, "PROBE_SETUP: child failed: {out}");
    assert_eq!(out["exit_code"], 0, "PROBE_SETUP: child exit: {out}");
    assert_eq!(out["termination_reason"], "exited", "{out}");
}

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
        env["filesystem_sandbox"]["availability_check"],
        "per_child_before_exec",
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

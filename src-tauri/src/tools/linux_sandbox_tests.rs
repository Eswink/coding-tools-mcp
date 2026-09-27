//! Actual authenticated desktop dispatch regressions, not library-only fixtures.
use crate::auth::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};
use serde_json::{json, Value};
use std::{
    net::TcpListener,
    path::PathBuf,
    time::{Duration, Instant},
};

struct Desktop {
    root: tempfile::TempDir,
    workspace: PathBuf,
    profile: String,
    client: reqwest::Client,
    url: String,
    stop: Option<crate::mcp::ShutdownSender>,
    task: Option<tauri::async_runtime::JoinHandle<()>>,
}
impl Desktop {
    fn open() -> Self {
        let root = tempfile::tempdir().unwrap();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        let profile = uuid::Uuid::new_v4().to_string();
        let socket = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = socket.local_addr().unwrap().port();
        let (stop, task, _) = crate::mcp::spawn_listener_from_bound(
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
        .unwrap();
        fixture::approve(&profile, &workspace, "sandbox-owner");
        Self {
            root,
            workspace,
            profile,
            client: fixture::client(),
            url: format!("http://127.0.0.1:{port}/mcp"),
            stop: Some(stop),
            task: Some(task),
        }
    }
    fn script(&self, name: &str, content: &str) {
        std::fs::write(self.workspace.join(name), content).unwrap();
    }
    async fn tool(&self, name: &str, args: Value) -> Value {
        let response = self
            .client
            .post(&self.url)
            .json(&fixture::request(name, args, "sandbox-owner"))
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), 200);
        let body: Value = response.json().await.unwrap();
        assert!(body["result"]["structuredContent"].is_object(), "{body}");
        body["result"]["structuredContent"].clone()
    }
    async fn command(&self, script: &str, extra: Value) -> Value {
        let mut args = json!({
            "cmd": format!("python3 {script}"), "timeout_ms": 5000,
            "yield_time_ms": 5000, "max_output_bytes": 8192,
        });
        for (name, value) in extra.as_object().unwrap() {
            args[name] = value.clone();
        }
        self.tool("exec_command", args).await
    }
    async fn terminal(&self, id: &str) -> Value {
        let end = Instant::now() + Duration::from_secs(8);
        loop {
            let result = self.tool("get_exec_task", json!({"job_id": id})).await;
            if result["terminal"] == true {
                return result;
            }
            assert!(Instant::now() < end, "{result}");
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }
    async fn close(mut self) {
        let profile = self.profile.clone();
        tokio::task::spawn_blocking(move || {
            crate::auth::chat::service().cancel_local_sessions(&profile);
        })
        .await
        .unwrap();
        let old = std::mem::replace(&mut self.client, reqwest::Client::new());
        drop(old);
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(task) = self.task.take() {
            tokio::time::timeout(Duration::from_secs(8), task)
                .await
                .unwrap()
                .unwrap();
        }
        crate::auth::chat::service().revoke(&self.profile, None);
    }
}
impl Drop for Desktop {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
    }
}
fn isolated_success(result: &Value) {
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(result["exit_code"], 0, "{result}");
    assert_eq!(result["sandbox_required"], true, "{result}");
    assert_eq!(result["sandbox_enforced"], true, "{result}");
    assert_eq!(result["execution_boundary"], "linux_landlock_seccomp");
}

#[tokio::test]
async fn actual_desktop_child_environment_and_stdin_are_bounded() {
    let s = Desktop::open();
    s.script(
        "env_probe.py",
        r#"import os, sys, tempfile
assert set(os.environ).issubset({'PATH', 'HOME', 'LANG', 'TMPDIR', 'LC_CTYPE'})
assert os.environ['PATH'] == '/usr/bin:/bin'
assert os.environ['TMPDIR'] == '.'
assert sys.stdin.read() == 'bounded-input'
with tempfile.TemporaryFile() as f:
    f.write(b'workspace-temporary-file')
print('ENV_STDIN_TMP_OK')
"#,
    );
    let result = s
        .command("env_probe.py", json!({"stdin": "bounded-input"}))
        .await;
    s.close().await;
    isolated_success(&result);
    assert!(result["stdout"]
        .as_str()
        .unwrap()
        .contains("ENV_STDIN_TMP_OK"));
}

#[tokio::test]
async fn actual_desktop_retains_approved_directory_after_path_replacement() {
    let s = Desktop::open();
    s.script("identity.py", "print('ORIGINAL_APPROVED_DIRECTORY')\n");
    let original = s.root.path().join("original");
    std::fs::rename(&s.workspace, &original).unwrap();
    std::fs::create_dir(&s.workspace).unwrap();
    s.script("identity.py", "print('REPLACEMENT_DIRECTORY')\n");
    let result = s.command("identity.py", json!({})).await;
    s.close().await;
    isolated_success(&result);
    assert_eq!(
        result["stdout"].as_str().unwrap().trim(),
        "ORIGINAL_APPROVED_DIRECTORY"
    );
}

#[tokio::test]
async fn actual_desktop_async_cancel_preserves_no_replay_and_sandbox_metadata() {
    let s = Desktop::open();
    s.script(
        "async_probe.py",
        r#"import pathlib, time
with pathlib.Path('executed').open('a') as f:
    f.write('x')
print('ASYNC_STARTED', flush=True)
time.sleep(60)
"#,
    );
    let args = json!({"cmd": "python3 async_probe.py", "request_id": "same-mutation",
        "timeout_ms": 15000});
    let submitted = s.tool("start_exec_task", args.clone()).await;
    assert_eq!(submitted["ok"], true, "{submitted}");
    let id = submitted["job_id"].as_str().unwrap().to_owned();
    let deadline = Instant::now() + Duration::from_secs(8);
    while !s.workspace.join("executed").exists() {
        assert!(Instant::now() < deadline, "background child never executed");
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    let duplicate = s.tool("start_exec_task", args).await;
    assert_eq!(duplicate["job_id"], id);
    assert_eq!(duplicate["deduplicated"], true);
    let cancelled = s.tool("cancel_exec_task", json!({"job_id": id})).await;
    assert_eq!(cancelled["ok"], true, "{cancelled}");
    let ended = s.terminal(&id).await;
    assert_eq!(ended["status"], "cancelled", "{ended}");
    assert_eq!(ended["result"]["sandbox_enforced"], true, "{ended}");
    assert_eq!(
        ended["result"]["execution_boundary"],
        "linux_landlock_seccomp"
    );
    let count = std::fs::read_to_string(s.workspace.join("executed")).unwrap();
    s.close().await;
    assert_eq!(count, "x", "the duplicate mutation ran twice");
}

#[tokio::test]
async fn actual_desktop_timeout_terminates_descendants_and_reports_isolation() {
    let s = Desktop::open();
    s.script(
        "child.py",
        "import time,pathlib\ntime.sleep(2)\npathlib.Path('escaped-child').write_text('bad')\n",
    );
    s.script(
        "parent.py",
        r#"import subprocess, sys, time
subprocess.Popen([sys.executable, 'child.py'])
print('PARENT_STARTED', flush=True)
time.sleep(60)
"#,
    );
    let result = s
        .command(
            "parent.py",
            json!({"timeout_ms": 200, "yield_time_ms": 3000}),
        )
        .await;
    assert_eq!(result["command_ok"], false, "{result}");
    assert_eq!(result["sandbox_enforced"], true, "{result}");
    assert_eq!(result["termination_reason"], "timeout", "{result}");
    tokio::time::sleep(Duration::from_millis(2300)).await;
    let escaped = s.workspace.join("escaped-child").exists();
    s.close().await;
    assert!(!escaped, "a descendant survived group cancellation");
}

#[tokio::test]
async fn actual_desktop_model_environment_is_rejected_without_child_execution() {
    let s = Desktop::open();
    s.script(
        "forbidden.py",
        "import pathlib\npathlib.Path('executed').touch()\n",
    );
    let result = s
        .command("forbidden.py", json!({"env": {"LD_PRELOAD": "pretend"}}))
        .await;
    let ran = s.workspace.join("executed").exists();
    s.close().await;
    assert_eq!(result["ok"], false, "{result}");
    assert!(!ran);
}

#[tokio::test]
async fn actual_desktop_environment_view_does_not_forge_a_kernel_probe() {
    let s = Desktop::open();
    let result = s.tool("check_exec_environment", json!({})).await;
    let diagnostic = s
        .tool("exec_command", json!({"cmd": "echo native-only"}))
        .await;
    s.close().await;
    assert_eq!(result["workspace_exec_sandbox_required"], true, "{result}");
    assert_eq!(result["filesystem_sandbox"]["enforced"], false);
    assert_eq!(
        result["filesystem_sandbox"]["status"],
        "checked_at_child_start"
    );
    assert!(result["filesystem_sandbox"]["available"].is_null());
    assert_eq!(result["network_allowed"], false);
    assert_eq!(diagnostic["child_process"], false);
    assert_eq!(diagnostic["sandbox_enforced"], false);
}

#[tokio::test]
async fn actual_desktop_yielded_session_keeps_isolation_metadata() {
    let s = Desktop::open();
    s.script(
        "yield_probe.py",
        "import time\nprint('SESSION_OK',flush=True)\ntime.sleep(0.2)\n",
    );
    let first = s
        .command("yield_probe.py", json!({"yield_time_ms": 0}))
        .await;
    assert_eq!(first["sandbox_enforced"], true, "{first}");
    let id = first["session_id"].as_str().unwrap();
    let next = s
        .tool(
            "write_stdin",
            json!({"session_id": id, "chars": "", "yield_time_ms": 500}),
        )
        .await;
    s.close().await;
    assert_eq!(next["sandbox_required"], true, "{next}");
    assert_eq!(next["sandbox_enforced"], true, "{next}");
    assert_eq!(next["execution_boundary"], "linux_landlock_seccomp");
}

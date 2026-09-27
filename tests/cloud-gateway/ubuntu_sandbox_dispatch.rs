//! Synthetic authenticated MCP dispatch probes, injected only by the diagnostic CI.
//! These acceptance tests are expected to be RED before mandatory host integration.
//! All data belongs to a temporary fixture; networking is IPv4 loopback only.
use super::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};
use serde_json::{json, Value};
use std::{net::TcpListener, path::PathBuf, sync::Arc, time::Duration};

const SCRIPT: &str = r#"import pathlib, socket, sys
root = pathlib.Path(__file__).parent
mode = sys.argv[1]
try:
    if mode == 'inside':
        with (root / 'executed').open('a') as f:
            f.write('x')
        print('INSIDE_OK')
    elif mode == 'read':
        print((root.parent / 'outside.txt').read_text())
    elif mode == 'link':
        print((root / 'escape').read_text())
    elif mode == 'write':
        (root.parent / 'written.txt').write_text('SYNTHETIC_OUTSIDE_WRITE')
        print('OUTSIDE_WRITE')
    elif mode == 'tcp':
        with socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=1) as s:
            s.sendall(b'SYNTHETIC_LOOPBACK')
        print('LOOPBACK_CONNECTED')
    else:
        raise ValueError('unknown fixture mode')
except PermissionError:
    print('KERNEL_DENIED')
"#;

struct Server {
    _root: tempfile::TempDir,
    workspace: PathBuf,
    profile: String,
    url: String,
    client: reqwest::Client,
    gate: Arc<crate::runtime::WorkspaceExecutionGate>,
    stop: Option<crate::mcp::ShutdownSender>,
    task: Option<tauri::async_runtime::JoinHandle<()>>,
}
impl Server {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        std::fs::write(root.path().join("outside.txt"), "SYNTHETIC_OUTSIDE_READ").unwrap();
        std::fs::write(workspace.join("dispatch_probe.py"), SCRIPT).unwrap();
        std::os::unix::fs::symlink("../outside.txt", workspace.join("escape")).unwrap();
        let profile = uuid::Uuid::new_v4().to_string();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let (stop, task, gate) = crate::mcp::spawn_listener_from_bound(
            listener, workspace.clone(), profile.clone(),
            AuthConfig { oauth_client_id: "test-client".into(), ..Default::default() },
            PublicOrigin::managed(fixture::ORIGIN).unwrap(), None,
            Some("synthetic-password".into()), Some(fixture::KEY.into()),
            RuntimeConfig { permission_mode: "safe".into(), ..Default::default() },
        ).unwrap();
        Self { _root: root, workspace, profile, url: format!("http://127.0.0.1:{port}/mcp"),
            client: fixture::client(), gate, stop: Some(stop), task: Some(task) }
    }
    fn approve(&self) { fixture::approve(&self.profile, &self.workspace, "owner"); }
    async fn rpc(&self, chat: &str, name: &str, args: Value) -> Value {
        let response = self.client.post(&self.url)
            .json(&fixture::request(name, args, chat)).send().await.unwrap();
        assert_eq!(response.status(), 200, "PROBE_SETUP: HTTP failed");
        assert!(response.headers().get("www-authenticate").is_none());
        let body: Value = response.json().await.unwrap();
        assert!(body["result"]["structuredContent"].is_object(), "PROBE_SETUP: bad RPC result");
        body["result"]["structuredContent"].clone()
    }
    async fn command(&self, mode: &str, extra: Value) -> Value {
        let mut args = json!({"cmd": format!("python3 dispatch_probe.py {mode}"),
            "filesystem_scope": "workspace", "timeout_ms": 3000,
            "yield_time_ms": 1000, "max_output_bytes": 4096});
        for (key, value) in extra.as_object().unwrap() { args[key] = value.clone(); }
        let mut out = self.rpc("owner", "exec_command", args).await;
        // Ordinary execution can yield before exit. Fetch bounded session output,
        // but retain the original sandbox metadata for the omission assertion.
        if let Some(id) = out["session_id"].as_str().map(str::to_owned) {
            if out["exit_code"].is_null() {
                let end = std::time::Instant::now() + Duration::from_secs(5);
                loop {
                    let next = self.rpc("owner", "read_output", json!({"session_id":id,"max_output_bytes":4096})).await;
                    assert!(next["ok"] == true, "PROBE_SETUP: cannot read session output: {next}");
                    if !next["exit_code"].is_null() {
                        for key in ["stdout", "stderr", "exit_code", "command_ok"] {
                            if !next[key].is_null() { out[key] = next[key].clone(); }
                        }
                        break;
                    }
                    assert!(std::time::Instant::now() < end, "PROBE_SETUP: child did not finish");
                    tokio::time::sleep(Duration::from_millis(20)).await;
                }
            }
        }
        out
    }
    async fn close(mut self) {
        super::chat::service().revoke(&self.profile, None);
        let old_client = std::mem::replace(&mut self.client, reqwest::Client::new());
        drop(old_client);
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
        if let Some(task) = self.task.take() {
            tokio::time::timeout(Duration::from_secs(5), task).await
                .expect("PROBE_SETUP: listener shutdown timed out").unwrap();
        }
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() { let _ = stop.send(()); }
    }
}
fn completed(out: &Value) {
    assert_eq!(out["ok"], true, "PROBE_SETUP: command rejected before kernel probe: {out}");
    assert_eq!(out["exit_code"], 0, "PROBE_SETUP: fixture failed to execute: {out}");
}
fn setup_denied(out: &Value) -> bool {
    matches!(out["error"]["code"].as_str(), Some("SANDBOX_REQUIRED" | "SANDBOX_SETUP_FAILED"))
}

#[tokio::test]
async fn control_unapproved_chat_cannot_spawn() {
    let s = Server::new();
    let out = s.command("inside", json!({})).await;
    let spawned = s.workspace.join("executed").exists();
    s.close().await;
    assert_eq!(out["ok"], false);
    assert!(!spawned, "unapproved caller spawned a child");
    assert!(out["session_id"].is_null());
}
#[tokio::test]
async fn control_approved_workspace_script_executes() {
    let s = Server::new(); s.approve();
    let out = s.command("inside", json!({})).await;
    let marker = std::fs::read_to_string(s.workspace.join("executed")).unwrap();
    s.close().await; completed(&out);
    assert!(out["stdout"].as_str().unwrap().contains("INSIDE_OK"));
    assert_eq!(marker, "x");
}
#[tokio::test]
async fn control_pause_and_revoke_block_new_children() {
    let s = Server::new(); s.approve(); s.gate.pause().unwrap();
    let paused = s.command("inside", json!({})).await;
    assert_eq!(paused["ok"], false);
    assert!(!s.workspace.join("executed").exists());
    s.gate.resume().unwrap();
    let allowed = s.command("inside", json!({})).await; completed(&allowed);
    super::chat::service().revoke(&s.profile, None);
    let revoked = s.command("inside", json!({})).await;
    let marker = std::fs::read_to_string(s.workspace.join("executed")).unwrap();
    s.close().await;
    assert_eq!(revoked["ok"], false); assert_eq!(marker, "x");
}
#[tokio::test]
async fn control_foreign_chat_cannot_use_approved_workspace() {
    let s = Server::new(); s.approve();
    let out = s.rpc("foreign", "exec_command", json!({"cmd":"python3 dispatch_probe.py inside"})).await;
    let spawned = s.workspace.join("executed").exists(); s.close().await;
    assert_eq!(out["ok"], false); assert!(!spawned);
}
#[tokio::test]
async fn acceptance_omitted_policy_never_spawns_unsandboxed() {
    let s = Server::new(); s.approve();
    let out = s.command("inside", json!({})).await; s.close().await;
    if setup_denied(&out) { return; } completed(&out);
    assert_eq!(out["sandbox_enforced"], true, "SANDBOX_GAP_OMITTED_POLICY");
}
#[tokio::test]
async fn acceptance_workspace_read_cannot_escape() {
    let s = Server::new(); s.approve();
    let out = s.command("read", json!({})).await; s.close().await;
    if setup_denied(&out) { return; } completed(&out);
    assert_eq!(out["stdout"].as_str().unwrap().trim(), "KERNEL_DENIED", "SANDBOX_GAP_FS_READ");
}
#[tokio::test]
async fn acceptance_symlink_cannot_escape() {
    let s = Server::new(); s.approve();
    let out = s.command("link", json!({})).await; s.close().await;
    if setup_denied(&out) { return; } completed(&out);
    assert_eq!(out["stdout"].as_str().unwrap().trim(), "KERNEL_DENIED", "SANDBOX_GAP_SYMLINK");
}
#[tokio::test]
async fn acceptance_workspace_write_cannot_escape() {
    let s = Server::new(); s.approve();
    let out = s.command("write", json!({})).await;
    let escaped = s.workspace.parent().unwrap().join("written.txt").exists();
    s.close().await;
    if !setup_denied(&out) { completed(&out); }
    assert!(!escaped, "SANDBOX_GAP_FS_WRITE");
}
#[tokio::test]
async fn acceptance_safe_mode_denies_loopback_network() {
    let socket = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = socket.local_addr().unwrap().port(); socket.set_nonblocking(true).unwrap();
    let listener = tokio::net::TcpListener::from_std(socket).unwrap();
    let receiver = tokio::spawn(async move {
        matches!(tokio::time::timeout(Duration::from_secs(5), listener.accept()).await, Ok(Ok(_)))
    });
    let s = Server::new(); s.approve();
    let out = s.command(&format!("tcp {port}"), json!({})).await;
    let connected = receiver.await.unwrap(); s.close().await;
    if !setup_denied(&out) { completed(&out); }
    assert!(!connected, "SANDBOX_GAP_NETWORK");
}
#[tokio::test]
async fn acceptance_model_cannot_disable_sandbox() {
    let s = Server::new(); s.approve();
    let out = s.command("inside", json!({"sandbox":false,"disable_sandbox":true})).await;
    let spawned = s.workspace.join("executed").exists();
    s.close().await;
    if setup_denied(&out) {
        assert!(!spawned, "sandbox setup denial spawned a child");
        return;
    }
    // Known argument-validation rejection is acceptable only before any spawn.
    if out["ok"] == false {
        assert!(matches!(out["error"]["code"].as_str(),
            Some("INVALID_ARGUMENT" | "INVALID_PARAMS" | "VALIDATION_ERROR")),
            "PROBE_SETUP: unrelated rejection: {out}");
        assert!(!spawned, "invalid model parameters spawned a child");
        return;
    }
    completed(&out);
    assert_eq!(out["sandbox_enforced"], true, "SANDBOX_GAP_MODEL_SWITCH");
}
#[tokio::test]
async fn acceptance_tty_flag_cannot_bypass_isolation() {
    let s = Server::new(); s.approve();
    let out = s.command("read", json!({"tty":true})).await; s.close().await;
    if setup_denied(&out) { return; } completed(&out);
    assert_eq!(out["stdout"].as_str().unwrap().trim(), "KERNEL_DENIED", "SANDBOX_GAP_TTY");
}

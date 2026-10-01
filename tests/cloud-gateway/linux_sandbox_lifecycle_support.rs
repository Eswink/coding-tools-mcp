//! Shared test-only HTTP fixture. Injected only by the lifecycle runner.
use super::{fixture, PublicOrigin};
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

pub(super) struct LifecycleServer {
    _root: tempfile::TempDir,
    pub(super) workspace: PathBuf,
    profile: String,
    url: String,
    client: reqwest::Client,
    stop: Option<crate::mcp::ShutdownSender>,
    task: Option<tauri::async_runtime::JoinHandle<()>>,
}

impl LifecycleServer {
    pub(super) fn start() -> Self {
        Self::start_with_permission_mode("safe")
    }

    pub(super) fn start_with_permission_mode(permission_mode: &str) -> Self {
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
                permission_mode: permission_mode.into(),
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

    pub(super) fn approve(&self) {
        fixture::approve(&self.profile, &self.workspace, "lifecycle-owner");
    }

    pub(super) async fn rpc(&self, name: &str, args: Value) -> Value {
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

    pub(super) async fn collect_terminal(&self, initial: Value) -> Value {
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

    pub(super) async fn close(mut self) {
        crate::auth::chat::service().revoke(&self.profile, None);
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

pub(super) fn assert_initial_boundary(out: &Value) {
    assert_eq!(out["ok"], true, "PROBE_SETUP: child admission: {out}");
    assert_eq!(out["child_process"], true, "{out}");
    assert_eq!(out["sandbox_required"], true, "{out}");
    assert_eq!(out["sandbox_enforced"], true, "{out}");
    assert_eq!(out["execution_boundary"], "landlock_seccomp", "{out}");
}

pub(super) fn require_real_child(out: &Value) {
    assert_eq!(out["ok"], true, "PROBE_SETUP: child result: {out}");
    assert_eq!(out["command_ok"], true, "PROBE_SETUP: child failed: {out}");
    assert_eq!(out["exit_code"], 0, "PROBE_SETUP: child exit: {out}");
    assert_eq!(out["termination_reason"], "exited", "{out}");
}

#[derive(Clone, Debug)]
pub(super) struct Identity {
    pub(super) pid: u64,
    pub(super) start: u64,
    pub(super) ppid: u64,
    pub(super) pgid: u64,
    pub(super) state: String,
}

pub(super) fn process(pid: u64) -> std::io::Result<Option<Identity>> {
    let text = match std::fs::read_to_string(format!("/proc/{pid}/stat")) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    let invalid = || std::io::Error::other("invalid process identity");
    let fields: Vec<_> = text
        .rsplit_once(") ")
        .ok_or_else(invalid)?
        .1
        .split_whitespace()
        .collect();
    let number = |index: usize| {
        fields
            .get(index)
            .ok_or_else(invalid)?
            .parse::<u64>()
            .map_err(|_| invalid())
    };
    Ok(Some(Identity {
        pid,
        start: number(19)?,
        ppid: number(1)?,
        pgid: number(2)?,
        state: fields.first().ok_or_else(invalid)?.to_string(),
    }))
}

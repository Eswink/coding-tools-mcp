//! Real authenticated HTTP deadline/kill proof, including inherited descendants.
use super::{
    assert_initial_boundary, require_real_child,
    support::{process, Identity},
    LifecycleServer,
};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tokio::time::{sleep, timeout_at, Instant};

const TREE: &str = r#"import json, os, pathlib, socket, subprocess, sys, time
root = pathlib.Path(__file__).parent
role, nonce, outside = sys.argv[1:]
deadline = time.monotonic() + 20
child = None

def publish(name, value):
    temporary = root / (name + '.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(root / name)

try:
    if (root / 'cleanup').exists():
        sys.exit(93)
    (root / (role + '-inside')).write_text('allowed')
    denied = {}
    try:
        pathlib.Path(outside + '-' + role).write_text('must-not-exist')
    except PermissionError as error:
        denied['filesystem'] = error.errno
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
    except PermissionError as error:
        denied['network'] = error.errno
    if role == 'parent':
        child = subprocess.Popen([sys.executable, __file__, 'grandchild', nonce, outside])
    publish(role + '-ready', {'nonce': nonce, 'role': role, 'pid': os.getpid(),
            'ppid': os.getppid(), 'pgid': os.getpgrp(), 'denied': denied})
    counter = 0
    while time.monotonic() < deadline:
        if (root / 'cleanup').exists():
            sys.exit(93)
        if (root / 'effect-release').exists():
            with (root / (role + '-effect')).open('a') as effect:
                effect.write('x')
            if child is not None:
                if child.wait(timeout=min(1, max(0.01, deadline - time.monotonic()))) != 0:
                    raise RuntimeError('grandchild control failed')
                print('TREE_CONTROL_OK', flush=True)
            sys.exit(0)
        counter += 1
        publish(role + '-beat', counter)
        time.sleep(0.02)
    raise TimeoutError('fixture self-expiry, not product termination')
finally:
    if child is not None and child.poll() is None:
        child.kill()
        child.wait(timeout=1)
"#;

struct TreeFixture {
    root: PathBuf,
    outside: PathBuf,
    nonce: String,
    started: AtomicBool,
    session: Mutex<Option<String>>,
    identities: Mutex<Vec<Identity>>,
}

impl TreeFixture {
    fn new(s: &LifecycleServer) -> Self {
        let nonce = uuid::Uuid::new_v4().to_string();
        let root = s.workspace.join(format!("tree-{nonce}"));
        std::fs::create_dir(&root).unwrap();
        std::fs::write(root.join("tree.py"), TREE).unwrap();
        let outside = s
            .workspace
            .parent()
            .unwrap()
            .join(format!("outside-{nonce}"));
        for role in ["parent", "grandchild"] {
            let path = PathBuf::from(format!("{}-{role}", outside.display()));
            std::fs::write(&path, "host-control").unwrap();
            std::fs::remove_file(path).unwrap();
        }
        Self {
            root,
            outside,
            nonce,
            started: AtomicBool::new(false),
            session: Mutex::new(None),
            identities: Mutex::new(Vec::new()),
        }
    }

    fn id(&self) -> String {
        self.session
            .lock()
            .unwrap()
            .clone()
            .expect("PROBE_SETUP: session identity")
    }

    async fn start(&self, s: &LifecycleServer, timeout: u64, until: Instant) {
        self.started.store(true, Ordering::Release);
        let first = request(s, "exec_command", json!({
            "cmd": format!("python3 '{}' parent {} '{}'", self.root.join("tree.py").display(), self.nonce, self.outside.display()),
            "timeout_ms": timeout, "yield_time_ms": 0
        }), until).await;
        *self.session.lock().unwrap() = first["session_id"].as_str().map(str::to_owned);
        assert_initial_boundary(&first);
        assert_eq!(first["status"], "running", "{first}");
        assert!(!self.id().is_empty());
    }

    fn counters(&self) -> [u64; 2] {
        ["parent", "grandchild"].map(|role| {
            serde_json::from_str(
                &std::fs::read_to_string(self.root.join(format!("{role}-beat"))).unwrap(),
            )
            .unwrap()
        })
    }

    async fn ready(&self, until: Instant) {
        while !["parent", "grandchild"].iter().all(|role| {
            self.root.join(format!("{role}-ready")).exists()
                && self.root.join(format!("{role}-beat")).exists()
        }) {
            assert!(
                Instant::now() < until,
                "PROBE_SETUP: tree readiness deadline"
            );
            sleep(Duration::from_millis(10)).await;
        }
        let mut owned = Vec::new();
        for role in ["parent", "grandchild"] {
            let ready: Value = serde_json::from_str(
                &std::fs::read_to_string(self.root.join(format!("{role}-ready"))).unwrap(),
            )
            .unwrap();
            assert_eq!(ready["nonce"], self.nonce);
            let actual = process(ready["pid"].as_u64().unwrap())
                .unwrap()
                .expect("PROBE_SETUP: live ready identity");
            let cmdline = std::fs::read(format!("/proc/{}/cmdline", actual.pid)).unwrap();
            assert!(cmdline
                .split(|byte| *byte == 0)
                .any(|part| part == self.nonce.as_bytes()));
            let script = self.root.join("tree.py");
            assert!(cmdline
                .split(|byte| *byte == 0)
                .any(|part| part == script.as_os_str().as_encoded_bytes()));
            self.identities.lock().unwrap().push(actual.clone());
            assert_eq!(ready["role"], role);
            assert_ne!(actual.state, "Z");
            assert_eq!(ready["ppid"], actual.ppid);
            assert_eq!(ready["pgid"], actual.pgid);
            assert_eq!(ready["denied"], json!({"filesystem": 13, "network": 1}));
            assert_eq!(
                std::fs::read_to_string(self.root.join(format!("{role}-inside"))).unwrap(),
                "allowed"
            );
            assert!(!PathBuf::from(format!("{}-{role}", self.outside.display())).exists());
            eprintln!("TREE_READY {} {role}: {ready}; proc={actual:?}", self.nonce);
            owned.push(actual);
        }
        assert_ne!(owned[0].pid, owned[1].pid);
        assert_eq!(owned[0].ppid, u64::from(std::process::id()));
        assert_eq!(owned[1].ppid, owned[0].pid);
        assert!(owned.iter().all(|item| item.pgid == owned[0].pid));
        let before = self.counters();
        while self
            .counters()
            .iter()
            .zip(before)
            .any(|(now, old)| *now <= old)
        {
            assert!(Instant::now() < until, "PROBE_SETUP: missing live progress");
            sleep(Duration::from_millis(10)).await;
        }
        assert!(
            Instant::now() < until,
            "PROBE_SETUP: readiness exceeded deadline"
        );
        eprintln!(
            "TREE_PROGRESS {}: {:?} -> {:?}",
            self.nonce,
            before,
            self.counters()
        );
    }

    fn stopped(&self) -> std::io::Result<bool> {
        let owned = self.identities.lock().unwrap();
        if owned.len() != 2 {
            return Ok(false);
        }
        for item in owned.iter() {
            if process(item.pid)?
                .is_some_and(|current| current.start == item.start && current.state != "Z")
            {
                return Ok(false);
            }
        }
        Ok(true)
    }

    async fn wait_stopped(&self, until: Instant) {
        while !self.stopped().expect("PROBE_SETUP: process observation") {
            assert!(
                Instant::now() < until,
                "live original process survived termination"
            );
            sleep(Duration::from_millis(10)).await;
        }
        assert!(
            Instant::now() < until,
            "PROBE_SETUP: process reconciliation deadline"
        );
        eprintln!(
            "TREE_STOPPED {}: {:?}",
            self.nonce,
            self.identities.lock().unwrap()
        );
    }

    async fn no_later_effect(&self) {
        let before = self.counters(); // Captured only after terminal/process reconciliation.
        std::fs::write(self.root.join("effect-release"), "observe").unwrap();
        let until = Instant::now() + Duration::from_millis(500);
        loop {
            assert!(self.stopped().unwrap());
            assert_eq!(self.counters(), before);
            for role in ["parent", "grandchild"] {
                assert!(
                    !self.root.join(format!("{role}-effect")).exists(),
                    "late workload effect"
                );
            }
            if Instant::now() >= until {
                break;
            }
            sleep(Duration::from_millis(20)).await;
        }
        eprintln!("TREE_NO_LATER_EFFECT {}: {before:?}", self.nonce);
    }

    async fn cleanup(&self, s: Arc<LifecycleServer>) {
        if !self.started.load(Ordering::Acquire) {
            return;
        }
        let mut verified = std::fs::write(self.root.join("cleanup"), "cleanup").is_ok();
        let until = Instant::now() + Duration::from_secs(3);
        let id = self.session.lock().unwrap().clone();
        if let Some(id) = id {
            let reply = tokio::spawn(async move {
                request(
                    &s,
                    "kill_session",
                    json!({"session_id": id, "signal": "KILL", "wait_ms": 50}),
                    until.min(Instant::now() + Duration::from_secs(1)),
                )
                .await
            })
            .await;
            verified &= reply
                .is_ok_and(|out| out["ok"] == true || out["error"]["code"] == "SESSION_NOT_FOUND");
        }
        // Unknown/partial identities consume the entire bound, never imply stopped.
        while Instant::now() < until && !self.stopped().unwrap_or(false) {
            sleep(Duration::from_millis(20)).await;
        }
        assert!(
            verified && self.stopped().unwrap_or(false),
            "PROBE_SETUP: owned cleanup unconfirmed for {}",
            self.nonce
        );
    }
}

impl Drop for TreeFixture {
    fn drop(&mut self) {
        let _ = std::fs::write(self.root.join("cleanup"), "fallback");
    }
}

async fn request(s: &LifecycleServer, name: &str, args: Value, until: Instant) -> Value {
    let out = timeout_at(until, s.rpc(name, args))
        .await
        .expect("PROBE_SETUP: HTTP phase deadline");
    assert!(
        Instant::now() < until,
        "PROBE_SETUP: HTTP response exceeded phase deadline"
    );
    out
}

async fn terminal(s: &LifecycleServer, tree: &TreeFixture, until: Instant, reason: &str) -> Value {
    loop {
        let out = request(
            s,
            "write_stdin",
            json!({"session_id": tree.id(), "chars": "", "yield_time_ms": 20}),
            until,
        )
        .await;
        assert_eq!(out["ok"], true, "{out}");
        assert_eq!(out["transport_ok"], true, "{out}");
        assert_eq!(out["session_id"], tree.id(), "{out}");
        if out["status"] == "exited" {
            assert_eq!(out["termination_reason"], reason, "{out}");
            assert_eq!(out["stdin_open"], false, "{out}");
            assert_eq!(out["process_may_be_running"], false, "{out}");
            return out;
        }
        assert_eq!(out["status"], "running", "{out}");
    }
}

async fn control(s: &LifecycleServer, tree: &TreeFixture) {
    let started = Instant::now();
    let until = started + Duration::from_secs(8);
    tree.start(s, 8000, started + Duration::from_secs(3)).await;
    tree.ready(started + Duration::from_secs(3)).await;
    std::fs::write(tree.root.join("effect-release"), "control").unwrap();
    let mut out = terminal(s, tree, until, "exited").await;
    while out["stdout"].as_str() != Some("TREE_CONTROL_OK\n") {
        sleep(Duration::from_millis(10)).await;
        out = terminal(s, tree, until, "exited").await;
    }
    require_real_child(&out);
    tree.wait_stopped(until).await;
    for role in ["parent", "grandchild"] {
        assert_eq!(
            std::fs::read_to_string(tree.root.join(format!("{role}-effect"))).unwrap(),
            "x"
        );
    }
    eprintln!("TREE_CONTROL_EFFECTS {}: parent=x grandchild=x", tree.nonce);
}

async fn exercise(s: &LifecycleServer, tree: &TreeFixture, kill: bool) {
    let started = Instant::now();
    tree.start(
        s,
        if kill { 15000 } else { 8000 },
        started + Duration::from_secs(3),
    )
    .await;
    tree.ready(started + Duration::from_secs(3)).await;
    let until = if kill {
        Instant::now() + Duration::from_secs(3)
    } else {
        started + Duration::from_secs(11)
    };
    let mut evicted = false;
    let out = if kill {
        let ack = request(
            s,
            "kill_session",
            json!({"session_id": tree.id(), "signal": "KILL", "wait_ms": 50}),
            until,
        )
        .await;
        assert_eq!(ack["ok"], true, "{ack}");
        assert_eq!(ack["transport_ok"], true, "{ack}");
        assert_eq!(ack["session_id"], tree.id(), "{ack}");
        if ack["status"] == "killed" {
            assert_eq!(ack["killed"], true, "{ack}");
            assert_eq!(ack["evicted"], true, "{ack}");
            evicted = true;
            ack
        } else {
            assert_eq!(ack["status"], "terminating", "{ack}");
            assert_eq!(ack["killed"], false, "{ack}");
            assert_eq!(ack["evicted"], false, "{ack}");
            terminal(s, tree, until, "killed").await
        }
    } else {
        terminal(s, tree, until, "timeout").await
    };
    assert_eq!(
        out["termination_reason"],
        if kill { "killed" } else { "timeout" },
        "{out}"
    );
    assert_eq!(out["command_ok"], false, "{out}");
    assert_eq!(out["stdin_open"], false, "{out}");
    assert_eq!(out["process_may_be_running"], false, "{out}");
    tree.wait_stopped(until).await;
    tree.no_later_effect().await;
    let late = request(
        s,
        "write_stdin",
        json!({"session_id": tree.id(), "chars": "must-not-run", "yield_time_ms": 0}),
        Instant::now() + Duration::from_secs(1),
    )
    .await;
    assert_eq!(late["ok"], false, "{late}");
    assert_eq!(
        late["error"]["code"],
        if evicted {
            "SESSION_NOT_FOUND"
        } else {
            "SESSION_CLOSED"
        },
        "{late}"
    );
}

async fn run_case(kill: bool) {
    let s = Arc::new(LifecycleServer::start());
    s.approve();
    let positive = Arc::new(TreeFixture::new(&s));
    let negative = Arc::new(TreeFixture::new(&s));
    let (server, first, second) = (s.clone(), positive.clone(), negative.clone());
    let outcome = tokio::spawn(async move {
        control(&server, &first).await;
        exercise(&server, &second, kill).await;
    })
    .await;
    let mut cleanup_ok = true;
    for tree in [positive.clone(), negative.clone()] {
        let server = s.clone();
        cleanup_ok &= tokio::spawn(async move { tree.cleanup(server).await })
            .await
            .is_ok();
    }
    drop(positive);
    drop(negative);
    let server = Arc::try_unwrap(s)
        .ok()
        .expect("PROBE_SETUP: listener ownership");
    cleanup_ok &= tokio::spawn(server.close()).await.is_ok();
    if let Err(error) = outcome {
        if error.is_panic() {
            std::panic::resume_unwind(error.into_panic());
        }
        panic!("PROBE_SETUP: case body cancelled: {error}");
    }
    assert!(cleanup_ok, "PROBE_SETUP: owned cleanup failed");
}

#[tokio::test]
async fn authenticated_timeout_stops_sandboxed_process_tree() {
    run_case(false).await;
}

#[tokio::test]
async fn authenticated_kill_session_stops_sandboxed_process_tree() {
    run_case(true).await;
}

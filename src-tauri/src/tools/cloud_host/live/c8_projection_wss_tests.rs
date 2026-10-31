//! A1 C8-1 (SPEC v5.6 §3.3): the projection hand-off end to end, replacing the
//! `c7_fake_runner` stand-in: a cloud spawn marks the projection dirty, the
//! production runner's tick challenges the real gateway (native_desktop_fixture
//! over WSS, real PostgreSQL), the gateway acknowledges the v2 projection, and
//! the acknowledgement releases the waiting spawn as `applied`. The gateway
//! then admits a worker call for the projected worker.
//!
//! A1 C9n nit 1: under load this test's own waits no longer go through the
//! frozen `Harness::wait` (18 s, wss_tests.rs:186, which only names the field on
//! timeout). The eligibility wait has its own 60 s budget and prints the last
//! fixture state, the agent link state and a phase timeline on timeout; every
//! failing assertion carries the same timeline. The `ready` wait inside the
//! frozen `Harness::start` keeps its 18 s; a panic there is labelled by the
//! timeline as "in Harness::start" (recorded, frozen file not touched).
use super::wss_tests::Harness;
use serde_json::{json, Value};
use std::time::{Duration, Instant};

const SCOPES: [&str; 3] = ["agents.manage", "files.read", "files.write"];
/// Own budget for the eligibility wait (the frozen `Harness::wait` has 18 s).
const STATE_WAIT: Duration = Duration::from_secs(60);
/// Own budget for the spawn round trip (it holds a bounded 3 s projection wait).
const SPAWN_BUDGET: Duration = Duration::from_secs(20);

/// Phase timeline since the test began; printed on every failure.
struct Trail {
    t0: Instant,
    phases: Vec<(&'static str, Duration)>,
}
impl Trail {
    fn new() -> Self {
        Self {
            t0: Instant::now(),
            phases: Vec::new(),
        }
    }
    fn mark(&mut self, phase: &'static str) {
        self.phases.push((phase, self.t0.elapsed()));
    }
}
impl std::fmt::Display for Trail {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "timeline [")?;
        for (phase, at) in &self.phases {
            write!(f, "{phase}@{:.2}s ", at.as_secs_f64())?;
        }
        write!(f, "now@{:.2}s]", self.t0.elapsed().as_secs_f64())
    }
}
impl Drop for Trail {
    fn drop(&mut self) {
        if std::thread::panicking() {
            let at = if self.phases.is_empty() {
                " (still in Harness::start: its frozen 18 s ready wait)"
            } else {
                ""
            };
            eprintln!("c8_projection_wss failed{at}: {self}");
        }
    }
}

fn link_state(h: &Harness) -> String {
    h.link
        .as_ref()
        .map(|l| format!("{:?}", *l.borrow()))
        .unwrap_or_else(|| "none".into())
}

/// The test's own state wait: [`STATE_WAIT`] budget, and on timeout the last
/// fixture state (public metadata only), the link state and the timeline.
async fn wait_state(h: &Harness, field: &str, trail: &Trail) -> Value {
    let end = Instant::now() + STATE_WAIT;
    loop {
        let state = h.inspect().await;
        if state[field] == true {
            return state;
        }
        assert!(
            !h.agent.as_ref().is_some_and(|task| task.is_finished()),
            "native Agent exited while waiting for {field}; last state {state}; link {}; {trail}",
            link_state(h)
        );
        assert!(
            Instant::now() < end,
            "c8 state timeout ({field}) after {STATE_WAIT:?}; last state {state}; link {}; {trail}",
            link_state(h)
        );
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn c8_runner_tick_gateway_ack_releases_cloud_spawn_as_applied() {
    let mut trail = Trail::new();
    let h = Harness::start().await;
    trail.mark("started");
    let workspace = h.host.tools.context.host.workspace_root.clone();
    for args in [
        &["init", "-q"][..],
        &["add", "native-canary.txt"],
        &[
            "-c",
            "user.name=F",
            "-c",
            "user.email=f@example.invalid",
            "commit",
            "-q",
            "-m",
            "f",
        ],
    ] {
        let out = std::process::Command::new("git")
            .current_dir(&workspace)
            .args(args)
            .output()
            .unwrap();
        assert!(out.status.success(), "git {args:?}: {out:?} {trail}");
    }
    trail.mark("git");
    let pending = h
        .rpc(
            8100,
            "native-A",
            "request_chat_authorization",
            json!({ "scopes": SCOPES }),
        )
        .await;
    assert_eq!(
        pending["authorization"]["status"], "pending",
        "{pending} {trail}"
    );
    let id = pending["authorization"]["id"].as_str().unwrap().to_owned();
    let scopes: Vec<String> = SCOPES.iter().map(|s| (*s).to_owned()).collect();
    h.host
        .tools
        .authorizer
        .decide("native-wss", &id, true, &scopes)
        .unwrap();
    trail.mark("decided");
    wait_state(&h, "eligible_a", &trail).await;
    trail.mark("eligible");

    let t = Instant::now();
    let spawned = h
        .rpc(
            8101,
            "native-A",
            "subagent_spawn",
            json!({ "request_id": "c8-e2e-1" }),
        )
        .await;
    trail.mark("spawned");
    assert_eq!(spawned["ok"], true, "{spawned} {trail}");
    assert_eq!(
        spawned["projection"],
        "applied",
        "runner tick -> gateway ack did not release the spawn: {spawned}; state {}; link {}; {trail}",
        h.inspect().await,
        link_state(&h)
    );
    assert!(
        t.elapsed() < SPAWN_BUDGET,
        "spawn took {:?} (budget {SPAWN_BUDGET:?}); {trail}",
        t.elapsed()
    );
    let worker = spawned["worker"]["worker_id"].as_str().unwrap().to_owned();

    // The acknowledged projection is what the gateway now checks: the projected
    // worker is admitted, an unprojected one is not.
    let read = h
        .rpc(
            8102,
            "native-A",
            "read_file",
            json!({ "path": "native-canary.txt", "worker_id": worker }),
        )
        .await;
    assert_eq!(read["ok"], true, "{read} {trail}");
    let foreign = h
        .rpc(
            8103,
            "native-A",
            "read_file",
            json!({ "path": "native-canary.txt", "worker_id": "f".repeat(32) }),
        )
        .await;
    assert_eq!(foreign["ok"], false, "{foreign} {trail}");
    assert_eq!(
        foreign["error"]["code"], "WORKER_NOT_OWNED",
        "{foreign} {trail}"
    );
}

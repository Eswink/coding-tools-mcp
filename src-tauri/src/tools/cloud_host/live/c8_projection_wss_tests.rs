//! A1 C8-1 (SPEC v5.6 §3.3): the projection hand-off end to end, replacing the
//! `c7_fake_runner` stand-in: a cloud spawn marks the projection dirty, the
//! production runner's tick challenges the real gateway (native_desktop_fixture
//! over WSS, real PostgreSQL), the gateway acknowledges the v2 projection, and
//! the acknowledgement releases the waiting spawn as `applied`. The gateway
//! then admits a worker call for the projected worker.
use super::wss_tests::Harness;
use serde_json::json;

const SCOPES: [&str; 3] = ["agents.manage", "files.read", "files.write"];

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn c8_runner_tick_gateway_ack_releases_cloud_spawn_as_applied() {
    let h = Harness::start().await;
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
        assert!(out.status.success(), "git {args:?}: {out:?}");
    }
    let pending = h
        .rpc(
            8100,
            "native-A",
            "request_chat_authorization",
            json!({ "scopes": SCOPES }),
        )
        .await;
    assert_eq!(pending["authorization"]["status"], "pending", "{pending}");
    let id = pending["authorization"]["id"].as_str().unwrap().to_owned();
    let scopes: Vec<String> = SCOPES.iter().map(|s| (*s).to_owned()).collect();
    h.host
        .tools
        .authorizer
        .decide("native-wss", &id, true, &scopes)
        .unwrap();
    h.wait("eligible_a", true).await;

    let t = std::time::Instant::now();
    let spawned = h
        .rpc(
            8101,
            "native-A",
            "subagent_spawn",
            json!({ "request_id": "c8-e2e-1" }),
        )
        .await;
    assert_eq!(spawned["ok"], true, "{spawned}");
    assert_eq!(
        spawned["projection"], "applied",
        "runner tick -> gateway ack did not release the spawn: {spawned}"
    );
    assert!(
        t.elapsed() < std::time::Duration::from_secs(8),
        "{:?}",
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
    assert_eq!(read["ok"], true, "{read}");
    let foreign = h
        .rpc(
            8103,
            "native-A",
            "read_file",
            json!({ "path": "native-canary.txt", "worker_id": "f".repeat(32) }),
        )
        .await;
    assert_eq!(foreign["ok"], false, "{foreign}");
    assert_eq!(foreign["error"]["code"], "WORKER_NOT_OWNED", "{foreign}");
}

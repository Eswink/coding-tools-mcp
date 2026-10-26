//! S2 GO-A live fault suite: (a)(b1)(c)(f1). Not scanned by issue40 inventory.
//! Hard-drop main path expects WORKSPACE_OFFLINE; assertion set also allows
//! EXECUTION_NOT_CONNECTED. (d) hold_up deferred to S2-4. eng ≠ QUALIFIED ≠ FINAL.
use super::*;
use coding_tools_cloud_agent::LinkState;
use serde_json::json;
use std::time::{Duration, Instant};

fn offline_set(code: &str) -> bool {
    matches!(code, "WORKSPACE_OFFLINE" | "EXECUTION_NOT_CONNECTED")
}

fn ledger_count(inspect: &Value, state: &str) -> i64 {
    inspect["ledger"]["by_state"][state].as_i64().unwrap_or(0)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn s2_online_workspace_probe_completes_ledger_and_same_id_is_not_replayed() {
    let h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    let before = h.inspect().await;
    let completed0 = ledger_count(&before, "completed");
    let result = h.rpc(8101, "native-A", "workspace_probe", json!({})).await;
    assert_eq!(result["ok"], true, "NATIVE_CLOUD_DISPATCH_DID_NOT_EXECUTE");
    assert_eq!(result["execution"], "native_tool_dispatch");
    assert!(!result.to_string().contains("native-canary.txt"));
    let after = h.inspect().await;
    assert_eq!(ledger_count(&after, "completed"), completed0 + 1);
    assert_eq!(after["ledger"]["last"]["state"], "completed");
    assert_eq!(after["ledger"]["last"]["result_hash_len"], 32);
    let again = h.rpc(8101, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(again["ok"], true, "same id must not complete twice");
    let after_replay = h.inspect().await;
    assert_eq!(
        ledger_count(&after_replay, "completed"),
        completed0 + 1,
        "completed must not increase on same-id replay"
    );
    assert_eq!(
        h.rpc(8102, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn s2_hard_drop_returns_offline_set_without_queue_or_replay() {
    let h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    h.wait_link_online().await;
    let before = h.inspect().await;
    let running0 = ledger_count(&before, "running");
    let admitted0 = ledger_count(&before, "admitted");
    h.relay("drop").await;
    h.wait_not_ready_or_offline_link().await;
    let offline = h.rpc(8201, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(offline["ok"], true);
    let code = offline["error"]["code"].as_str().unwrap_or("");
    assert!(
        offline_set(code),
        "expected WORKSPACE_OFFLINE|EXECUTION_NOT_CONNECTED, got {code}"
    );
    // Primary hard-drop path is WORKSPACE_OFFLINE; ENC allowed only as a flash.
    if code != "WORKSPACE_OFFLINE" {
        eprintln!(
            "s2_hard_drop: observed {code} (allowed set member; primary is WORKSPACE_OFFLINE)"
        );
    }
    let mid = h.inspect().await;
    assert_eq!(ledger_count(&mid, "running"), running0);
    assert_eq!(ledger_count(&mid, "admitted"), admitted0);
    h.oauth_refresh_ok().await;
    let catalog = h.tools_list(8202).await;
    assert!(!catalog["result"]["tools"].as_array().unwrap().is_empty());
    // Gateway still alive: inspect must succeed.
    let _ = h.inspect().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn s2_hard_drop_then_reconnect_increments_generation_and_new_call_ok() {
    let h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    h.wait_link_online().await;
    let gen0 = h.inspect().await["channel"]["generation"].as_i64().unwrap();
    h.relay("drop").await;
    // Wait until we leave Online, then wait until Online again without restarting Agent.
    let end_leave = Instant::now() + Duration::from_secs(8);
    loop {
        if h.link() != LinkState::Online {
            break;
        }
        assert!(Instant::now() < end_leave, "never left Online after drop");
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    h.wait_link_online().await;
    h.wait("ready", true).await;
    h.wait("eligible_a", true).await;
    let after = h.inspect().await;
    let gen1 = after["channel"]["generation"].as_i64().unwrap();
    assert!(
        gen1 > gen0,
        "generation must strictly increase after reconnect ({gen0} -> {gen1})"
    );
    assert_eq!(
        h.rpc(8301, "native-A", "workspace_probe", json!({})).await["ok"],
        true
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn s2_revoke_device_closes_agent_and_tools_call_needs_authorization() {
    let h = Harness::start().await;
    h.approve("native-A", "eligible_a").await;
    h.wait_link_online().await;
    h.revoke_device().await;
    // Sample link: Online must not return during the observation window.
    let end = Instant::now() + Duration::from_secs(15);
    let mut saw_non_online = false;
    while Instant::now() < end {
        match h.link() {
            LinkState::Online => {
                if saw_non_online {
                    panic!("Agent returned to Online after device revoke");
                }
            }
            LinkState::Connecting | LinkState::Reconnecting { .. } => {
                saw_non_online = true;
            }
            other => {
                saw_non_online = true;
                let _ = other;
            }
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(
        saw_non_online || h.inspect().await["ready"] == false,
        "revoke must take the Agent off Online / ready"
    );
    let denied = h.rpc(8501, "native-A", "workspace_probe", json!({})).await;
    assert_ne!(denied["ok"], true);
    let code = denied["error"]["code"].as_str().unwrap_or("");
    // Primary expectation CHAT_AUTHORIZATION_REQUIRED; WORKSPACE_OFFLINE allowed if
    // the channel was torn down first.
    assert!(
        matches!(
            code,
            "CHAT_AUTHORIZATION_REQUIRED" | "WORKSPACE_OFFLINE" | "EXECUTION_NOT_CONNECTED"
        ),
        "unexpected revoke error code {code}"
    );
    if code != "CHAT_AUTHORIZATION_REQUIRED" {
        eprintln!("s2_revoke: observed {code} (primary expectation CHAT_AUTHORIZATION_REQUIRED)");
    }
    h.oauth_refresh_ok().await;
}
